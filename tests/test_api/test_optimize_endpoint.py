"""
Tests for /api/v1/optimize endpoint.
"""


def test_optimize_endpoint_success(client, sample_workload_payload):
    """Test successful single workload optimization."""
    response = client.post("/api/v1/optimize", json=sample_workload_payload)

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["command"] == "optimize"
    assert "timestamp" in data
    assert "version" in data
    assert data["version"] == "0.1.0"
    assert "data" in data

    # Check data structure
    result_data = data["data"]
    assert "workload" in result_data
    assert "optimization" in result_data
    assert "metrics" in result_data

    # Check workload details
    workload = result_data["workload"]
    assert workload["name"] == "Test Job"
    assert workload["duration_hours"] == 4.0
    assert workload["power_draw_kw"] == 50.0
    assert workload["energy_kwh"] == 200.0  # Computed property

    # Check optimization details
    optimization = result_data["optimization"]
    assert "optimal_start" in optimization
    assert "optimal_end" in optimization
    assert "baseline_start" in optimization
    assert "baseline_end" in optimization
    assert "delay_hours" in optimization  # Computed property
    assert optimization["delay_hours"] >= 0

    # Check metrics structure
    metrics = result_data["metrics"]
    assert "optimized" in metrics
    assert "baseline" in metrics
    assert "savings" in metrics

    # Check savings (computed properties)
    savings = metrics["savings"]
    assert "cost" in savings
    assert "cost_percent" in savings
    assert "carbon_kg" in savings
    assert "carbon_percent" in savings


def test_optimize_with_custom_config(client):
    """Test optimization with custom optimization config."""
    payload = {
        "workload": {
            "name": "Custom Config Job",
            "duration_hours": 2.0,
            "power_draw_kw": 30.0,
            "deadline_hours": 12.0,
        },
        "region": "US-EAST",
        "optimization_config": {"price_weight": 0.8, "carbon_weight": 0.2},
    }

    response = client.post("/api/v1/optimize", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["command"] == "optimize"
    assert "data" in data


def test_optimize_with_invalid_workload(client):
    """Test optimization with invalid workload (deadline < duration)."""
    payload = {
        "workload": {
            "name": "Bad Job",
            "duration_hours": 12.0,
            "power_draw_kw": 50.0,
            "deadline_hours": 4.0,  # Invalid: deadline < duration
        }
    }

    response = client.post("/api/v1/optimize", json=payload)

    assert response.status_code == 422
    error = response.json()
    assert error["error"] == "ValidationError"
    assert "details" in error


def test_optimize_with_missing_fields(client):
    """Test optimization with missing required fields."""
    payload = {"workload": {"name": "Incomplete Job"}}  # Missing required fields

    response = client.post("/api/v1/optimize", json=payload)

    assert response.status_code == 422
    error = response.json()
    assert error["error"] == "ValidationError"


def test_optimize_with_invalid_optimization_config(client):
    """Test optimization with invalid config weights."""
    payload = {
        "workload": {
            "name": "Test Job",
            "duration_hours": 4.0,
            "power_draw_kw": 50.0,
            "deadline_hours": 12.0,
        },
        "optimization_config": {
            "price_weight": 0.5,
            "carbon_weight": 0.3,  # Sum != 1.0
        },
    }

    response = client.post("/api/v1/optimize", json=payload)

    assert response.status_code == 422
    error = response.json()
    assert "ValidationError" in error["error"] or "weight" in str(error).lower()
