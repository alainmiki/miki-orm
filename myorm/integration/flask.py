"""Flask integration helpers for miki-orm."""

from __future__ import annotations

from typing import Any

from flask import Flask


class FlaskIntegration:
    def __init__(self, app: Flask, db_config: dict[str, Any]) -> None:
        self.app = app
        self.db_config = db_config

    def init_app(self) -> None:
        self.app.config.setdefault("MIKI_ORM_DATABASES", self.db_config)
