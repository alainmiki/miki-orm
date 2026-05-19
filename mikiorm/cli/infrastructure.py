"""Enhanced CLI infrastructure with command groups and configuration management.

Features:
- Command groups for better organization
- Configuration validation and loading
- YAML/TOML configuration file support
- Environment variable substitution
- Better error handling and formatting
- Config file discovery (mikiorm.yaml, mikiorm.toml, pyproject.toml)
- Validation of configuration schema
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import importlib

logger = logging.getLogger(__name__)


class ConfigFormat(Enum):
    """Supported configuration file formats."""
    YAML = "yaml"
    TOML = "toml"
    PYTHON = "python"


@dataclass
class CLIConfig:
    """CLI configuration container."""
    settings_module: Optional[str] = None
    migrations_dir: str = "migrations"
    models_paths: List[str] = None
    databases: Dict[str, Dict[str, Any]] = None
    logging_level: str = "INFO"
    verbose: bool = False
    
    def __post_init__(self):
        if self.models_paths is None:
            self.models_paths = []
        if self.databases is None:
            self.databases = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "settings_module": self.settings_module,
            "migrations_dir": self.migrations_dir,
            "models_paths": self.models_paths,
            "databases": self.databases,
            "logging_level": self.logging_level,
            "verbose": self.verbose,
        }


class ConfigValidator:
    """Validates CLI configuration."""
    
    REQUIRED_FIELDS = {"settings_module"}
    OPTIONAL_FIELDS = {
        "migrations_dir",
        "models_paths",
        "databases",
        "logging_level",
        "verbose",
    }
    
    @staticmethod
    def validate(config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate configuration dictionary.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check required fields
        for field in ConfigValidator.REQUIRED_FIELDS:
            if field not in config or not config[field]:
                errors.append(f"Missing required field: {field}")
        
        # Validate field types
        if "logging_level" in config:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if config["logging_level"].upper() not in valid_levels:
                errors.append(
                    f"Invalid logging level: {config['logging_level']}. "
                    f"Must be one of: {', '.join(valid_levels)}"
                )
        
        if "models_paths" in config:
            if not isinstance(config["models_paths"], list):
                errors.append("models_paths must be a list")
        
        if "databases" in config:
            if not isinstance(config["databases"], dict):
                errors.append("databases must be a dictionary")
        
        return len(errors) == 0, errors


class ConfigLoader:
    """Load CLI configuration from various sources."""
    
    @staticmethod
    def load_from_yaml(path: str | Path) -> Dict[str, Any]:
        """Load configuration from YAML file.
        
        Args:
            path: Path to YAML file
            
        Returns:
            Configuration dictionary
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for YAML configuration support. Install with: pip install pyyaml")
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path) as f:
            config = yaml.safe_load(f)
        
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def load_from_toml(path: str | Path) -> Dict[str, Any]:
        """Load configuration from TOML file.
        
        Args:
            path: Path to TOML file
            
        Returns:
            Configuration dictionary
        """
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                raise ImportError(
                    "TOML support requires Python 3.11+ or tomli. "
                    "Install with: pip install tomli"
                )
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "rb") as f:
            config = tomllib.load(f)
        
        # Extract mikiorm section if present
        if "tool" in config and "mikiorm" in config["tool"]:
            config = config["tool"]["mikiorm"]
        elif "mikiorm" in config:
            config = config["mikiorm"]
        
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def load_from_pyproject(path: str | Path = "pyproject.toml") -> Dict[str, Any]:
        """Load mikiorm config from pyproject.toml.
        
        Args:
            path: Path to pyproject.toml
            
        Returns:
            Configuration dictionary
        """
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return {}
        
        path = Path(path)
        if not path.exists():
            return {}
        
        with open(path, "rb") as f:
            pyproject = tomllib.load(f)
        
        # Look for tool.mikiorm section
        if "tool" not in pyproject or "mikiorm" not in pyproject["tool"]:
            return {}
        
        config = pyproject["tool"]["mikiorm"]
        return ConfigLoader._apply_env_substitution(config)
    
    @staticmethod
    def discover_config_file(
        start_dir: str | Path = ".",
        search_names: List[str] = None,
    ) -> Optional[Path]:
        """Discover configuration file in directory hierarchy.
        
        Args:
            start_dir: Directory to start search from
            search_names: Names to search for (default: ["mikiorm.yaml", "mikiorm.toml"])
            
        Returns:
            Path to config file if found, None otherwise
        """
        if search_names is None:
            search_names = ["mikiorm.yaml", "mikiorm.toml", "pyproject.toml"]
        
        current = Path(start_dir).resolve()
        max_depth = 10  # Prevent infinite loops
        depth = 0
        
        while depth < max_depth:
            for name in search_names:
                config_path = current / name
                if config_path.exists():
                    logger.debug(f"Found config file: {config_path}")
                    return config_path
            
            # Move up to parent directory
            parent = current.parent
            if parent == current:  # Reached root
                break
            
            current = parent
            depth += 1
        
        return None
    
    @staticmethod
    def _apply_env_substitution(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable substitution in configuration.
        
        Supports ${VAR_NAME} or ${VAR_NAME:default_value} syntax.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Configuration with environment variables substituted
        """
        import re
        
        def substitute_value(value):
            if isinstance(value, str):
                def replace_env_var(match):
                    var_spec = match.group(1)
                    if ":" in var_spec:
                        var_name, default_value = var_spec.split(":", 1)
                    else:
                        var_name = var_spec
                        default_value = None
                    
                    result = os.environ.get(var_name, default_value)
                    if result is None:
                        raise ValueError(
                            f"Environment variable not found: {var_name}"
                        )
                    return result
                
                # Replace ${VAR} or ${VAR:default} patterns
                return re.sub(r'\$\{([^}]+)\}', replace_env_var, value)
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(v) for v in value]
            
            return value
        
        return substitute_value(config)
    
    @staticmethod
    def load(
        config_file: Optional[str | Path] = None,
        search_dirs: List[str | Path] = None,
    ) -> CLIConfig:
        """Load CLI configuration from file or discover.
        
        Args:
            config_file: Explicit config file path
            search_dirs: Directories to search for config file
            
        Returns:
            CLIConfig instance
        """
        config_dict = {}
        config_path = None
        
        if config_file:
            config_path = Path(config_file)
        elif search_dirs:
            for search_dir in search_dirs:
                config_path = ConfigLoader.discover_config_file(search_dir)
                if config_path:
                    break
        else:
            config_path = ConfigLoader.discover_config_file()
        
        if config_path:
            logger.info(f"Loading configuration from: {config_path}")
            if config_path.suffix == ".yaml" or config_path.suffix == ".yml":
                config_dict = ConfigLoader.load_from_yaml(config_path)
            elif config_path.suffix == ".toml":
                if config_path.name == "pyproject.toml":
                    config_dict = ConfigLoader.load_from_pyproject(config_path)
                else:
                    config_dict = ConfigLoader.load_from_toml(config_path)
        
        # Validate configuration
        is_valid, errors = ConfigValidator.validate(config_dict)
        if not is_valid:
            logger.warning("Configuration validation failed:")
            for error in errors:
                logger.warning(f"  - {error}")
        
        # Build CLI config
        return CLIConfig(
            settings_module=config_dict.get("settings_module"),
            migrations_dir=config_dict.get("migrations_dir", "migrations"),
            models_paths=config_dict.get("models_paths", []),
            databases=config_dict.get("databases", {}),
            logging_level=config_dict.get("logging_level", "INFO"),
            verbose=config_dict.get("verbose", False),
        )


class CommandGroup:
    """Group of related CLI commands."""
    
    def __init__(self, name: str, description: str):
        """Initialize command group.
        
        Args:
            name: Group name
            description: Group description
        """
        self.name = name
        self.description = description
        self.commands: Dict[str, Callable] = {}
    
    def register(self, command_name: str, handler: Callable) -> None:
        """Register a command handler.
        
        Args:
            command_name: Command name
            handler: Callable command handler
        """
        self.commands[command_name] = handler
    
    def get_command(self, name: str) -> Optional[Callable]:
        """Get command handler by name.
        
        Args:
            name: Command name
            
        Returns:
            Command handler or None if not found
        """
        return self.commands.get(name)
    
    def list_commands(self) -> Dict[str, Callable]:
        """List all commands in group.
        
        Returns:
            Dictionary of command_name -> handler
        """
        return self.commands.copy()


class CLIManager:
    """Manages CLI command groups and execution."""
    
    def __init__(self):
        """Initialize CLI manager."""
        self.groups: Dict[str, CommandGroup] = {}
        self.config: Optional[CLIConfig] = None
    
    def create_group(self, name: str, description: str) -> CommandGroup:
        """Create a new command group.
        
        Args:
            name: Group name
            description: Group description
            
        Returns:
            CommandGroup instance
        """
        group = CommandGroup(name, description)
        self.groups[name] = group
        return group
    
    def get_group(self, name: str) -> Optional[CommandGroup]:
        """Get command group by name.
        
        Args:
            name: Group name
            
        Returns:
            CommandGroup or None if not found
        """
        return self.groups.get(name)
    
    def register_command(
        self,
        group_name: str,
        command_name: str,
        handler: Callable,
        description: str = "",
    ) -> None:
        """Register a command in a group.
        
        Args:
            group_name: Name of group to add to
            command_name: Command name
            handler: Command handler function
            description: Command description
        """
        if group_name not in self.groups:
            raise ValueError(f"Group not found: {group_name}")
        
        group = self.groups[group_name]
        group.register(command_name, handler)
    
    def load_configuration(self, config_file: Optional[str] = None) -> CLIConfig:
        """Load CLI configuration.
        
        Args:
            config_file: Optional config file path
            
        Returns:
            CLIConfig instance
        """
        self.config = ConfigLoader.load(config_file)
        return self.config
    
    def apply_logging_config(self) -> None:
        """Apply logging configuration."""
        if not self.config:
            return
        
        level = getattr(logging, self.config.logging_level.upper(), logging.INFO)
        logging.basicConfig(level=level)


__all__ = [
    "ConfigFormat",
    "CLIConfig",
    "ConfigValidator",
    "ConfigLoader",
    "CommandGroup",
    "CLIManager",
]
