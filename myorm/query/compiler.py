"""SQL compiler and dialect adaptation."""

from __future__ import annotations

from typing import Any, Iterable, Tuple


class Compiler:
    """Compile a query AST or SQL template to backend-specific SQL."""

    def compile(self, sql: str, params: Iterable[Any], dialect: str = "sqlite") -> tuple[str, tuple[Any, ...]]:
        if dialect == "postgres":
            return self._compile_postgres(sql, params)
        if dialect == "mysql":
            return self._compile_mysql(sql, params)
        return sql, tuple(params)

    def _compile_postgres(self, sql: str, params: Iterable[Any]) -> tuple[str, tuple[Any, ...]]:
        placeholders = []
        for i, _ in enumerate(params, 1):
            placeholders.append(f"${i}")
        compiled_sql = sql.replace("%s", "%s")
        return compiled_sql, tuple(params)

    def _compile_mysql(self, sql: str, params: Iterable[Any]) -> tuple[str, tuple[Any, ...]]:
        return sql, tuple(params)
