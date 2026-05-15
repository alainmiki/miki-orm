"""Pyramid integration utilities."""

from __future__ import annotations

from typing import Any

from pyramid.config import Configurator


class PyramidIntegration:
    def __init__(self, config: Configurator, db_config: dict[str, Any]) -> None:
        self.config = config
        self.db_config = db_config

    def init_app(self) -> None:
        self.config.registry.settings.setdefault("miki_orm.databases", self.db_config)
