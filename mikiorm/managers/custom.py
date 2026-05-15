"""Example extension point for custom manager behavior."""

from __future__ import annotations

from .base import Manager


class CustomManager(Manager):
    """Example manager for application-specific query helpers."""

    def published(self) -> "CustomManager":
        return self.filter(is_published=True)
