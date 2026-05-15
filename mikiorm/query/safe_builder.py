"""Compatibility shim: dialect-aware SQL builder lives in backends.base.

Importing from here still works for historical callers but the canonical
home is :mod:`mikiorm.backends.base.dialect`.
"""

from ..backends.base.dialect import Dialect, SafeBuilder, get_safe_builder

__all__ = ["Dialect", "SafeBuilder", "get_safe_builder"]
