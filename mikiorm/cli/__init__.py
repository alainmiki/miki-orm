"""CLI management package for mikiorm.

Provides:
- Infrastructure for command groups and managers
- Configuration loading with YAML/TOML support
- Environment variable substitution
- CLI utilities and helpers
"""

from .infrastructure import (
    ConfigFormat,
    CLIConfig,
    ConfigValidator,
    ConfigLoader,
    CommandGroup,
    CLIManager,
)
from .cli import main

__all__ = [
    "ConfigFormat",
    "CLIConfig",
    "ConfigValidator",
    "ConfigLoader",
    "CommandGroup",
    "CLIManager",
    "main",
]
