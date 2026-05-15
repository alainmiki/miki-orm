"""Single canonical schema editor used by both `Model._ensure_table_exists`
and the migration engine.

The editor takes a model class (or a list of column descriptors) and emits
the SQL needed to create or alter a table.  Per-engine quirks are handled
via small overrides; the common path lives here.

Design goals:

* DRY - the field-to-SQL mapping lives in exactly one place.
* Safe - identifiers go through the dialect quoter; defaults are emitted
  using safe literal encoding for the few cases ALTER TABLE prohibits
  parameter binding (otherwise we always parameterise).
* Reversible - the editor knows how to drop what it creates.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from .dialect import Dialect, SafeBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field → SQL type table (single source of truth)
# ---------------------------------------------------------------------------
# The function is dialect-aware: UUID is native in PostgreSQL, but a fixed
# VARCHAR elsewhere; JSON maps to JSONB on PG, JSON on MySQL, TEXT on SQLite.


def field_to_sql_type(field: Any, dialect: Dialect) -> str:
    """Return the dialect-specific SQL column type for *field*."""
    # Lazy import - avoids a circular dependency between fields and backends.
    from ...models.fields import (
        AutoField,
        BigAutoField,
        BigIntegerField,
        BinaryField,
        BooleanField,
        CharField,
        DateField,
        DateTimeField,
        DecimalField,
        DurationField,
        EmailField,
        FilePathField,
        FloatField,
        GenericIPAddressField,
        IntegerField,
        JSONField,
        PositiveIntegerField,
        PositiveSmallIntegerField,
        SlugField,
        SmallAutoField,
        SmallIntegerField,
        TextField,
        TimeField,
        URLField,
        UUIDField,
    )
    from ...models.relationships import ForeignKey, OneToOneField

    name = field.__class__.__name__

    # Auto-increment primary keys.
    if isinstance(field, (AutoField, SmallAutoField)):
        if dialect == Dialect.POSTGRESQL:
            return "SERIAL"
        if dialect == Dialect.MYSQL:
            return "INTEGER"
        return "INTEGER"
    if isinstance(field, BigAutoField):
        if dialect == Dialect.POSTGRESQL:
            return "BIGSERIAL"
        return "BIGINT"

    if isinstance(field, BigIntegerField):
        return "BIGINT"
    if isinstance(field, (IntegerField, SmallIntegerField,
                          PositiveIntegerField, PositiveSmallIntegerField)):
        return "INTEGER"

    if isinstance(field, (ForeignKey, OneToOneField)):
        return "INTEGER"  # PK type of referenced table; INTEGER covers AutoField

    if isinstance(field, CharField):
        return f"VARCHAR({field.max_length or 255})"
    if isinstance(field, TextField):
        return "TEXT"
    if isinstance(field, BooleanField):
        if dialect == Dialect.POSTGRESQL:
            return "BOOLEAN"
        return "INTEGER"  # SQLite/MySQL store as integer for portability
    if isinstance(field, FloatField):
        return "DOUBLE PRECISION" if dialect == Dialect.POSTGRESQL else "REAL"
    if isinstance(field, DecimalField):
        return f"DECIMAL({field.max_digits}, {field.decimal_places})"
    if isinstance(field, DurationField):
        return "BIGINT"

    if isinstance(field, DateTimeField):
        if dialect == Dialect.POSTGRESQL:
            return "TIMESTAMPTZ"
        if dialect == Dialect.MYSQL:
            return "DATETIME(6)"
        return "DATETIME"
    if isinstance(field, DateField):
        return "DATE"
    if isinstance(field, TimeField):
        return "TIME"

    if isinstance(field, UUIDField):
        if dialect == Dialect.POSTGRESQL:
            return "UUID"
        if dialect == Dialect.MYSQL:
            return "CHAR(36)"
        return "VARCHAR(36)"

    if isinstance(field, JSONField):
        if dialect == Dialect.POSTGRESQL:
            return "JSONB"
        if dialect == Dialect.MYSQL:
            return "JSON"
        return "TEXT"

    if isinstance(field, BinaryField):
        if dialect == Dialect.POSTGRESQL:
            return "BYTEA"
        if dialect == Dialect.MYSQL:
            return "BLOB"
        return "BLOB"

    if isinstance(field, EmailField):
        return f"VARCHAR({field.max_length or 254})"
    if isinstance(field, URLField):
        return f"VARCHAR({field.max_length or 200})"
    if isinstance(field, SlugField):
        return f"VARCHAR({field.max_length or 50})"
    if isinstance(field, GenericIPAddressField):
        return "INET" if dialect == Dialect.POSTGRESQL else "VARCHAR(45)"
    if isinstance(field, FilePathField):
        return "VARCHAR(255)"

    logger.debug("No SQL mapping for %s, falling back to TEXT", name)
    return "TEXT"


def _safe_default_literal(value: Any) -> str:
    """Encode a default value as a literal SQL fragment.

    Only used in contexts (mainly SQLite ALTER TABLE ADD COLUMN) where
    parameter binding is not allowed.  Strings are JSON-encoded for safe
    quoting.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # ``json.dumps`` gives us a properly escaped double-quoted literal;
        # swap the outer quotes to single-quotes for SQL.
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, (list, dict)):
        return "'" + json.dumps(value).replace("'", "''") + "'"
    # Fallback - stringify and quote.
    return "'" + str(value).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Schema editor
# ---------------------------------------------------------------------------


class SchemaEditor:
    """Generate and execute schema changes for a single connection."""

    def __init__(
        self,
        connection: Any,
        dialect: Dialect = Dialect.SQLITE,
        *,
        collect_sql: bool = False,
    ) -> None:
        self.connection = connection
        self.dialect = dialect
        self.builder = SafeBuilder(dialect)
        self.collect_sql = collect_sql
        self.collected: list[tuple[str, list[Any]]] = []

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def table_name_for(self, model: type) -> str:
        return getattr(model._meta, "table_name", None) or model.__name__.lower() + "s"

    def create_model(self, model: type, *, if_not_exists: bool = True) -> None:
        """Build ``CREATE TABLE`` for *model* and execute it."""
        sql, params = self.build_create_table_sql(model, if_not_exists=if_not_exists)
        self._execute(sql, params)
        for idx_sql, idx_params in self.build_create_indexes_sql(model):
            self._execute(idx_sql, idx_params)
        # Through-tables for ManyToManyField.
        from ...models.relationships import ManyToManyField
        for fname, fobj in model._meta.fields.items():
            if isinstance(fobj, ManyToManyField):
                self.create_m2m_through(model, fname, fobj)

    def delete_model(self, model: type, *, if_exists: bool = True) -> None:
        table = self.builder.quote_table(self.table_name_for(model))
        exists = "IF EXISTS " if if_exists else ""
        self._execute(f"DROP TABLE {exists}{table}", [])

    def add_field(self, model: type, field: Any) -> None:
        table = self.builder.quote_table(self.table_name_for(model))
        col_def, params = self._column_def(field, for_alter=True)
        self._execute(f"ALTER TABLE {table} ADD COLUMN {col_def}", params)

    def drop_field(self, model: type, field_name: str) -> None:
        if self.dialect == Dialect.SQLITE:
            # SQLite 3.35+ supports DROP COLUMN; we attempt it and let the
            # driver raise if unsupported.
            table = self.builder.quote_table(self.table_name_for(model))
            col = self.builder.quote_column(field_name)
            self._execute(f"ALTER TABLE {table} DROP COLUMN {col}", [])
            return
        table = self.builder.quote_table(self.table_name_for(model))
        col = self.builder.quote_column(field_name)
        self._execute(f"ALTER TABLE {table} DROP COLUMN {col}", [])

    def rename_field(self, model: type, old: str, new: str) -> None:
        table = self.builder.quote_table(self.table_name_for(model))
        old_col = self.builder.quote_column(old)
        new_col = self.builder.quote_column(new)
        self._execute(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}", [])

    def create_index(
        self,
        model: type,
        columns: Iterable[str],
        *,
        name: str | None = None,
        unique: bool = False,
    ) -> None:
        cols = list(columns)
        table_raw = self.table_name_for(model)
        quoted_cols = ", ".join(self.builder.quote_column(c) for c in cols)
        idx_name = name or f"idx_{table_raw}_{'_'.join(cols)}"
        unique_kw = "UNIQUE " if unique else ""
        self._execute(
            f"CREATE {unique_kw}INDEX IF NOT EXISTS "
            f"{self.builder.quote_identifier(idx_name)} "
            f"ON {self.builder.quote_table(table_raw)} ({quoted_cols})",
            [],
        )

    def drop_index(self, name: str) -> None:
        self._execute(
            f"DROP INDEX IF EXISTS {self.builder.quote_identifier(name)}", []
        )

    def create_m2m_through(self, model: type, field_name: str, m2m_field: Any) -> None:
        """Create the join table for a ManyToManyField."""
        through = m2m_field.db_table or (
            self.table_name_for(model) + "_" + field_name
        )
        src_col = self.builder.quote_column("source_id")
        tgt_col = self.builder.quote_column("target_id")
        quoted_through = self.builder.quote_table(through)
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {quoted_through} ("
            f"  {src_col} INTEGER NOT NULL, "
            f"  {tgt_col} INTEGER NOT NULL, "
            f"  PRIMARY KEY ({src_col}, {tgt_col})"
            f")"
        )
        self._execute(ddl, [])

    # ------------------------------------------------------------------
    # Building blocks
    # ------------------------------------------------------------------
    def build_create_table_sql(
        self, model: type, *, if_not_exists: bool = True
    ) -> tuple[str, list[Any]]:
        from ...models.relationships import ManyToManyField

        column_defs: list[str] = []
        params: list[Any] = []
        for fname, fobj in model._meta.fields.items():
            if isinstance(fobj, ManyToManyField):
                continue  # handled via through-table
            col_def, col_params = self._column_def(fobj)
            column_defs.append("  " + col_def)
            params.extend(col_params)

        exists = "IF NOT EXISTS " if if_not_exists else ""
        table = self.builder.quote_table(self.table_name_for(model))
        joined = ",\n".join(column_defs)
        sql = f"CREATE TABLE {exists}{table} (\n{joined}\n)"
        return sql, params

    def build_create_indexes_sql(self, model: type) -> list[tuple[str, list[Any]]]:
        stmts: list[tuple[str, list[Any]]] = []
        # db_index=True on individual fields
        for fname, fobj in model._meta.fields.items():
            if getattr(fobj, "db_index", False) and not fobj.primary_key:
                table_raw = self.table_name_for(model)
                idx_name = f"idx_{table_raw}_{fname}"
                stmts.append((
                    f"CREATE INDEX IF NOT EXISTS "
                    f"{self.builder.quote_identifier(idx_name)} "
                    f"ON {self.builder.quote_table(table_raw)} "
                    f"({self.builder.quote_column(fname)})",
                    [],
                ))
        # Meta.indexes - list of dicts {"name": ..., "columns": [...], "unique": bool}
        for idx in getattr(model._meta, "indexes", []) or []:
            cols = idx.get("columns") or []
            if not cols:
                continue
            name = idx.get("name") or f"idx_{self.table_name_for(model)}_{'_'.join(cols)}"
            unique_kw = "UNIQUE " if idx.get("unique") else ""
            quoted_cols = ", ".join(self.builder.quote_column(c) for c in cols)
            stmts.append((
                f"CREATE {unique_kw}INDEX IF NOT EXISTS "
                f"{self.builder.quote_identifier(name)} "
                f"ON {self.builder.quote_table(self.table_name_for(model))} "
                f"({quoted_cols})",
                [],
            ))
        return stmts

    # ------------------------------------------------------------------
    def _column_def(
        self, field: Any, *, for_alter: bool = False
    ) -> tuple[str, list[Any]]:
        from ...models.fields import AutoField, BigAutoField, SmallAutoField

        col = self.builder.quote_column(field.name)
        sql_type = field_to_sql_type(field, self.dialect)
        parts: list[str] = [col, sql_type]
        params: list[Any] = []

        # Primary key / auto-increment - dialect-specific clauses.
        is_auto_pk = isinstance(field, (AutoField, BigAutoField, SmallAutoField))
        if is_auto_pk:
            if self.dialect == Dialect.SQLITE:
                parts.append("PRIMARY KEY AUTOINCREMENT")
            elif self.dialect == Dialect.MYSQL:
                parts.append("AUTO_INCREMENT PRIMARY KEY")
            else:  # PostgreSQL SERIAL already implies sequence + PRIMARY KEY
                parts.append("PRIMARY KEY")
        elif field.primary_key:
            parts.append("PRIMARY KEY")

        # Nullability.  Auto PKs are implicitly NOT NULL.
        if not is_auto_pk:
            if field.null:
                parts.append("NULL")
            else:
                parts.append("NOT NULL")

        # UNIQUE.
        if field.unique and not field.primary_key:
            parts.append("UNIQUE")

        # DEFAULT.
        default = getattr(field, "default", None)
        if default is not None and not callable(default) and not is_auto_pk:
            if for_alter and self.dialect == Dialect.SQLITE:
                # SQLite ALTER TABLE ADD COLUMN demands a literal default.
                parts.append(f"DEFAULT {_safe_default_literal(default)}")
            else:
                ph = self.builder.param_placeholder
                parts.append(f"DEFAULT {ph}")
                params.append(field.db_value(default))

        return " ".join(parts), params

    # ------------------------------------------------------------------
    def _execute(self, sql: str, params: list[Any]) -> None:
        if self.collect_sql:
            self.collected.append((sql, list(params)))
            return
        logger.debug("schema: %s | params=%r", sql, params)
        self.connection.execute(sql, params)

    # Context-manager: commit on clean exit, rollback otherwise.
    def __enter__(self) -> "SchemaEditor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.collect_sql:
            return
        try:
            if exc_type is not None:
                self.connection.rollback()
            else:
                self.connection.commit()
        except Exception:
            pass


__all__ = ["SchemaEditor", "field_to_sql_type"]
