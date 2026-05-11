"""Structured logging helpers for ORM operations."""

from __future__ import annotations

import logging


def get_logger(name: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name or "myorm")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
