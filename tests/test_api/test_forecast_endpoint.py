"""
Tests for /api/v1/forecast endpoint.
"""


def test_forecast_default_params(client):
    """Test forecast with default parameters."""
    response = client.get("/api/v1/forecast")

    assert response.status_code == 200
    data = response.json()

    assert data["command"] == "forecast"
    assert "data" in data

    result_data = data["data"]
    assert "metadata" in result_data
    assert "data" in result_data

    # Check metadata
    metadata = result_data["metadata"]
    assert metadata["region"] == "US-WEST"
    assert metadata["hours"] == 24
    assert metadata["data_points"] == 24
    assert metadata["resolution_minutes"] == 60

    # Check forecast data
    forecast_data = result_data["data"]
    assert len(forecast_data) == 24
    assert "timestamp" in forecast_data[0]
    assert "co2_intensity" in forecast_data[0]
    assert "price" in forecast_data[0]
    assert "renewable_percentage" in forecast_data[0]


def test_forecast_custom_region(client):
    """Test forecast with custom region."""
    response = client.get("/api/v1/forecast?region=EU-WEST")

    assert response.status_code == 200
    data = response.json()

    metadata = data["data"]["metadata"]
    assert metadata["region"] == "EU-WEST"


def test_forecast_custom_hours(client):
    """Test forecast with custom hours."""
    response = client.get("/api/v1/forecast?hours=48")

    assert response.status_code == 200
    data = response.json()

    metadata = data["data"]["metadata"]
    assert metadata["hours"] == 48
    assert metadata["data_points"] == 48
    assert len(data["data"]["data"]) == 48


def test_forecast_invalid_hours_too_low(client):
    """Test forecast with hours < 1."""
    response = client.get("/api/v1/forecast?hours=0")

    assert response.status_code == 422
    error = response.json()
    assert "ValidationError" in error["error"] or "validation" in str(error).lower()


def test_forecast_invalid_hours_too_high(client):
    """Test forecast with hours > 168."""
    response = client.get("/api/v1/forecast?hours=200")

    assert response.status_code == 422
    error = response.json()
    assert "ValidationError" in error["error"] or "validation" in str(error).lower()


def test_forecast_all_supported_regions(client):
    """Test forecast for all supported regions."""
    regions = ["US-WEST", "US-EAST", "EU-WEST", "NORDIC"]

    for region in regions:
        response = client.get(f"/api/v1/forecast?region={region}")
        assert response.status_code == 200

        data = response.json()
        assert data["data"]["metadata"]["region"] == region
