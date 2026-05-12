"""Pytest configuration and shared fixtures for miki-orm tests."""

import sys
import asyncio

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--backend",
        action="store",
        default="all",
        help="Run tests for specific backend: sqlite, postgres, all",
    )


def pytest_collection_modifyitems(config, items):
    backend_choice = config.getoption("--backend")
    if backend_choice == "all":
        return
    # Skip tests not marked with the requested backend
    selected = []
    for item in items:
        # Get parametrize backend from item's fixtures
        if hasattr(item, "callspec"):
            param_backends = item.callspec.params.get("backend", [])
            if backend_choice not in param_backends:
                item.add_marker(pytest.mark.skip(reason="Backend not selected"))
        selected.append(item)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Set default asyncio mode for pytest-asyncio if available
pytest_plugins = ("pytest_asyncio",)
