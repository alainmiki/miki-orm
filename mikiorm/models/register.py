"""Unified model registration system with decorator and API support.

This module consolidates app-based model registration with support for:
- Multiple apps with separate model namespaces
- Duplicate model names across different apps
- Pythonic @register decorator for registration
- Auto-discovery of models.py files
- Model resolution: app.ModelName or just ModelName (if unique)
- Backward compatible with legacy ModelRegistry API

Example:
    # Decorator-based registration
    @register(app='users')
    class User(Model):
        name = CharField()
    
    # API-based registration
    from mikiorm.models.register import register_app, register_model
    
    register_app('users', base_path='./apps/users')
    register_app('products', base_path='./apps/products')
    
    # Auto-discover or manual registration
    get_default_registry().auto_discover()
    register_model(UserModel, app='users')
    
    # Model retrieval
    User = get_model('users.User')  # Qualified name
    Product = get_model('Product')  # If unique
"""

from __future__ import annotations

import importlib.util
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Type, Tuple, TypeVar

if TYPE_CHECKING:
    from .base import Model

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


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
        self._models_by_qualified_name: Dict[str, Type[Model]] = {}
        self._models_by_name: Dict[str, List[Type[Model]]] = {}
        self._global_registry: Dict[str, Type[Model]] = {}
    
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
        
        logger.debug(f"Registered app: {app_name} at {base_path}")
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
        logger.debug(f"Unregistered app: {app_name}")
    
    def auto_discover(self, verbose: bool = False, force: bool = False) -> int:
        """Auto-discover models in all registered apps.

        Scans each app's ``models.py`` file and registers all ``Model``
        subclasses that are defined directly in that file.

        Args:
            verbose: Print discovery information.
            force:   Re-discover even if the app has already been scanned.

        Returns:
            Number of models discovered across all apps.
        """
        total_discovered = 0

        for app_name, app_config in self._apps.items():
            if app_config.is_discovered() and not force:
                continue

            if not app_config.has_models():
                if verbose:
                    logger.info("App '%s': No models.py found", app_name)
                continue

            try:
                discovered = self._discover_app_models(app_config, verbose)
                total_discovered += discovered
                app_config._discovered = True

                if verbose:
                    logger.info("App '%s': Discovered %d model(s)", app_name, discovered)
            except Exception as e:
                logger.error("Error discovering models in app '%s': %s", app_name, e)

        return total_discovered
    
    def _discover_app_models(self, app_config: AppConfig, verbose: bool = False) -> int:
        """Discover models in a specific app.

        The path-guard below ensures the module being imported cannot escape
        the registered app directory (prevents ``models/../../etc/passwd``
        supply-chain or symlink attacks).

        Args:
            app_config: App configuration.
            verbose:    Print information.

        Returns:
            Number of models discovered in *app_config*.
        """
        from .base import Model  # local import to avoid circular deps

        models_file = app_config.get_models_path()

        # ── Security: guard against path traversal ──────────────────
        try:
            resolved_file = models_file.resolve()
            resolved_base = app_config.base_path.resolve()
            _ = resolved_file.relative_to(resolved_base)
        except (OSError, ValueError):
            logger.warning(
                "Refusing to import %r: not inside registered app path %s",
                str(models_file),
                app_config.base_path,
            )
            return 0

        # Create a module spec for dynamic import
        spec = importlib.util.spec_from_file_location(
            f"{app_config.module_path}.models",
            models_file
        )

        if not spec or not spec.loader:
            return 0

        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(
                "Failed to import models from '%s': %s",
                app_config.app_name, e,
            )
            return 0
        
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

    def auto_discover_app_models(
        self, app_name: str, verbose: bool = False, force: bool = False
    ) -> int:
        """Discover and register models for a single named app.

        Args:
            app_name: The app to scan.
            verbose:  Print discovery information.
            force:    Re-discover even if already scanned.

        Returns:
            Number of models registered.
        """
        app_config = self._apps.get(app_name)
        if app_config is None:
            logger.warning("auto_discover_app_models: app '%s' is not registered", app_name)
            return 0

        if app_config.is_discovered() and not force:
            return 0

        if not app_config.has_models():
            if verbose:
                logger.info("App '%s': No models.py found", app_name)
            return 0

        return self._discover_app_models(app_config, verbose)

    def auto_discover_apps_from_settings(self) -> int:
        """Convenience wrapper: discover models from every entry in
        ``settings.installed_apps``.

        Apps not yet registered with this ``AppRegistry`` are registered
        first.  Paths are resolved via :func:`_resolve_app_path` when
        the ``installed_apps`` entry is a plain dotted name.

        Returns:
            Total number of models registered across all apps.
        """
        from ..conf.settings import settings

        total = 0
        for entry in settings.installed_apps:
            label = getattr(entry, "label", entry.name)
            path_intended: Optional[str] = None
            if isinstance(entry, str):
                label = entry.split(".")[-1]
                path_intended = _resolve_app_path(entry)
            else:
                path_intended = entry.path

            # Register app if not yet tracked by this registry
            if not self.get_app(label):
                if path_intended:
                    try:
                        self.register_app(label, path_intended)
                    except (ValueError, FileNotFoundError) as exc:
                        logger.warning("Could not register app %r: %s", label, exc)
                        continue

            total += self.auto_discover_app_models(label)

        return total

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _resolve_app_path(name: str) -> str:
        """Resolve a dotted app name to an absolute filesystem directory.

        Walks ``sys.path`` entries (virtualenv, site-packages, CWD) looking
        for a matching ``<name>/__init__.py`` package marker.  When no match
        is found the CWD-based fallback is returned so the caller can still
        attempt discovery without raising.

        Args:
            name: Dotted Python path (e.g. ``"users"`` or
                  ``"myproj.apps.users"``).

        Returns:
            Absolute path string, never raises.
        """
        leaf = name.split(".")[-1]

        # entries in sys.path first (virtualenv / site-packages ordering)
        for entry in sys.path:
            candidate = Path(entry) / name.replace(".", os.sep)
            if (candidate / "__init__.py").exists():
                return str(candidate.resolve())
            # Also check the simple leaf name
            leaf_dir = Path(entry) / leaf
            if (leaf_dir / "__init__.py").exists():
                return str(leaf_dir.resolve())

        # CWD and direct leaf-sub-path
        cwd = Path.cwd()
        direct = cwd / name.replace(".", os.sep)
        if (direct / "__init__.py").exists() or direct.is_dir():
            return str(direct.resolve())
        cwd_leaf = cwd / leaf
        if (cwd_leaf / "__init__.py").exists() or cwd_leaf.is_dir():
            return str(cwd_leaf.resolve())

        # Absolute path case
        p = Path(name)
        if p.is_dir():
            return str(p.resolve())

        # CWD leaf fallback — safest default for |startapp| style layout
        return str((cwd / leaf).resolve())

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
        
        # Sync app_label to model meta
        if hasattr(model, '_meta'):
            model._meta.app_label = app_name

        # Store in app's models
        app_config.models[model_name] = model
        
        # Store in qualified name index
        qualified_name = f"{app_name}.{model_name}"
        self._models_by_qualified_name[qualified_name] = model
        
        # Store in name index (for ambiguity resolution)
        if model_name not in self._models_by_name:
            self._models_by_name[model_name] = []
        if model not in self._models_by_name[model_name]:
            self._models_by_name[model_name].append(model)
        
        # Store in global registry (backward compat)
        if model_name not in self._global_registry:
            self._global_registry[model_name] = model
        
        if verbose:
            logger.info(f"Registered: {qualified_name}")
    
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


def register(app: str, **kwargs) -> Callable[[Type[T]], Type[T]]:
    """Decorator for registering a model.
    
    Mandatorily requires an app label to ensure namespacing.
    """
    app_name = kwargs.get('app_label', app)
    
    if not isinstance(app_name, str):
        raise ValueError(
            "@register decorator now mandatorily requires an app label string. "
            "Usage: @register(app='your_app_name')"
        )

    registry = get_default_registry()

    def do_register(model_cls: Type[T], app_name: str) -> Type[T]:
        if not registry.get_app(app_name):
            try:
                # Fallback registration for simple scripts
                registry.register_app(app_name, os.getcwd())
            except ValueError:
                pass  # App already registered
        registry.register_model_in_app(app_name, model_cls)
        return model_cls

    def decorator(model_class: Type[T]) -> Type[T]:
        do_register(model_class, app_name)
        return model_class

    return decorator


def register_model(model: Type[Model], app: str = 'default') -> None:
    """Register a model in an app.
    
    Args:
        model: Model class to register
        app: App name (default: 'default')
    """
    registry = get_default_registry()
    
    # Ensure app is registered
    if not registry.get_app(app):
        registry.register_app(app, '.')
    
    registry.register_model_in_app(app, model)


def register_app(app_name: str, base_path: str, **kwargs) -> AppConfig:
    """Register an app.
    
    Args:
        app_name: Name of app
        base_path: Path to app directory
        **kwargs: Additional arguments (module_path, verbose_name)
        
    Returns:
        AppConfig instance
    """
    registry = get_default_registry()
    return registry.register_app(app_name, base_path, **kwargs)


def get_model(model_path: str) -> Optional[Type[Model]]:
    """Get a model by name or qualified name.
    
    Args:
        model_path: Model name or 'app.ModelName'
        
    Returns:
        Model class or None
    """
    registry = get_default_registry()
    return registry.get_model(model_path)


def auto_discover(verbose: bool = False) -> int:
    """Auto-discover models in all registered apps.
    
    Args:
        verbose: Print discovery information
        
    Returns:
        Number of models discovered
    """
    registry = get_default_registry()
    return registry.auto_discover(verbose)


def list_models() -> Dict[str, List[str]]:
    """List all registered models organized by app.
    
    Returns:
        Dictionary: app_name -> [model_names]
    """
    registry = get_default_registry()
    return registry.list_models()


def get_all_models() -> List[Type[Model]]:
    """Get all registered models.
    
    Returns:
        List of all model classes
    """
    registry = get_default_registry()
    return registry.get_models()


def get_apps() -> List[AppConfig]:
    """Get all registered apps.
    
    Returns:
        List of AppConfig instances
    """
    registry = get_default_registry()
    return registry.get_apps()


# Backward compatibility: Legacy ModelRegistry interface
class ModelRegistry:
    """Legacy registry interface (deprecated, use functions above).
    
    Provided for backward compatibility.
    """
    
    _models: Dict[str, Type[Any]] = {}
    
    @classmethod
    def register_model(cls, model: Type[Any]) -> None:
        """Register a model (legacy API, uses default app)."""
        register(app='default')(model)
    
    @classmethod
    def get_model(cls, name: str) -> Optional[Type[Any]]:
        """Get a model by name or qualified name."""
        return get_model(name)
    
    @classmethod
    def all_models(cls) -> List[Type[Any]]:
        """Get all registered models."""
        return get_all_models()
    
    @classmethod
    def get_app_registry(cls):
        """Get the underlying app registry."""
        return get_default_registry()
    
    @classmethod
    def get_models_by_app(cls, app_name: str) -> List[Type[Any]]:
        """Get models from a specific app."""
        registry = get_default_registry()
        return registry.get_models(app_name)
    
    @classmethod
    def list_all_apps(cls) -> Dict[str, List[str]]:
        """List all apps and their models."""
        return list_models()
    
    @classmethod
    def get_model_qualified_name(cls, model: Type[Any]) -> Optional[str]:
        """Get the fully qualified name of a model."""
        registry = get_default_registry()
        return registry.get_model_qualified_name(model)


__all__ = [
    # Classes
    "AppConfig",
    "AppRegistry",
    "ModelRegistry",
    # Registry management
    "get_default_registry",
    "set_default_registry",
    # Decorator and functions
    "register",
    "register_model",
    "register_app",
    "get_model",
    "auto_discover",
    "auto_discover_app_models",
    "auto_discover_apps_from_settings",
    "list_models",
    "get_all_models",
    "get_apps",
]
