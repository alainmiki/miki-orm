"""Tests for CLI infrastructure and configuration management.

Validates:
- Configuration loading from YAML/TOML
- Configuration validation
- Environment variable substitution
- Command group management
- CLI manager functionality
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from mikiorm.cli.infrastructure import (
    ConfigFormat,
    CLIConfig,
    ConfigValidator,
    ConfigLoader,
    CommandGroup,
    CLIManager,
)


class TestCLIConfig:
    """Tests for CLIConfig dataclass."""
    
    def test_initialization_defaults(self):
        """Test CLIConfig initialization with defaults."""
        config = CLIConfig()
        assert config.settings_module is None
        assert config.migrations_dir == "migrations"
        assert config.models_paths == []
        assert config.databases == {}
        assert config.logging_level == "INFO"
        assert config.verbose is False
    
    def test_initialization_with_values(self):
        """Test CLIConfig initialization with values."""
        config = CLIConfig(
            settings_module="myapp.settings",
            migrations_dir="db/migrations",
            models_paths=["myapp/models"],
            logging_level="DEBUG",
            verbose=True,
        )
        assert config.settings_module == "myapp.settings"
        assert config.migrations_dir == "db/migrations"
        assert config.models_paths == ["myapp/models"]
        assert config.logging_level == "DEBUG"
        assert config.verbose is True
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = CLIConfig(
            settings_module="settings",
            logging_level="DEBUG"
        )
        config_dict = config.to_dict()
        
        assert config_dict["settings_module"] == "settings"
        assert config_dict["logging_level"] == "DEBUG"
        assert isinstance(config_dict["models_paths"], list)
        assert isinstance(config_dict["databases"], dict)


class TestConfigValidator:
    """Tests for configuration validation."""
    
    def test_validate_required_fields(self):
        """Test validation of required fields."""
        config = {}
        is_valid, errors = ConfigValidator.validate(config)
        
        assert not is_valid
        assert any("settings_module" in error for error in errors)
    
    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        config = {
            "settings_module": "myapp.settings",
            "migrations_dir": "migrations",
            "logging_level": "INFO",
        }
        is_valid, errors = ConfigValidator.validate(config)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_invalid_logging_level(self):
        """Test validation of invalid logging level."""
        config = {
            "settings_module": "settings",
            "logging_level": "INVALID",
        }
        is_valid, errors = ConfigValidator.validate(config)
        
        assert not is_valid
        assert any("logging_level" in error.lower() for error in errors)
    
    def test_validate_invalid_models_paths_type(self):
        """Test validation of invalid models_paths type."""
        config = {
            "settings_module": "settings",
            "models_paths": "not_a_list",
        }
        is_valid, errors = ConfigValidator.validate(config)
        
        assert not is_valid
        assert any("models_paths" in error.lower() for error in errors)
    
    def test_validate_invalid_databases_type(self):
        """Test validation of invalid databases type."""
        config = {
            "settings_module": "settings",
            "databases": ["not", "a", "dict"],
        }
        is_valid, errors = ConfigValidator.validate(config)
        
        assert not is_valid
        assert any("databases" in error.lower() for error in errors)


class TestConfigLoader:
    """Tests for configuration loading."""
    
    def test_load_yaml(self):
        """Test loading YAML configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.yaml"
            config_path.write_text("""
settings_module: myapp.settings
migrations_dir: db/migrations
models_paths:
  - myapp/models
logging_level: DEBUG
verbose: true
""")
            
            config = ConfigLoader.load_from_yaml(config_path)
            
            assert config["settings_module"] == "myapp.settings"
            assert config["migrations_dir"] == "db/migrations"
            assert config["models_paths"] == ["myapp/models"]
            assert config["logging_level"] == "DEBUG"
            assert config["verbose"] is True
    
    def test_load_yaml_not_found(self):
        """Test loading non-existent YAML file."""
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load_from_yaml("/nonexistent/config.yaml")
    
    def test_load_toml(self):
        """Test loading TOML configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.toml"
            config_path.write_text("""
settings_module = "myapp.settings"
migrations_dir = "db/migrations"
models_paths = ["myapp/models"]
logging_level = "DEBUG"
verbose = true
""")
            
            config = ConfigLoader.load_from_toml(config_path)
            
            assert config["settings_module"] == "myapp.settings"
            assert config["migrations_dir"] == "db/migrations"
            assert config["logging_level"] == "DEBUG"
    
    def test_load_pyproject_toml(self):
        """Test loading config from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject_path = Path(tmpdir) / "pyproject.toml"
            pyproject_path.write_text("""
[tool.mikiorm]
settings_module = "myapp.settings"
migrations_dir = "db/migrations"
logging_level = "DEBUG"
""")
            
            config = ConfigLoader.load_from_pyproject(pyproject_path)
            
            assert config["settings_module"] == "myapp.settings"
            assert config["migrations_dir"] == "db/migrations"
    
    def test_load_pyproject_not_found(self):
        """Test loading non-existent pyproject.toml."""
        config = ConfigLoader.load_from_pyproject("/nonexistent/pyproject.toml")
        assert config == {}
    
    def test_discover_config_file_yaml(self):
        """Test discovering YAML config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.yaml"
            config_path.write_text("settings_module: test")
            
            found = ConfigLoader.discover_config_file(tmpdir)
            assert found == config_path
    
    def test_discover_config_file_toml(self):
        """Test discovering TOML config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.toml"
            config_path.write_text("settings_module = 'test'")
            
            found = ConfigLoader.discover_config_file(tmpdir)
            assert found == config_path
    
    def test_discover_config_file_not_found(self):
        """Test config discovery when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            found = ConfigLoader.discover_config_file(tmpdir)
            assert found is None
    
    def test_env_substitution_simple(self):
        """Test environment variable substitution."""
        os.environ["TEST_VAR"] = "test_value"
        
        config = {"key": "${TEST_VAR}"}
        result = ConfigLoader._apply_env_substitution(config)
        
        assert result["key"] == "test_value"
    
    def test_env_substitution_with_default(self):
        """Test environment variable substitution with default."""
        config = {"key": "${NONEXISTENT_VAR:default_value}"}
        result = ConfigLoader._apply_env_substitution(config)
        
        assert result["key"] == "default_value"
    
    def test_env_substitution_nested(self):
        """Test environment variable substitution in nested config."""
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        
        config = {
            "databases": {
                "default": {
                    "host": "${DB_HOST}",
                    "port": "${DB_PORT}",
                }
            }
        }
        result = ConfigLoader._apply_env_substitution(config)
        
        assert result["databases"]["default"]["host"] == "localhost"
        assert result["databases"]["default"]["port"] == "5432"
    
    def test_env_substitution_in_list(self):
        """Test environment variable substitution in lists."""
        os.environ["MODEL_PATH"] = "myapp/models"
        
        config = {"models_paths": ["${MODEL_PATH}", "other/models"]}
        result = ConfigLoader._apply_env_substitution(config)
        
        assert result["models_paths"][0] == "myapp/models"
        assert result["models_paths"][1] == "other/models"
    
    def test_env_substitution_missing_var(self):
        """Test error when required environment variable missing."""
        config = {"key": "${MISSING_VAR}"}
        
        with pytest.raises(ValueError):
            ConfigLoader._apply_env_substitution(config)
    
    def test_load_with_discovery(self):
        """Test loading config with automatic discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.yaml"
            config_path.write_text("settings_module: myapp.settings")
            
            config = ConfigLoader.load(search_dirs=[tmpdir])
            
            assert config.settings_module == "myapp.settings"


class TestCommandGroup:
    """Tests for command groups."""
    
    def test_create_group(self):
        """Test creating command group."""
        group = CommandGroup("migrations", "Migration commands")
        
        assert group.name == "migrations"
        assert group.description == "Migration commands"
        assert len(group.commands) == 0
    
    def test_register_command(self):
        """Test registering command."""
        group = CommandGroup("test", "Test commands")
        handler = Mock()
        
        group.register("list", handler)
        
        assert "list" in group.commands
        assert group.commands["list"] is handler
    
    def test_get_command(self):
        """Test getting command."""
        group = CommandGroup("test", "Test")
        handler = Mock()
        
        group.register("cmd", handler)
        
        retrieved = group.get_command("cmd")
        assert retrieved is handler
    
    def test_get_command_not_found(self):
        """Test getting non-existent command."""
        group = CommandGroup("test", "Test")
        
        retrieved = group.get_command("nonexistent")
        assert retrieved is None
    
    def test_list_commands(self):
        """Test listing all commands."""
        group = CommandGroup("test", "Test")
        handler1 = Mock()
        handler2 = Mock()
        
        group.register("cmd1", handler1)
        group.register("cmd2", handler2)
        
        commands = group.list_commands()
        
        assert len(commands) == 2
        assert "cmd1" in commands
        assert "cmd2" in commands


class TestCLIManager:
    """Tests for CLI manager."""
    
    def test_create_manager(self):
        """Test creating CLI manager."""
        manager = CLIManager()
        
        assert len(manager.groups) == 0
        assert manager.config is None
    
    def test_create_group(self):
        """Test creating command group."""
        manager = CLIManager()
        
        group = manager.create_group("migrations", "Migration commands")
        
        assert "migrations" in manager.groups
        assert group.name == "migrations"
    
    def test_get_group(self):
        """Test getting command group."""
        manager = CLIManager()
        group = manager.create_group("test", "Test")
        
        retrieved = manager.get_group("test")
        assert retrieved is group
    
    def test_get_group_not_found(self):
        """Test getting non-existent group."""
        manager = CLIManager()
        
        retrieved = manager.get_group("nonexistent")
        assert retrieved is None
    
    def test_register_command(self):
        """Test registering command."""
        manager = CLIManager()
        manager.create_group("migrations", "Migration commands")
        handler = Mock()
        
        manager.register_command("migrations", "makemigrations", handler)
        
        group = manager.get_group("migrations")
        assert group.get_command("makemigrations") is handler
    
    def test_register_command_group_not_found(self):
        """Test registering command in non-existent group."""
        manager = CLIManager()
        
        with pytest.raises(ValueError):
            manager.register_command("nonexistent", "cmd", Mock())
    
    def test_load_configuration(self):
        """Test loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.yaml"
            config_path.write_text("""
settings_module: myapp.settings
migrations_dir: db/migrations
logging_level: DEBUG
""")
            
            manager = CLIManager()
            config = manager.load_configuration(str(config_path))
            
            assert config.settings_module == "myapp.settings"
            assert config.migrations_dir == "db/migrations"
            assert manager.config is config
    
    def test_apply_logging_config(self):
        """Test applying logging configuration."""
        manager = CLIManager()
        manager.config = CLIConfig(
            settings_module="settings",
            logging_level="DEBUG"
        )
        
        # Should not raise
        manager.apply_logging_config()


class TestConfigLoaderIntegration:
    """Integration tests for configuration loading."""
    
    def test_load_and_validate_complete_config(self):
        """Test loading and validating complete configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "mikiorm.yaml"
            config_path.write_text("""
settings_module: myapp.settings
migrations_dir: db/migrations
models_paths:
  - myapp/models
  - other/models
logging_level: INFO
verbose: false

databases:
  default:
    engine: postgresql
    host: localhost
    port: 5432
""")
            
            config = ConfigLoader.load(str(config_path))
            
            assert config.settings_module == "myapp.settings"
            assert config.migrations_dir == "db/migrations"
            assert len(config.models_paths) == 2
            assert "default" in config.databases
            assert config.verbose is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
