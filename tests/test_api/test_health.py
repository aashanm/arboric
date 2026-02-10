"""
Tests for health and status endpoints.
"""


def test_root_endpoint(client):
    """Test root endpoint returns API info."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "Arboric API"
    assert data["version"] == "0.1.0"
    assert data["docs"] == "/docs"
    assert data["health"] == "/api/v1/health"


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_status_endpoint(client):
    """Test status endpoint returns system information."""
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    data = response.json()

    assert data["command"] == "status"
    assert "data" in data

    status_data = data["data"]
    assert "service" in status_data
    assert "components" in status_data
    assert "configuration" in status_data

    # Check service info
    service = status_data["service"]
    assert service["name"] == "arboric-api"
    assert service["version"] == "0.1.0"
    assert service["status"] == "online"
    assert "uptime_seconds" in service

    # Check components
    components = status_data["components"]
    assert "grid_oracle" in components
    assert "autopilot" in components
    assert "supported_regions" in components
    assert len(components["supported_regions"]) > 0


def test_config_endpoint(client):
    """Test config endpoint returns configuration."""
    response = client.get("/api/v1/config")

    assert response.status_code == 200
    data = response.json()

    assert data["command"] == "config"
    assert "data" in data

    config_data = data["data"]
    assert "optimization" in config_data
    assert "defaults" in config_data
    assert "api" in config_data

    # Check optimization config
    optimization = config_data["optimization"]
    assert "price_weight" in optimization
    assert "carbon_weight" in optimization
    assert optimization["price_weight"] + optimization["carbon_weight"] == 1.0
