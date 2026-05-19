"""Registry for all defined models and metadata introspection.

Enhanced to support app-based namespacing with backward compatibility.
Delegates to AppRegistry for new functionality while maintaining legacy API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from .base import Model

from .app_registry import get_default_registry


class ModelRegistry:
    """Model registry with backward-compatible interface.
    
    Provides legacy API while delegating to AppRegistry for full functionality.
    """
    
    _models: Dict[str, Type[Any]] = {}  # Legacy fallback

    @classmethod
    def register_model(cls, model: Type[Any]) -> None:
        """Register a model (legacy API, uses default app).
        
        Args:
            model: Model class to register
        """
        # Store in legacy registry
        cls._models[model.__name__] = model
        
        # Also register in app registry (default app)
        registry = get_default_registry()
        if not registry.get_app('default'):
            registry.register_app('default', '.')
        registry.register_model_in_app('default', model)

    @classmethod
    def get_model(cls, name: str) -> Optional[Type[Any]]:
        """Get a model by name or qualified name.
        
        Supports both legacy (name only) and new (app.Model) formats.
        
        Args:
            name: Model name or 'app.ModelName'
            
        Returns:
            Model class or None if not found
        """
        # Try app registry first
        registry = get_default_registry()
        model = registry.get_model(name)
        if model:
            return model
        
        # Fallback to legacy registry
        return cls._models.get(name)

    @classmethod
    def all_models(cls) -> List[Type[Any]]:
        """Get all registered models.
        
        Returns:
            List of all model classes
        """
        registry = get_default_registry()
        models = registry.get_models()
        if models:
            return models
        return list(cls._models.values())
    
    @classmethod
    def get_app_registry(cls):
        """Get the underlying app registry.
        
        Allows advanced usage with app namespacing.
        
        Returns:
            AppRegistry instance
        """
        return get_default_registry()
    
    @classmethod
    def get_models_by_app(cls, app_name: str) -> List[Type[Any]]:
        """Get models from a specific app.
        
        Args:
            app_name: Name of app
            
        Returns:
            List of models in the app
        """
        registry = get_default_registry()
        return registry.get_models(app_name)
    
    @classmethod
    def list_all_apps(cls) -> Dict[str, List[str]]:
        """List all apps and their models.
        
        Returns:
            Dictionary: app_name -> [model_names]
        """
        registry = get_default_registry()
        return registry.list_models()
    
    @classmethod
    def get_model_qualified_name(cls, model: Type[Any]) -> Optional[str]:
        """Get the fully qualified name of a model.
        
        Args:
            model: Model class
            
        Returns:
            Qualified name 'app.ModelName' or None
        """
        registry = get_default_registry()
        return registry.get_model_qualified_name(model)