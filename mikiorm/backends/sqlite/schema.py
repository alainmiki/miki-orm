"""SQLite-specific schema editor.

The heavy lifting (field→SQL mapping, CREATE TABLE building) lives in
:mod:`mikiorm.backends.base.schema_editor`; this file only carries
SQLite-specific quirks such as the limited ``ALTER TABLE`` semantics.
"""

from __future__ import annotations

from ..base.dialect import Dialect
from ..base.schema_editor import SchemaEditor


class DatabaseSchemaEditor(SchemaEditor):
    """SQLite flavour of :class:`SchemaEditor`."""

    def __init__(self, connection, collect_sql: bool = False) -> None:
        super().__init__(connection, dialect=Dialect.SQLITE, collect_sql=collect_sql)


__all__ = ["DatabaseSchemaEditor"]
