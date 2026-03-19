"""Configuration for receipt tests - skip if cryptography not available."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip all receipt tests if cryptography is not available."""
    try:
        import cryptography  # noqa: F401
    except ImportError:
        skip_marker = pytest.mark.skip(reason="cryptography not installed")
        for item in items:
            item.add_marker(skip_marker)
