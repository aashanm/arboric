"""Configuration for receipt tests - skip if cryptography not available."""

import pytest

# Skip all receipt tests if cryptography is not available
pytest.importorskip("cryptography")
