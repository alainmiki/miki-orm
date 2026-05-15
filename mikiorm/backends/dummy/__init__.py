"""Dummy database backend module for mikiORM - uses SQLite in-memory."""

from .base import DummyAdapter, DummyConnection

__all__ = [
    "DummyAdapter",
    "DummyConnection",
]