"""
Shared test fixtures for API tests.
"""

import pytest
from fastapi.testclient import TestClient

from arboric.api.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_workload_payload():
    """Sample workload payload for testing."""
    return {
        "workload": {
            "name": "Test Job",
            "duration_hours": 4.0,
            "power_draw_kw": 50.0,
            "deadline_hours": 12.0,
            "workload_type": "ml_training",
        },
        "region": "US-WEST",
    }


@pytest.fixture
def sample_fleet_payload():
    """Sample fleet payload for testing."""
    return {
        "workloads": [
            {
                "name": "Job 1",
                "duration_hours": 4.0,
                "power_draw_kw": 50.0,
                "deadline_hours": 12.0,
            },
            {
                "name": "Job 2",
                "duration_hours": 2.0,
                "power_draw_kw": 30.0,
                "deadline_hours": 8.0,
            },
        ],
        "region": "US-WEST",
    }
