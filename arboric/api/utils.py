"""
API utility functions for serialization and response formatting.

Reuses serialization logic from arboric.cli.export to maintain consistency
between API responses and export formats.
"""

from datetime import datetime

from arboric.cli.export import _serialize_fleet_result, _serialize_schedule_result
from arboric.core.models import FleetOptimizationResult, ScheduleResult


def create_api_response(command: str, data: dict) -> dict:
    """
    Create standardized API response with metadata wrapper.

    All API responses follow this format:
    {
        "command": "optimize",
        "timestamp": "2026-02-10T10:30:00Z",
        "version": "0.1.0",
        "data": { ... }
    }

    Args:
        command: API command that generated this response
        data: Response payload

    Returns:
        Standardized response dictionary
    """
    return {
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
        "data": data,
    }


def serialize_schedule_for_api(result: ScheduleResult) -> dict:
    """
    Serialize ScheduleResult for API response.

    Reuses export module's serialization logic to ensure computed properties
    are included (cost_savings, carbon_savings_kg, delay_hours, etc.).

    Args:
        result: ScheduleResult to serialize

    Returns:
        Structured dictionary with workload, optimization, and metrics sections
    """
    data = _serialize_schedule_result(result)

    return {
        "workload": data["workload"],
        "optimization": {
            "optimal_start": data["optimal_start"],
            "optimal_end": data["optimal_end"],
            "baseline_start": data["baseline_start"],
            "baseline_end": data["baseline_end"],
            "delay_hours": data["delay_hours"],  # Computed property
        },
        "metrics": {
            "optimized": {
                "cost": data["optimized_cost"],
                "carbon_kg": data["optimized_carbon_kg"],
                "avg_price": data["optimized_avg_price"],
                "avg_carbon": data["optimized_avg_carbon"],
            },
            "baseline": {
                "cost": data["baseline_cost"],
                "carbon_kg": data["baseline_carbon_kg"],
                "avg_price": data["baseline_avg_price"],
                "avg_carbon": data["baseline_avg_carbon"],
            },
            "savings": {
                "cost": data["cost_savings"],  # Computed property
                "cost_percent": data["cost_savings_percent"],  # Computed property
                "carbon_kg": data["carbon_savings_kg"],  # Computed property
                "carbon_percent": data["carbon_savings_percent"],  # Computed property
            },
        },
    }


def serialize_fleet_for_api(result: FleetOptimizationResult) -> dict:
    """
    Serialize FleetOptimizationResult for API response.

    Args:
        result: FleetOptimizationResult to serialize

    Returns:
        Structured dictionary with summary and schedules sections
    """
    data = _serialize_fleet_result(result)

    return {
        "summary": {
            "total_workloads": data["total_workloads"],
            "total_cost_savings": data["total_cost_savings"],
            "total_carbon_savings_kg": data["total_carbon_savings_kg"],
            "average_cost_savings_percent": data["average_cost_savings_percent"],  # Computed
            "average_carbon_savings_percent": data["average_carbon_savings_percent"],  # Computed
            "optimization_timestamp": data["optimization_timestamp"],
        },
        "schedules": [serialize_schedule_for_api(schedule) for schedule in result.schedules],
    }
