"""
API request models.

Pydantic models for validating incoming API requests.
"""

from pydantic import BaseModel, Field, model_validator

from arboric.core.models import Workload


class OptimizationConfigRequest(BaseModel):
    """API request model for optimization configuration."""

    cost_weight: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Weight for cost optimization (0-1)"
    )
    carbon_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight for carbon optimization (0-1)"
    )
    min_delay_hours: float = Field(
        default=0.0, ge=0.0, description="Minimum delay before starting workload"
    )
    prefer_continuous: bool = Field(default=True, description="Prefer continuous execution windows")

    @model_validator(mode="after")
    def validate_weights(self) -> "OptimizationConfigRequest":
        """Validate that weights sum to 1.0."""
        total = self.cost_weight + self.carbon_weight
        if abs(total - 1.0) > 0.001:  # Allow small floating point errors
            raise ValueError(f"cost_weight and carbon_weight must sum to 1.0, got {total}")
        return self


class OptimizeRequest(BaseModel):
    """Request model for single workload optimization."""

    workload: Workload = Field(..., description="Workload to optimize")
    region: str = Field(
        default="US-WEST",
        description="Grid region for optimization, or 'all' for cross-region comparison",
    )
    optimization_config: OptimizationConfigRequest | None = Field(
        None, description="Optional optimization configuration override"
    )
    forecast_hours: int | None = Field(
        None, ge=1, le=168, description="Forecast horizon in hours (1-168)"
    )
    runs_per_week: float | None = Field(
        None,
        ge=0.01,
        le=168,
        description="Job frequency for annual savings projection (e.g. 1.0=weekly, 5.0=weekdays, 0.14=monthly). Omit to skip annual projection.",
    )


class FleetOptimizeRequest(BaseModel):
    """Request model for fleet optimization."""

    workloads: list[Workload] = Field(
        ..., min_length=1, max_length=100, description="List of workloads to optimize (1-100)"
    )
    region: str = Field(default="US-WEST", description="Grid region for optimization")
    optimization_config: OptimizationConfigRequest | None = Field(
        None, description="Optional optimization configuration override"
    )
    forecast_hours: int | None = Field(
        None, ge=1, le=168, description="Forecast horizon in hours (1-168)"
    )
    runs_per_week: float | None = Field(
        None,
        ge=0.01,
        le=168,
        description="Job frequency for annual savings projection. Omit to skip annual projection.",
    )
