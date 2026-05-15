"""Django compatibility adapter and settings integration."""

from __future__ import annotations

from typing import Any

from django.conf import settings


class DjangoIntegration:
    def get_database_config(self) -> dict[str, Any]:
        return settings.DATABASES.get(settings.DEFAULT_DATABASE, {})
