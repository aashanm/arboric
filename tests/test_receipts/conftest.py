"""Configuration for receipt tests - skip if cryptography not available."""

import pytest

# Check if cryptography is available at import time
try:
    import cryptography  # noqa: F401

    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    _CRYPTOGRAPHY_AVAILABLE = False


def pytest_collection_modifyitems(config, items):
    """Skip all receipt tests if cryptography is not available."""
    if not _CRYPTOGRAPHY_AVAILABLE:
        skip_marker = pytest.mark.skip(reason="cryptography not installed")
        for item in items:
            item.add_marker(skip_marker)
