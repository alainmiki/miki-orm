"""Schema diff generation: compare model definitions to database schema."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .schema import get_introspector
from ..models.registry import ModelRegistry
from ..models.fields import (
    AutoField, BigAutoField, SmallAutoField,
    IntegerField, BigIntegerField, SmallIntegerField,
    PositiveIntegerField, PositiveSmallIntegerField,
    CharField, TextField, BooleanField,
    DecimalField, FloatField, DurationField,
    DateTimeField, DateField, TimeField,
    UUIDField, JSONField, BinaryField,
    EmailField, URLField, SlugField,
    GenericIPAddressField, FilePathField,
)
from ..models.relationships import (
    ForeignKey, OneToOneField, ManyToManyField,
)
from ..query.safe_builder import get_safe_builder

logger = logging.getLogger(__name__)


class SchemaDiffGenerator:
    """Generates migration operations by comparing model registry to DB schema."""

    def __init__(self, connection: Any, engine: str) -> None:
        self.connection = connection
        self.engine = engine
        self.introspector = get_introspector(connection, engine)
        self.builder = get_safe_builder(engine)

    def _get_db_schema(self) -> Dict[str, Dict[str, Any]]:
        """Return dict mapping table_name -> column_metadata."""
        schema: Dict[str, Dict[str, Any]] = {}
        try:
            tables = self.introspector.get_tables()
            for table in tables:
                columns = self.introspector.get_columns(table)
                indexes = self.introspector.get_indexes(table)
                constraints = self.introspector.get_constraints(table)
                schema[table] = {
                    "columns": {col["name"]: col for col in columns},
                    "indexes": indexes,
                    "constraints": constraints,
                }
        except Exception as e:
            logger.debug(f"Schema introspection failed: {e}")
        return schema

    def _get_model_meta(self, model_cls: type[Any]) -> Dict[str, Any]:
        """Extract table and column definitions from a model class."""
        table_name = getattr(model_cls._meta, "table_name", None) or model_cls.__name__.lower() + "s"
        fields = {}
        for fname, fobj in model_cls._meta.fields.items():
            fields[fname] = self._field_to_column_def(fobj)
        return {
            "table_name": table_name,
            "fields": fields,
        }

    def _field_to_column_def(self, field: Any) -> Dict[str, Any]:
        """Convert a Field instance to a column definition dict."""
        is_pk = field.primary_key
        sql_type = self._sql_type_for_field(field, include_auto=is_pk)
        
        col_def = {
            "name": field.name,
            "type": sql_type,
            "null": field.null,
            "default": field.default if not is_pk else None,
            "primary_key": is_pk,
            "unique": field.unique if hasattr(field, "unique") else False,
            "auto_increment": getattr(field, "auto_increment", False) or isinstance(field, (AutoField, BigAutoField, SmallAutoField)),
        }
        return col_def

    def _sql_type_for_field(self, field: Any, include_auto: bool = False) -> str:
        """Get SQL type string for a field."""
        if isinstance(field, (IntegerField, AutoField, SmallAutoField,
                              PositiveIntegerField, PositiveSmallIntegerField)):
            return "INTEGER"
        if isinstance(field, BigIntegerField):
            return "BIGINT"
        if isinstance(field, BigAutoField):
            return "BIGINT"
        if isinstance(field, CharField):
            ml = field.max_length or 255
            return f"VARCHAR({ml})"
        if isinstance(field, TextField):
            return "TEXT"
        if isinstance(field, BooleanField):
            return "BOOLEAN"
        if isinstance(field, DecimalField):
            return f"DECIMAL({field.max_digits}, {field.decimal_places})"
        if isinstance(field, FloatField):
            return "FLOAT"
        if isinstance(field, DurationField):
            return "BIGINT"
        if isinstance(field, DateTimeField):
            return "DATETIME"
        if isinstance(field, DateField):
            return "DATE"
        if isinstance(field, TimeField):
            return "TIME"
        if isinstance(field, UUIDField):
            return "VARCHAR(36)"
        if isinstance(field, JSONField):
            return "TEXT"
        if isinstance(field, BinaryField):
            return "BLOB"
        if isinstance(field, EmailField):
            ml = field.max_length or 254
            return f"VARCHAR({ml})"
        if isinstance(field, URLField):
            ml = field.max_length or 200
            return f"VARCHAR({ml})"
        if isinstance(field, SlugField):
            ml = field.max_length or 50
            return f"VARCHAR({ml})"
        if isinstance(field, GenericIPAddressField):
            return "VARCHAR(45)"
        if isinstance(field, FilePathField):
            return "VARCHAR(255)"
        if isinstance(field, (ForeignKey, OneToOneField)):
            # FK type inferred from referenced field; for now use INTEGER
            return "INTEGER"
        if isinstance(field, ManyToManyField):
            # M2M doesn't create a column; handled separately
            return None
        return "TEXT"

    def generate_diff(self) -> List[Any]:
        """Compare registered models to DB schema and return list of operations."""
        from .operations import (
            CreateTable, AddField, AlterField, DropField,
            CreateIndex, DropIndex, RenameField, DeleteModel
        )
        
        ops = []
        db_schema = self._get_db_schema()
        model_classes = ModelRegistry.all_models()
        
        # Track processed tables
        processed_tables = set()
        
        for model_cls in model_classes:
            meta = self._get_model_meta(model_cls)
            table_name = meta["table_name"]
            processed_tables.add(table_name)
            
            model_fields = meta["fields"]
            
            if table_name not in db_schema:
                # Table doesn't exist - create it
                columns_data = []
                for fname, fdef in model_fields.items():
                    if fdef.get("type") is not None:  # skip M2M
                        field = model_cls._meta.fields[fname]
                        columns_data.append({
                            "name": fname,
                            "field_type": f"{field.__module__}.{field.__class__.__name__}",
                            **{k: v for k, v in fdef.items() if k not in ("name", "field_type")}
                        })
                ops.append(CreateTable(name=table_name, columns=columns_data))
                continue
            
            # Table exists - compute column differences
            db_columns = db_schema[table_name]["columns"]
            db_col_names = set(db_columns.keys())
            model_col_names = set(model_fields.keys())
            
            # New columns -> AddField
            for col_name in model_col_names - db_col_names:
                field = model_cls._meta.fields[col_name]
                if field.__class__.__name__ in ("ManyToManyField",):
                    # Handle M2M separately
                    continue
                ops.append(AddField(model_name=table_name, field=field))
            
            # Removed columns -> DropField (careful: don't drop PKs)
            for col_name in db_col_names - model_col_names:
                # Verify it's not a managed FK constraint we should clean up
                ops.append(DropField(model_name=table_name, field_name=col_name))
            
            # Changed columns -> AlterField
            for col_name in (db_col_names & model_col_names):
                db_col = db_columns[col_name]
                model_field = model_cls._meta.fields[col_name]
                model_def = self._field_to_column_def(model_field)
                
                if self._column_changed(db_col, model_def):
                    ops.append(AlterField(model_name=table_name, field=model_field))
            
            # Index differences - simplified: check Meta.indexes
            model_indexes = getattr(model_cls._meta, "indexes", [])
            db_indexes = db_schema[table_name].get("indexes", [])
            # TODO: proper index diff
            
        # Check for tables in DB not in models -> DeleteModel (with caution)
        db_tables = set(db_schema.keys())
        for table in db_tables - processed_tables:
            # Only if table wasn't manually created
            pass  # skip auto-deletion for safety
            
        return ops

    def _column_changed(self, db_col: Dict[str, Any], model_def: Dict[str, Any]) -> bool:
        """Compare DB column metadata to model definition."""
        # Compare type, null, default, unique, auto_increment
        checks = [
            ("type", self._normalize_type(db_col["type"], db_col.get("primary_key", False))),
            ("null", db_col["null"]),
            ("default", db_col.get("default")),
            ("unique", db_col.get("unique", False)),
            ("primary_key", db_col.get("primary_key", False)),
        ]
        
        model_type = model_def.get("type")
        is_pk = model_def.get("primary_key", False)
        
        for attr, db_val in checks:
            model_val = model_def.get(attr)
            if attr == "type":
                model_val = self._normalize_type(model_val, is_pk)
            if db_val != model_val:
                logger.debug(f"Column {model_def['name']} changed: {attr} db={db_val} model={model_val}")
                return True
        return False

    def _normalize_type(self, type_str: Optional[str], is_pk: bool) -> str:
        """Normalize type strings across different backends."""
        if type_str is None:
            return "TEXT"
        t = type_str.upper()
        # Normalize integer types
        if "INT" in t:
            if is_pk and "AUTOINCREMENT" in t or t == "INTEGER PRIMARY KEY":
                return "INTEGER"
            return "INTEGER"
        if t.startswith("VARCHAR") or t.startswith("CHAR"):
            return t
        if t == "TEXT":
            return "TEXT"
        if t == "BOOLEAN" or t == "BOOL":
            return "BOOLEAN"
        if t.startswith("DECIMAL"):
            return t
        if t in ("FLOAT", "REAL", "DOUBLE"):
            return "FLOAT"
        if t == "DATETIME":
            return "DATETIME"
        if t == "DATE":
            return "DATE"
        if t == "TIME":
            return "TIME"
        if t.startswith("VARCHAR"):
            return t
        return t


def generate_migration_operations(connection: Any, engine: str) -> List[Any]:
    """Convenience function: return list of migration operations needed."""
    gen = SchemaDiffGenerator(connection, engine)
    return gen.generate_diff()
