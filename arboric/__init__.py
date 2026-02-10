"""
Arboric - Intelligent Autopilot for Cloud Infrastructure

Automatically schedule heavy AI workflows and data pipelines to the
cheapest and cleanest times of the day. Slash electricity bills and
carbon emissions with algorithmic precision.

Usage:
    from arboric import Workload, MockGrid, Autopilot

    # Define your workload
    workload = Workload(
        name="LLM Training",
        duration_hours=6,
        power_draw_kw=100,
        deadline_hours=24
    )

    # Get grid forecast
    grid = MockGrid(region="US-WEST")
    forecast = grid.get_forecast(hours=24)

    # Optimize scheduling
    autopilot = Autopilot()
    result = autopilot.optimize_schedule(workload, forecast)

    print(f"Optimal start: {result.optimal_start}")
    print(f"Cost savings: ${result.cost_savings:.2f}")
    print(f"Carbon saved: {result.carbon_savings_kg:.2f} kg")
"""

__version__ = "0.1.0"
__author__ = "Arboric"
__license__ = "MIT"

from arboric.core.models import (
    FleetOptimizationResult,
    GridWindow,
    ScheduleResult,
    Workload,
    WorkloadPriority,
    WorkloadType,
)
from arboric.core.grid_oracle import MockGrid, get_grid
from arboric.core.autopilot import Autopilot, OptimizationConfig, create_autopilot

__all__ = [
    # Models
    "Workload",
    "WorkloadType",
    "WorkloadPriority",
    "GridWindow",
    "ScheduleResult",
    "FleetOptimizationResult",
    # Grid Oracle
    "MockGrid",
    "get_grid",
    # Autopilot
    "Autopilot",
    "OptimizationConfig",
    "create_autopilot",
]
