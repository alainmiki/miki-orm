"""Tests for the miki-orm CLI (settings.py-backed, no YAML/TOML)."""

import os
import sys
import tempfile
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

# Guard: these tests require Python 3.14+ and the local package
from mikiorm.cli.cli import (
    load_settings,
    _handle_startproject,
    _handle_startapp,
)


# ===========================================================================
# load_settings
# ===========================================================================

class TestLoadSettings:
    """Tests for :func:`load_settings`."""

    def test_loads_existing_module(self, tmp_path):
        """A valid settings module on sys.path is imported successfully."""
        # Create a minimal settings module on disk
        mod_dir = tmp_path / "pkg"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("")
        (mod_dir / "settings.py").write_text(
            "DATABASES = {}\nINSTALLED_APPS = []\n"
        )
        sys.path.insert(0, str(tmp_path))
        try:
            load_settings("pkg.settings")  # no-op: just must not raise / sys.exit
        except SystemExit as exc:
            # load_settings calls sys.exit(1) on failure; this should NOT exit
            pytest.fail(f"load_settings exited with {exc}")
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("pkg.settings", None)
            sys.modules.pop("pkg", None)

    def test_fails_on_missing_module(self):
        """A non-existent module causes sys.exit(1)."""
        with pytest.raises(SystemExit) as exc:
            load_settings("nonexistent_settings_module_xyz")
        assert exc.value.code == 1


# ===========================================================================
# _handle_startproject
# ===========================================================================


class TestHandleStartproject:
    def _make_args(self, target="."):
        return type("Args", (), {"project_name": "conf", "target_dir": target})()

    def test_creates_settings_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = self._make_args(target=".")
        _handle_startproject(args)
        assert (tmp_path / "conf" / "settings.py").exists()

    def test_settings_file_has_expected_sections(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startproject(self._make_args("."))
        content = (tmp_path / "conf" / "settings.py").read_text(encoding="utf-8")
        assert "DATABASES" in content
        assert "INSTALLED_APPS" in content
        assert "MIGRATION_PATH" in content
        assert "configure_project" in content

    def test_fails_on_existing_non_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        proj = tmp_path / "conf"
        proj.mkdir()
        (proj / "existing.txt").write_text("hi")
        with pytest.raises(SystemExit) as exc:
            _handle_startproject(self._make_args("."))
        assert exc.value.code == 1

    def test_creates_nested_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = self._make_args(target=str(tmp_path))
        _handle_startproject(args)
        # startproject with target "."  →  ./conf/settings.py
        # with explicit dir   →  <target>/<project_name>/settings.py
        # In this fixture both resolve to tmp_path/conf/settings.py since
        # project_dir == target/project_name
        assert (tmp_path / "conf" / "settings.py").exists()


# ===========================================================================
# _handle_startapp
# ===========================================================================

class TestHandleStartapp:
    def _make_args(self, target_dir=None):
        return type("Args", (), {"app_name": "users", "target_dir": target_dir})()

    def test_creates_app_dir_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startapp(self._make_args())
        assert (tmp_path / "users").is_dir()

    def test_creates_app_dir_in_target(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()
        _handle_startapp(self._make_args(target_dir=str(apps_dir)))
        assert (apps_dir / "users").is_dir()

    def test_creates_app_py(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startapp(self._make_args())
        assert (tmp_path / "users" / "app.py").exists()

    def test_creates_models_py(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startapp(self._make_args())
        assert (tmp_path / "users" / "models.py").exists()

    def test_app_py_contains_app_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startapp(self._make_args())
        content = (tmp_path / "users" / "app.py").read_text(encoding="utf-8")
        assert "users" in content

    def test_models_py_mentions_register(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _handle_startapp(self._make_args())
        content = (tmp_path / "users" / "models.py").read_text(encoding="utf-8")
        assert "register" in content
