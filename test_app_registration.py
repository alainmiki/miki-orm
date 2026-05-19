"""Tests for enhanced app-based model registration system."""

import pytest
import tempfile
import sys
from pathlib import Path
from mikiorm.models import (
    Model, CharField, IntegerField, AppRegistry, AppConfig,
    get_default_registry, set_default_registry
)


class TestAppConfig:
    """Test AppConfig functionality."""
    
    def test_app_config_initialization(self):
        """Test AppConfig creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(
                app_name='test_app',
                base_path=tmpdir,
                verbose_name='Test Application'
            )
            
            assert config.app_name == 'test_app'
            assert config.verbose_name == 'Test Application'
            assert config.base_path == Path(tmpdir).resolve()
    
    def test_app_config_models_path(self):
        """Test models.py path resolution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig('test', tmpdir)
            models_path = config.get_models_path()
            
            assert models_path == Path(tmpdir) / 'models.py'
    
    def test_app_config_migrations_path(self):
        """Test migrations directory path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig('test', tmpdir)
            migrations_path = config.get_migrations_path()
            
            assert migrations_path == Path(tmpdir) / 'migrations'
    
    def test_app_config_has_models(self):
        """Test checking for models.py existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig('test', tmpdir)
            
            assert not config.has_models()
            
            # Create models.py
            models_file = Path(tmpdir) / 'models.py'
            models_file.write_text('')
            
            assert config.has_models()


class TestAppRegistry:
    """Test AppRegistry functionality."""
    
    def test_registry_initialization(self):
        """Test AppRegistry creation."""
        registry = AppRegistry()
        
        assert len(registry.get_apps()) == 0
        assert len(registry.list_models()) == 0
    
    def test_register_app(self):
        """Test app registration."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            app_config = registry.register_app(
                'users',
                tmpdir,
                verbose_name='Users App'
            )
            
            assert app_config.app_name == 'users'
            assert len(registry.get_apps()) == 1
            assert registry.get_app('users') is app_config
    
    def test_register_app_duplicate_error(self):
        """Test that duplicate app registration fails."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            with pytest.raises(ValueError):
                registry.register_app('users', tmpdir)
    
    def test_register_app_invalid_name(self):
        """Test that invalid app names are rejected."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                registry.register_app('user-app', tmpdir)  # Hyphens not allowed
    
    def test_register_app_nonexistent_path(self):
        """Test that non-existent paths are rejected."""
        registry = AppRegistry()
        
        with pytest.raises(ValueError):
            registry.register_app('test', '/nonexistent/path')
    
    def test_unregister_app(self):
        """Test app unregistration."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            assert len(registry.get_apps()) == 1
            
            registry.unregister_app('users')
            assert len(registry.get_apps()) == 0
    
    def test_register_model_in_app(self):
        """Test registering a model in an app."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            class User(Model):
                name = CharField(max_length=100)
            
            registry.register_model_in_app('users', User)
            
            app_config = registry.get_app('users')
            assert 'User' in app_config.models
            assert app_config.models['User'] is User
    
    def test_get_model_by_qualified_name(self):
        """Test getting model by qualified name."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            class User(Model):
                name = CharField(max_length=100)
            
            registry.register_model_in_app('users', User)
            
            # Get by qualified name
            model = registry.get_model('users.User')
            assert model is User
    
    def test_get_model_by_unqualified_name(self):
        """Test getting model by unqualified name (if unique)."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            class User(Model):
                name = CharField(max_length=100)
            
            registry.register_model_in_app('users', User)
            
            # Get by unqualified name
            model = registry.get_model('User')
            assert model is User
    
    def test_get_model_ambiguous_error(self):
        """Test that ambiguous model names raise error."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            registry.register_app('users', tmpdir1)
            registry.register_app('admin', tmpdir2)
            
            class User(Model):
                name = CharField(max_length=100)
            
            class AdminUser(Model):
                pass
            AdminUser.__name__ = 'User'  # Same name, different class
            
            registry.register_model_in_app('users', User)
            registry.register_model_in_app('admin', AdminUser)
            
            # Unqualified name should raise error (ambiguous)
            with pytest.raises(ValueError):
                registry.get_model('User')
    
    def test_get_models_all(self):
        """Test getting all models."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            class User(Model):
                name = CharField(max_length=100)
            
            class Profile(Model):
                bio = CharField(max_length=500)
            
            registry.register_model_in_app('users', User)
            registry.register_model_in_app('users', Profile)
            
            models = registry.get_models()
            assert len(models) == 2
            assert User in models
            assert Profile in models
    
    def test_get_models_by_app(self):
        """Test getting models from specific app."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            registry.register_app('users', tmpdir1)
            registry.register_app('products', tmpdir2)
            
            class User(Model):
                name = CharField(max_length=100)
            
            class Product(Model):
                title = CharField(max_length=200)
            
            registry.register_model_in_app('users', User)
            registry.register_model_in_app('products', Product)
            
            user_models = registry.get_models('users')
            assert len(user_models) == 1
            assert user_models[0] is User
            
            product_models = registry.get_models('products')
            assert len(product_models) == 1
            assert product_models[0] is Product
    
    def test_list_models(self):
        """Test listing models organized by app."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            registry.register_app('users', tmpdir1)
            registry.register_app('products', tmpdir2)
            
            class User(Model):
                name = CharField(max_length=100)
            
            class Product(Model):
                title = CharField(max_length=200)
            
            registry.register_model_in_app('users', User)
            registry.register_model_in_app('products', Product)
            
            model_list = registry.list_models()
            
            assert 'users' in model_list
            assert 'products' in model_list
            assert 'User' in model_list['users']
            assert 'Product' in model_list['products']
    
    def test_check_conflicts(self):
        """Test detecting model name conflicts."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            registry.register_app('users', tmpdir1)
            registry.register_app('admin', tmpdir2)
            
            class User(Model):
                name = CharField(max_length=100)
            
            class AdminUser(Model):
                pass
            AdminUser.__name__ = 'User'
            
            registry.register_model_in_app('users', User)
            registry.register_model_in_app('admin', AdminUser)
            
            conflicts = registry.check_conflicts()
            assert 'User' in conflicts
    
    def test_get_model_qualified_name(self):
        """Test getting qualified name for a model."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            registry.register_app('users', tmpdir)
            
            class User(Model):
                name = CharField(max_length=100)
            
            registry.register_model_in_app('users', User)
            
            qualified_name = registry.get_model_qualified_name(User)
            assert qualified_name == 'users.User'


class TestModelRegistryBackwardCompat:
    """Test backward compatibility of ModelRegistry."""
    
    def test_register_model_legacy(self):
        """Test legacy model registration API."""
        from mikiorm.models import ModelRegistry
        
        class LegacyUser(Model):
            name = CharField(max_length=100)
        
        ModelRegistry.register_model(LegacyUser)
        
        # Should be retrievable via legacy API
        model = ModelRegistry.get_model('LegacyUser')
        assert model is LegacyUser
    
    def test_all_models_legacy(self):
        """Test legacy all_models API."""
        from mikiorm.models import ModelRegistry
        
        class LegacyProduct(Model):
            title = CharField(max_length=200)
        
        ModelRegistry.register_model(LegacyProduct)
        
        models = ModelRegistry.all_models()
        assert LegacyProduct in models


class TestAutoDiscovery:
    """Test auto-discovery of models."""
    
    def test_auto_discover_simple(self):
        """Test auto-discovering models from models.py."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create models.py file
            models_file = Path(tmpdir) / 'models.py'
            models_file.write_text('''
from mikiorm.models import Model, CharField

class TestModel(Model):
    name = CharField(max_length=100)
''')
            
            # Register app and discover
            registry.register_app('test', tmpdir)
            count = registry.auto_discover()
            
            assert count == 1
            model = registry.get_model('test.TestModel')
            assert model is not None
    
    def test_auto_discover_multiple_apps(self):
        """Test auto-discovering in multiple apps."""
        registry = AppRegistry()
        
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            # Create models in first app
            (Path(tmpdir1) / 'models.py').write_text('''
from mikiorm.models import Model, CharField

class User(Model):
    name = CharField(max_length=100)
''')
            
            # Create models in second app
            (Path(tmpdir2) / 'models.py').write_text('''
from mikiorm.models import Model, CharField

class Product(Model):
    title = CharField(max_length=200)
''')
            
            registry.register_app('users', tmpdir1)
            registry.register_app('products', tmpdir2)
            count = registry.auto_discover(verbose=False)
            
            assert count == 2
            assert registry.get_model('users.User') is not None
            assert registry.get_model('products.Product') is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
