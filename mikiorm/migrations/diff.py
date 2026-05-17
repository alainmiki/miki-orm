"""Schema diff generation: compare model definitions to database schema."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .schema import get_introspector
from ..backends.base.dialect import get_safe_builder
from ..models.registry import ModelRegistry
from ..models.fields import (
    AutoField, BigAutoField, SmallAutoField,
    IntegerField, BigIntegerField, SmallIntegerField,
    PositiveIntegerField, PositiveSmallIntegerField,
    Field, # Import Field for type checking
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
from ..backends.base.schema_editor import field_to_sql_type # Import canonical helper

logger = logging.getLogger(__name__)


class SchemaDiffGenerator:
    """Generates migration operations by comparing model registry to DB schema."""

    def __init__(self, connection: Any, engine: str) -> None:
        self.connection = connection
        self.engine = engine
        self.app_labels: list[str] | None = None  # Added to store app_labels
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
        sql_type = self._sql_type_for_field(field)

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

    def _sql_type_for_field(self, field: Any) -> str:
        """Get SQL type string for a field using the canonical helper."""
        # The builder's dialect is available via self.builder.dialect
        return field_to_sql_type(field, self.builder.dialect)

    def _find_renamed_field(self, removed_db_col: Dict[str, Any], added_model_fields: Dict[str, Dict[str, Any]]) -> Optional[str]:
        """
        Attempts to find a matching added model field that could be a rename of the removed DB column.
        This is a heuristic and can be improved.
        """
        removed_col_name = removed_db_col["name"]
        removed_col_type = self._normalize_type(removed_db_col["type"], removed_db_col["primary_key"])
        removed_col_null = removed_db_col["null"]
        removed_col_pk = removed_db_col["primary_key"]

        for added_field_name, added_field_def in added_model_fields.items():
            added_col_type = self._normalize_type(added_field_def["type"], added_field_def["primary_key"])
            added_col_null = added_field_def["null"]
            added_col_pk = added_field_def["primary_key"]

            # Simple heuristic: types must be compatible, nullability must match, PK status must match.
            # More advanced: check for similar names, or allow type changes if compatible.
            if (removed_col_type == added_col_type and
                removed_col_null == added_col_null and
                removed_col_pk == added_col_pk):
                # This is a strong candidate for a rename.
                # We could add a name similarity check here, but for now, this is a basic match.
                return added_field_name
        return None

    def generate_diff(self) -> List[Any]:
        """Compare registered models to DB schema and return list of operations.

        Args:
            app_labels: Optional list of model names to filter by.
        """
        from .operations import (
            CreateTable,
            AddField,
            AlterField,
            DropField,
            CreateIndex,
            DropIndex,
            DeleteModel,
            RenameField, # Import RenameField
        )

        ops = []
        db_schema = self._get_db_schema()
        model_classes = ModelRegistry.all_models()

        if not model_classes:
            logger.debug("No models found in Registry during diff.")
            return []

        # Filter models if app_labels (interpreted as model names) are provided
        if self.app_labels:
            model_classes = [m for m in model_classes if m.__name__ in self.app_labels]

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
            
            # Identify removed and added fields
            removed_db_cols = {name: col_def for name, col_def in db_columns.items() if name not in model_fields}
            added_model_fields = {name: field_def for name, field_def in model_fields.items() if name not in db_columns}

            # Attempt to detect renames
            renamed_pairs: List[Tuple[str, str]] = [] # (old_name, new_name)
            matched_added_fields = set()

            for removed_col_name, removed_col_def in removed_db_cols.items():
                matched_new_field_name = self._find_renamed_field(removed_col_def, added_model_fields)
                if matched_new_field_name and matched_new_field_name not in matched_added_fields:
                    renamed_pairs.append((removed_col_name, matched_new_field_name))
                    matched_added_fields.add(matched_new_field_name)
                    logger.info(f"Detected potential rename: {table_name}.{removed_col_name} -> {table_name}.{matched_new_field_name}")
            
            # Process renames first
            for old_name, new_name in renamed_pairs:
                ops.append(RenameField(model_name=table_name, old_name=old_name, new_name=new_name))
                # Remove these from further processing as they are handled
                del removed_db_cols[old_name]
                del added_model_fields[new_name]

            # Now handle remaining AddField and DropField
            # New columns -> AddField
            for col_name, field_def in added_model_fields.items(): # Iterate over remaining added fields
                field = model_cls._meta.fields[col_name]
                if isinstance(field, ManyToManyField): # Use isinstance for proper type checking
                    continue
                ops.append(AddField(model_name=table_name, field=field))

            # Removed columns -> DropField
            for col_name, col_def in removed_db_cols.items(): # Iterate over remaining removed columns
                ops.append(DropField(model_name=table_name, field_name=col_name))

            # Changed columns -> AlterField (for fields common to both)
            for col_name in (set(db_columns.keys()) & set(model_fields.keys())) - matched_added_fields: # Exclude renamed fields
                db_col = db_columns[col_name]
                model_field = model_cls._meta.fields[col_name]
                model_def = self._field_to_column_def(model_field)

                if self._column_changed(db_col, model_def):
                    # Provide the old_field state by reconstructing it from DB metadata
                    old_field = self._reconstruct_field(db_col, model_field)
                    ops.append(AlterField(model_name=table_name, field=model_field, old_field=old_field))

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

    def _reconstruct_field(self, db_col: Dict[str, Any], current_field: Any) -> Any:
        """Reconstruct a Field instance representing the state currently in the DB."""
        from copy import copy
        old_field = copy(current_field)
        old_field.null = db_col["null"]
        old_field.primary_key = db_col["primary_key"]
        old_field.default = db_col.get("default")
        if "unique" in db_col:
            old_field.unique = db_col["unique"]
        return old_field

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


def generate_migration_operations(
    connection: Any, engine: str, app_labels: list[str] | None = None
) -> List[Any]:
    """Convenience function: return list of migration operations needed."""
    gen = SchemaDiffGenerator(connection, engine)
    gen.app_labels = app_labels  # Pass app_labels to the generator
    return gen.generate_diff()
