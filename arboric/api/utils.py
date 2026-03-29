"""
API utility functions for serialization and response formatting.

Reuses serialization logic from arboric.cli.export to maintain consistency
between API responses and export formats.
"""

from datetime import datetime

from arboric.cli.export import _serialize_fleet_result, _serialize_schedule_result
from arboric.core.models import FleetOptimizationResult, RegionComparisonResult, ScheduleResult


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


def serialize_schedule_for_api(
    result: ScheduleResult, runs_per_week: float | None = None, region: str | None = None
) -> dict:
    """
    Serialize ScheduleResult for API response.

    Reuses export module's serialization logic to ensure computed properties
    are included (cost_savings, carbon_savings_kg, delay_hours, etc.).

    Args:
        result: ScheduleResult to serialize
        runs_per_week: Optional job frequency for annual savings projection
        region: The region where optimization was performed

    Returns:
        Structured dictionary with workload, optimization, and metrics sections
    """
    data = _serialize_schedule_result(result)

    # Build savings dict with optional annual projection
    savings = {
        "cost": data["cost_savings"],  # Computed property
        "cost_percent": data["cost_savings_percent"],  # Computed property
        "carbon_kg": data["carbon_savings_kg"],  # Computed property
        "carbon_percent": data["carbon_savings_percent"],  # Computed property
    }
    if runs_per_week is not None:
        savings["annual_cost_savings"] = data["cost_savings"] * runs_per_week * 52 * 0.80
        savings["annual_projection_basis"] = f"{runs_per_week} runs/week × 52 weeks"

    return {
        "region": region or "unknown",
        "workload": data["workload"],
        "optimization": {
            "optimal_start": data["optimal_start"],
            "optimal_end": data["optimal_end"],
            "baseline_start": data["baseline_start"],
            "baseline_end": data["baseline_end"],
            "delay_hours": data["delay_hours"],  # Computed property
            "optimal_start_clock": data.get("optimal_start_clock"),  # Computed property
            "deadline_slack_hours": data.get("deadline_slack_hours"),  # Computed property
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
            "savings": savings,
        },
    }


def serialize_fleet_for_api(
    result: FleetOptimizationResult, runs_per_week: float | None = None
) -> dict:
    """
    Serialize FleetOptimizationResult for API response.

    Args:
        result: FleetOptimizationResult to serialize
        runs_per_week: Optional job frequency for annual savings projection

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
        "schedules": [
            serialize_schedule_for_api(schedule, runs_per_week) for schedule in result.schedules
        ],
    }


def serialize_region_comparison(result: RegionComparisonResult) -> dict:
    """
    Serialize RegionComparisonResult for API response.

    Args:
        result: RegionComparisonResult to serialize

    Returns:
        Structured dictionary with comparison entries sorted by cost
    """
    return {
        "workload_name": result.workload_name,
        "duration_hours": result.duration_hours,
        "cheapest_region": result.cheapest_region,
        "cleanest_region": result.cleanest_region,
        "entries": [
            {
                "region": entry.region,
                "optimal_start_clock": entry.optimal_start_clock,
                "delay_hours": entry.delay_hours,
                "avg_spot_price": entry.avg_spot_price,
                "avg_carbon": entry.avg_carbon,
                "optimized_cost": entry.optimized_cost,
                "optimized_carbon_kg": entry.optimized_carbon_kg,
                "cost_savings": entry.cost_savings,
                "cost_savings_percent": entry.cost_savings_percent,
                "carbon_savings_kg": entry.carbon_savings_kg,
                "carbon_savings_percent": entry.carbon_savings_percent,
                "on_demand_rate_per_hr": entry.on_demand_rate_per_hr,
            }
            for entry in result.entries
        ],
        "generated_at": result.generated_at.isoformat(),
    }
