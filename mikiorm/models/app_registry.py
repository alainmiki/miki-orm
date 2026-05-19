"""Enhanced app-based model registration system with app namespacing.

Supports:
- Multiple apps with separate model namespaces
- Duplicate model names across different apps
- Auto-discovery of models.py files
- App configuration with migrations tracking
- Model resolution: app.ModelName or just ModelName (if unique)

Example:
    from mikiorm.models.app_registry import AppRegistry
    
    registry = AppRegistry()
    registry.register_app('users', base_path='./apps/users')
    registry.register_app('products', base_path='./apps/products')
    registry.auto_discover()
    
    # Access models
    UserModel = registry.get_model('users.User')  # Fully qualified
    User = registry.get_model('User')  # If unique
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, Tuple

if TYPE_CHECKING:
    from .base import Model


class AppConfig:
    """Configuration for a registered app."""
    
    def __init__(
        self,
        app_name: str,
        base_path: str,
        module_path: Optional[str] = None,
        verbose_name: Optional[str] = None
    ):
        """Initialize app configuration.
        
        Args:
            app_name: Name of the app (e.g., 'users', 'products')
            base_path: File system path to the app
            module_path: Python module path (auto-determined if not provided)
            verbose_name: Human-readable name for the app
        """
        self.app_name = app_name
        self.base_path = Path(base_path).resolve()
        self.module_path = module_path or f"apps.{app_name}"
        self.verbose_name = verbose_name or app_name.capitalize()
        self.models: Dict[str, Type[Model]] = {}
        self._discovered = False
    
    def get_models_path(self) -> Path:
        """Get path to models.py file."""
        return self.base_path / "models.py"
    
    def get_migrations_path(self) -> Path:
        """Get path to migrations directory."""
        return self.base_path / "migrations"
    
    def has_models(self) -> bool:
        """Check if app has models.py file."""
        return self.get_models_path().exists()
    
    def is_discovered(self) -> bool:
        """Check if models have been discovered."""
        return self._discovered
    
    def __repr__(self) -> str:
        """String representation."""
        return f"AppConfig({self.app_name}, path={self.base_path})"


class AppRegistry:
    """App-based model registry supporting namespacing and auto-discovery."""
    
    def __init__(self):
        """Initialize app registry."""
        self._apps: Dict[str, AppConfig] = {}
        self._models_by_qualified_name: Dict[str, Type[Model]] = {}  # 'app.Model' -> Model
        self._models_by_name: Dict[str, List[Type[Model]]] = {}  # 'Model' -> [Model, ...]
        self._global_registry: Dict[str, Type[Model]] = {}  # For backward compat
    
    def register_app(
        self,
        app_name: str,
        base_path: str,
        module_path: Optional[str] = None,
        verbose_name: Optional[str] = None
    ) -> AppConfig:
        """Register an app with models.
        
        Args:
            app_name: Name of app (must be unique)
            base_path: Path to app directory
            module_path: Python module path (optional)
            verbose_name: Human-readable name (optional)
            
        Returns:
            AppConfig instance
            
        Raises:
            ValueError: If app already registered or app_name invalid
        """
        if app_name in self._apps:
            raise ValueError(f"App '{app_name}' already registered")
        
        if not app_name.isidentifier():
            raise ValueError(f"Invalid app name: '{app_name}' (must be valid identifier)")
        
        base_path_obj = Path(base_path).resolve()
        if not base_path_obj.exists():
            raise ValueError(f"App path does not exist: {base_path}")
        
        app_config = AppConfig(app_name, base_path, module_path, verbose_name)
        self._apps[app_name] = app_config
        
        return app_config
    
    def unregister_app(self, app_name: str) -> None:
        """Unregister an app and remove its models.
        
        Args:
            app_name: Name of app to unregister
        """
        if app_name not in self._apps:
            return
        
        app = self._apps[app_name]
        
        # Remove from qualified names
        for model_name in list(app.models.keys()):
            qualified_name = f"{app_name}.{model_name}"
            if qualified_name in self._models_by_qualified_name:
                del self._models_by_qualified_name[qualified_name]
        
        # Remove from name index
        for model_name in app.models.keys():
            if model_name in self._models_by_name:
                self._models_by_name[model_name] = [
                    m for m in self._models_by_name[model_name]
                    if m not in app.models.values()
                ]
                if not self._models_by_name[model_name]:
                    del self._models_by_name[model_name]
        
        del self._apps[app_name]
    
    def auto_discover(self, verbose: bool = False) -> int:
        """Auto-discover models in all registered apps.
        
        Scans each app's models.py file and registers all Model subclasses.
        
        Args:
            verbose: Print discovery information
            
        Returns:
            Number of models discovered
        """
        total_discovered = 0
        
        for app_name, app_config in self._apps.items():
            if app_config.is_discovered():
                continue
            
            if not app_config.has_models():
                if verbose:
                    print(f"App '{app_name}': No models.py found")
                continue
            
            try:
                discovered = self._discover_app_models(app_config, verbose)
                total_discovered += discovered
                app_config._discovered = True
                
                if verbose:
                    print(f"App '{app_name}': Discovered {discovered} model(s)")
            except Exception as e:
                print(f"Error discovering models in app '{app_name}': {e}")
        
        return total_discovered
    
    def _discover_app_models(self, app_config: AppConfig, verbose: bool = False) -> int:
        """Discover models in a specific app.
        
        Args:
            app_config: App configuration
            verbose: Print information
            
        Returns:
            Number of models discovered
        """
        from .base import Model
        
        models_file = app_config.get_models_path()
        
        # Create a module spec for dynamic import
        spec = importlib.util.spec_from_file_location(
            f"{app_config.module_path}.models",
            models_file
        )
        
        if not spec or not spec.loader:
            return 0
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        
        # Find all Model subclasses in the module
        discovered = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            # Check if it's a Model subclass (but not Model itself)
            if (isinstance(attr, type) and 
                issubclass(attr, Model) and 
                attr is not Model and
                attr.__module__ == module.__name__):
                
                self.register_model_in_app(
                    app_config.app_name,
                    attr,
                    verbose
                )
                discovered += 1
        
        return discovered
    
    def register_model_in_app(
        self,
        app_name: str,
        model: Type[Model],
        verbose: bool = False
    ) -> None:
        """Register a model in a specific app.
        
        Args:
            app_name: Name of app
            model: Model class to register
            verbose: Print information
            
        Raises:
            ValueError: If app not registered
        """
        if app_name not in self._apps:
            raise ValueError(f"App '{app_name}' not registered")
        
        app_config = self._apps[app_name]
        model_name = model.__name__
        
        # Store in app's models
        app_config.models[model_name] = model
        
        # Store in qualified name index
        qualified_name = f"{app_name}.{model_name}"
        self._models_by_qualified_name[qualified_name] = model
        
        # Store in name index (for ambiguity resolution)
        if model_name not in self._models_by_name:
            self._models_by_name[model_name] = []
        self._models_by_name[model_name].append(model)
        
        # Store in global registry (backward compat)
        if model_name in self._global_registry:
            # Name collision - store qualified version
            if model_name not in self._global_registry or self._global_registry[model_name] is model:
                pass  # Keep existing or update if same
        else:
            self._global_registry[model_name] = model
        
        if verbose:
            print(f"Registered: {qualified_name}")
    
    def get_app(self, app_name: str) -> Optional[AppConfig]:
        """Get an app by name.
        
        Args:
            app_name: Name of app
            
        Returns:
            AppConfig or None if not found
        """
        return self._apps.get(app_name)
    
    def get_model(self, model_path: str) -> Optional[Type[Model]]:
        """Get a model by name or qualified name.
        
        Resolution order:
        1. Qualified name: 'app.ModelName' - exact match
        2. Unique name: 'ModelName' - if only one exists
        3. Global registry: fallback for backward compatibility
        
        Args:
            model_path: Model name or 'app.ModelName'
            
        Returns:
            Model class or None if not found
            
        Raises:
            ValueError: If model name is ambiguous (multiple apps)
        """
        # Try qualified name first
        if '.' in model_path:
            return self._models_by_qualified_name.get(model_path)
        
        # Try unqualified name
        if model_path in self._models_by_name:
            candidates = self._models_by_name[model_path]
            if len(candidates) == 1:
                return candidates[0]
            elif len(candidates) > 1:
                raise ValueError(
                    f"Ambiguous model name '{model_path}'. Use qualified name: "
                    f"{', '.join(f'{self._find_app_for_model(m)}.{model_path}' for m in candidates)}"
                )
        
        # Fallback to global registry
        return self._global_registry.get(model_path)
    
    def _find_app_for_model(self, model: Type[Model]) -> Optional[str]:
        """Find which app a model belongs to.
        
        Args:
            model: Model class
            
        Returns:
            App name or None
        """
        for app_name, app_config in self._apps.items():
            if model in app_config.models.values():
                return app_name
        return None
    
    def get_models(
        self,
        app_name: Optional[str] = None
    ) -> List[Type[Model]]:
        """Get all models, optionally filtered by app.
        
        Args:
            app_name: Filter by app name (optional)
            
        Returns:
            List of model classes
        """
        if app_name:
            if app_name not in self._apps:
                return []
            return list(self._apps[app_name].models.values())
        
        # Return all models from all apps
        all_models = []
        for app_config in self._apps.values():
            all_models.extend(app_config.models.values())
        return all_models
    
    def get_apps(self) -> List[AppConfig]:
        """Get all registered apps.
        
        Returns:
            List of AppConfig instances
        """
        return list(self._apps.values())
    
    def get_all_apps_dict(self) -> Dict[str, AppConfig]:
        """Get all apps as a dictionary.
        
        Returns:
            Dictionary mapping app_name -> AppConfig
        """
        return dict(self._apps)
    
    def list_models(self) -> Dict[str, List[str]]:
        """List all models organized by app.
        
        Returns:
            Dictionary: app_name -> [model_names]
        """
        result = {}
        for app_name, app_config in self._apps.items():
            result[app_name] = sorted(app_config.models.keys())
        return result
    
    def check_conflicts(self) -> List[str]:
        """Check for model name conflicts across apps.
        
        Returns:
            List of conflicting model names
        """
        conflicts = []
        for model_name, models in self._models_by_name.items():
            if len(models) > 1:
                conflicts.append(model_name)
        return conflicts
    
    def get_model_qualified_name(self, model: Type[Model]) -> Optional[str]:
        """Get the fully qualified name of a model.
        
        Args:
            model: Model class
            
        Returns:
            Qualified name 'app.ModelName' or None
        """
        for qualified_name, m in self._models_by_qualified_name.items():
            if m is model:
                return qualified_name
        return None
    
    def validate_model_names(self) -> List[str]:
        """Validate that all model names are unique within their apps.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        for app_name, app_config in self._apps.items():
            seen_names = set()
            for model_name in app_config.models.keys():
                if model_name in seen_names:
                    errors.append(
                        f"App '{app_name}': Duplicate model name '{model_name}'"
                    )
                seen_names.add(model_name)
        
        return errors
    
    def __repr__(self) -> str:
        """String representation."""
        total_models = sum(len(app.models) for app in self._apps.values())
        return f"AppRegistry({len(self._apps)} apps, {total_models} models)"


# Global default registry instance
_default_registry: Optional[AppRegistry] = None


def get_default_registry() -> AppRegistry:
    """Get or create the default app registry.
    
    Returns:
        Default AppRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = AppRegistry()
    return _default_registry


def set_default_registry(registry: AppRegistry) -> None:
    """Set the default app registry.
    
    Args:
        registry: AppRegistry instance to use as default
    """
    global _default_registry
    _default_registry = registry


__all__ = [
    "AppConfig",
    "AppRegistry",
    "get_default_registry",
    "set_default_registry",
]
