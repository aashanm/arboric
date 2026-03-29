"""
Arboric Data Models

Pydantic models for workload definitions and grid forecast windows.
Designed for validation, serialization, and type safety across the platform.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_CLOUD_PROVIDERS = frozenset({"aws", "gcp", "azure"})


class WorkloadPriority(str, Enum):
    """Priority levels for workload scheduling."""

    CRITICAL = "critical"  # Must run immediately
    HIGH = "high"  # Prefer sooner
    NORMAL = "normal"  # Flexible timing
    LOW = "low"  # Maximum flexibility for optimization


class WorkloadType(str, Enum):
    """Classification of workload types for optimization heuristics."""

    ML_TRAINING = "ml_training"
    ML_INFERENCE = "ml_inference"
    ETL_PIPELINE = "etl_pipeline"
    BATCH_PROCESSING = "batch_processing"
    DATA_ANALYTICS = "data_analytics"
    GENERIC = "generic"


class WorkloadDependency(BaseModel):
    """
    Represents a dependency relationship between workloads.

    A workload with dependencies cannot start until its prerequisite
    workloads complete (and any minimum delay elapses).

    Example:
        If Job B depends on Job A:
        - source_workload_id = A's UUID (the prerequisite)
        - This dependency is stored in Job B's dependencies list
    """

    source_workload_id: UUID = Field(
        ..., description="UUID of the prerequisite workload that must complete first"
    )
    depends_on_completion: bool = Field(
        default=True, description="Whether to wait for prerequisite completion (vs just start)"
    )
    min_delay_hours: float = Field(
        default=0.0,
        ge=0.0,
        le=168.0,
        description="Minimum hours to wait after prerequisite completes",
    )


class Workload(BaseModel):
    """
    Represents a schedulable compute workload.

    The Arboric autopilot uses these attributes to determine optimal
    execution windows based on grid conditions.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique workload identifier")
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable workload name")
    duration_hours: float = Field(..., gt=0, le=168, description="Expected runtime in hours")
    power_draw_kw: float | None = Field(
        default=None,
        gt=0,
        le=10000,
        description="Average power consumption in kilowatts. Auto-resolved from instance profile when instance_type is set.",
    )
    deadline_hours: float = Field(
        ..., gt=0, le=720, description="Must complete within this many hours"
    )
    workload_type: WorkloadType = Field(
        default=WorkloadType.GENERIC, description="Workload classification"
    )
    priority: WorkloadPriority = Field(
        default=WorkloadPriority.NORMAL, description="Scheduling priority"
    )
    description: str | None = Field(default=None, max_length=512)
    dependencies: list["WorkloadDependency"] = Field(
        default=[], description="List of prerequisite workloads that must complete first"
    )
    instance_type: str | None = Field(
        default=None,
        description=(
            "Cloud instance type for spot pricing. "
            "Examples: 'p3.8xlarge' (AWS), 'a2-highgpu-4g' (GCP), 'Standard_NC24s_v3' (Azure). "
            "Must be provided together with cloud_provider."
        ),
    )
    cloud_provider: str | None = Field(
        default=None,
        description="Cloud provider: 'aws', 'gcp', or 'azure'. Must be provided with instance_type.",
    )

    @field_validator("deadline_hours")
    @classmethod
    def deadline_must_exceed_duration(cls, v, info):
        """Ensure deadline provides enough time to complete the workload."""
        if "duration_hours" in info.data and v < info.data["duration_hours"]:
            raise ValueError("deadline_hours must be >= duration_hours")
        return v

    @model_validator(mode="after")
    def validate_instance_fields(self) -> "Workload":
        """Ensure instance_type and cloud_provider are either both set or both None. Auto-resolve power_draw_kw from instance profile if not set."""
        has_type = self.instance_type is not None
        has_provider = self.cloud_provider is not None
        if has_type != has_provider:
            raise ValueError("instance_type and cloud_provider must both be set or both be None.")
        if has_provider:
            normalized = self.cloud_provider.lower()
            if normalized not in VALID_CLOUD_PROVIDERS:
                raise ValueError(
                    f"cloud_provider must be one of {sorted(VALID_CLOUD_PROVIDERS)}, got {self.cloud_provider!r}"
                )
            object.__setattr__(self, "cloud_provider", normalized)

        # Auto-resolve power_draw_kw from instance profile if not set
        if self.power_draw_kw is None:
            if self.instance_type and self.cloud_provider:
                from arboric.core.grid_oracle import DEFAULT_INSTANCE, INSTANCE_PROFILES

                prof = INSTANCE_PROFILES.get(self.cloud_provider, {}).get(
                    self.instance_type, DEFAULT_INSTANCE
                )
                object.__setattr__(self, "power_draw_kw", prof["typical_power_kw"])
            else:
                object.__setattr__(self, "power_draw_kw", 100.0)  # neutral fallback

        return self

    @property
    def energy_kwh(self) -> float:
        """Total energy consumption for the workload."""
        return self.power_draw_kw * self.duration_hours

    def __str__(self) -> str:
        result = f"Workload({self.name}, {self.duration_hours}h @ {self.power_draw_kw}kW)"
        if self.instance_type:
            result += f" [{self.instance_type} ({self.cloud_provider.upper()})]"
        return result


class GridWindow(BaseModel):
    """
    Represents a single time window in the grid forecast.

    Each window captures the carbon intensity and spot instance pricing
    at a specific point in time, enabling cost/carbon optimization.
    """

    timestamp: datetime = Field(..., description="Start time of this forecast window")
    co2_intensity: float = Field(..., ge=0, le=2000, description="Carbon intensity in gCO2/kWh")
    price: float = Field(..., ge=0, le=500, description="Cloud spot instance rate in $/hr")
    renewable_percentage: float = Field(
        default=0, ge=0, le=100, description="Percentage of renewable sources"
    )
    region: str = Field(default="US-WEST", description="Grid region identifier")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Forecast confidence score")

    @property
    def is_green_window(self) -> bool:
        """Returns True if this is a low-carbon window (< 200 gCO2/kWh)."""
        return self.co2_intensity < 200

    @property
    def is_cheap_window(self) -> bool:
        """Returns True if this is a low-price window (< $12.00/hr spot rate)."""
        return self.price < 12.0

    @property
    def composite_score(self) -> float:
        """
        Combined optimization score (lower is better).
        Weighted: 60% price, 40% carbon.
        Normalized to 0-100 scale.
        """
        price_normalized = (
            min(self.price / 25.0, 1.0) * 100
        )  # Normalize to $25/hr on-demand ceiling
        carbon_normalized = min(self.co2_intensity / 800, 1.0) * 100  # Normalize to 800 gCO2 max
        return (price_normalized * 0.6) + (carbon_normalized * 0.4)

    def __str__(self) -> str:
        return f"GridWindow({self.timestamp.strftime('%H:%M')}: ${self.price:.2f}/hr, {self.co2_intensity:.0f}gCO2)"


class ScheduleResult(BaseModel):
    """
    Result of the Arboric optimization algorithm.

    Contains both the optimal schedule and comparative metrics
    against a baseline (immediate execution) scenario.
    """

    workload: Workload
    optimal_start: datetime
    optimal_end: datetime
    baseline_start: datetime
    baseline_end: datetime

    # Optimized metrics
    optimized_cost: float = Field(..., ge=0, description="Total cost at optimal time ($)")
    optimized_carbon_kg: float = Field(..., ge=0, description="Total carbon at optimal time (kg)")
    optimized_avg_price: float = Field(..., ge=0, description="Average price during optimal window")
    optimized_avg_carbon: float = Field(
        ..., ge=0, description="Average carbon during optimal window"
    )

    # Baseline metrics (immediate execution)
    baseline_cost: float = Field(..., ge=0, description="Total cost if run immediately ($)")
    baseline_carbon_kg: float = Field(..., ge=0, description="Total carbon if run immediately (kg)")
    baseline_avg_price: float = Field(..., ge=0, description="Average price during baseline window")
    baseline_avg_carbon: float = Field(
        ..., ge=0, description="Average carbon during baseline window"
    )

    # Instance pricing metadata
    on_demand_rate_per_hr: float | None = Field(
        default=None,
        description="On-demand rate for the scheduled instance type ($/hr), if instance was specified.",
    )

    # Constraint enforcement flag
    cost_constrained: bool = Field(
        default=False,
        description="True if cost constraint was applied (composite score recommended a more expensive window, so minimum-cost window was selected instead).",
    )

    @property
    def cost_savings(self) -> float:
        """Dollar savings from optimization."""
        return self.baseline_cost - self.optimized_cost

    @property
    def carbon_savings_kg(self) -> float:
        """Carbon savings from optimization in kg."""
        return self.baseline_carbon_kg - self.optimized_carbon_kg

    @property
    def cost_savings_percent(self) -> float:
        """Percentage cost reduction."""
        if self.baseline_cost == 0:
            return 0.0
        return (self.cost_savings / self.baseline_cost) * 100

    @property
    def carbon_savings_percent(self) -> float:
        """Percentage carbon reduction."""
        if self.baseline_carbon_kg == 0:
            return 0.0
        return (self.carbon_savings_kg / self.baseline_carbon_kg) * 100

    @property
    def delay_hours(self) -> float:
        """Hours delayed from immediate start."""
        return (self.optimal_start - self.baseline_start).total_seconds() / 3600

    @property
    def optimal_start_clock(self) -> str:
        """Clock time string for optimal start, e.g. '2:00 AM'. Portable across macOS/Linux/Windows."""
        return self.optimal_start.strftime("%I:%M %p").lstrip("0")

    @property
    def deadline_slack_hours(self) -> float:
        """Hours of slack remaining after scheduled completion."""
        return self.workload.deadline_hours - self.delay_hours - self.workload.duration_hours


class RegionScheduleEntry(BaseModel):
    """Single region's best schedule in a multi-region comparison."""

    region: str
    optimal_start_clock: str
    delay_hours: float
    avg_spot_price: float
    avg_carbon: float
    optimized_cost: float
    optimized_carbon_kg: float
    cost_savings: float
    cost_savings_percent: float
    carbon_savings_kg: float
    carbon_savings_percent: float
    on_demand_rate_per_hr: float | None = None


class RegionComparisonResult(BaseModel):
    """Result of running temporal optimization across all regions."""

    workload_name: str
    duration_hours: float
    entries: list[RegionScheduleEntry]
    cheapest_region: str
    cleanest_region: str
    generated_at: datetime = Field(default_factory=datetime.now)

    @property
    def best_cost_entry(self) -> RegionScheduleEntry:
        """Region with lowest cost."""
        return min(self.entries, key=lambda e: e.optimized_cost)

    @property
    def best_carbon_entry(self) -> RegionScheduleEntry:
        """Region with lowest carbon."""
        return min(self.entries, key=lambda e: e.avg_carbon)


class FleetOptimizationResult(BaseModel):
    """Aggregated results for multiple workloads."""

    schedules: list[ScheduleResult]
    total_cost_savings: float
    total_carbon_savings_kg: float
    total_workloads: int
    optimization_timestamp: datetime = Field(default_factory=datetime.now)
    dependency_order: list[UUID] = Field(
        default=[], description="Topologically sorted workload execution order"
    )

    @property
    def average_cost_savings_percent(self) -> float:
        """Average cost savings across all workloads."""
        if not self.schedules:
            return 0.0
        return sum(s.cost_savings_percent for s in self.schedules) / len(self.schedules)

    @property
    def average_carbon_savings_percent(self) -> float:
        """Average carbon savings across all workloads."""
        if not self.schedules:
            return 0.0
        return sum(s.carbon_savings_percent for s in self.schedules) / len(self.schedules)
