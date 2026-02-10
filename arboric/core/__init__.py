"""
Arboric Core Package

Core functionality including optimization algorithms, data models,
and grid forecasting.
"""

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
from arboric.core.config import (
    ArboricConfig,
    OptimizationSettings,
    DefaultWorkloadSettings,
    APISettings,
    CLISettings,
    get_config,
    reset_config,
)

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
    # Configuration
    "ArboricConfig",
    "OptimizationSettings",
    "DefaultWorkloadSettings",
    "APISettings",
    "CLISettings",
    "get_config",
    "reset_config",
]
