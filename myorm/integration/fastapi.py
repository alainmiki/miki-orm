"""FastAPI adapter utilities."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


class FastAPIIntegration:
    def __init__(self, app: FastAPI, db_config: dict[str, Any]) -> None:
        self.app = app
        self.db_config = db_config

    def init_app(self) -> None:
        self.app.state.miki_orm = self.db_config
