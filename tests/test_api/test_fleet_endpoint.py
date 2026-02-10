"""
Tests for /api/v1/fleet/optimize endpoint.
"""


def test_fleet_optimize_success(client, sample_fleet_payload):
    """Test successful fleet optimization."""
    response = client.post("/api/v1/fleet/optimize", json=sample_fleet_payload)

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["command"] == "fleet"
    assert "timestamp" in data
    assert "data" in data

    # Check data structure
    result_data = data["data"]
    assert "summary" in result_data
    assert "schedules" in result_data

    # Check summary
    summary = result_data["summary"]
    assert summary["total_workloads"] == 2
    assert "total_cost_savings" in summary
    assert "total_carbon_savings_kg" in summary
    assert "average_cost_savings_percent" in summary  # Computed property
    assert "average_carbon_savings_percent" in summary  # Computed property

    # Check schedules
    schedules = result_data["schedules"]
    assert len(schedules) == 2
    assert schedules[0]["workload"]["name"] == "Job 1"
    assert schedules[1]["workload"]["name"] == "Job 2"


def test_fleet_optimize_single_workload(client):
    """Test fleet optimization with single workload."""
    payload = {
        "workloads": [
            {
                "name": "Single Job",
                "duration_hours": 4.0,
                "power_draw_kw": 50.0,
                "deadline_hours": 12.0,
            }
        ]
    }

    response = client.post("/api/v1/fleet/optimize", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["summary"]["total_workloads"] == 1


def test_fleet_optimize_empty_workloads(client):
    """Test fleet optimization with no workloads."""
    payload = {"workloads": []}

    response = client.post("/api/v1/fleet/optimize", json=payload)

    assert response.status_code == 422
    error = response.json()
    assert error["error"] == "ValidationError"


def test_fleet_optimize_too_many_workloads(client):
    """Test fleet optimization with more than 100 workloads."""
    workloads = [
        {
            "name": f"Job {i}",
            "duration_hours": 2.0,
            "power_draw_kw": 30.0,
            "deadline_hours": 12.0,
        }
        for i in range(101)
    ]
    payload = {"workloads": workloads}

    response = client.post("/api/v1/fleet/optimize", json=payload)

    assert response.status_code == 422
    error = response.json()
    assert error["error"] == "ValidationError"
