"""Relationship field definitions like ForeignKey and ManyToMany."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from .fields import Field


@dataclass
class ForeignKey(Field):
    to: str | Type[Any] = ""
    related_name: str | None = None


@dataclass
class OneToOneField(ForeignKey):
    pass


@dataclass
class ManyToManyField(Field):
    to: str | Type[Any] = ""
    related_name: str | None = None
