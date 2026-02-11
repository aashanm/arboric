"""
Arboric Autopilot

The optimization engine that schedules workloads to minimize cost
and carbon emissions. Implements a rolling-window algorithm that
evaluates all feasible start times within a workload's deadline.

Architecture:
- Designed for single-workload optimization (this file)
- Fleet orchestration handled at CLI layer
- Future: constraint satisfaction for multi-workload dependencies
"""

from datetime import timedelta
from uuid import UUID

import pandas as pd

from arboric.core.models import (
    FleetOptimizationResult,
    ScheduleResult,
    Workload,
    WorkloadPriority,
)

# Optimization weights (configurable per deployment)
# Cost-first strategy: prioritize dollar savings, use carbon as tie-breaker
DEFAULT_PRICE_WEIGHT = 0.7
DEFAULT_CARBON_WEIGHT = 0.3


class OptimizationConfig:
    """Configuration for the optimization algorithm."""

    def __init__(
        self,
        price_weight: float = DEFAULT_PRICE_WEIGHT,
        carbon_weight: float = DEFAULT_CARBON_WEIGHT,
        min_delay_hours: float = 0,
        prefer_continuous: bool = True,
    ):
        """
        Args:
            price_weight: Weight for cost optimization (0-1)
            carbon_weight: Weight for carbon optimization (0-1)
            min_delay_hours: Minimum delay before starting (e.g., for prep time)
            prefer_continuous: Prefer continuous windows over fragmented
        """
        if not (0 <= price_weight <= 1 and 0 <= carbon_weight <= 1):
            raise ValueError("Weights must be between 0 and 1")
        if abs(price_weight + carbon_weight - 1.0) > 0.01:
            raise ValueError("Weights must sum to 1.0")

        self.price_weight = price_weight
        self.carbon_weight = carbon_weight
        self.min_delay_hours = min_delay_hours
        self.prefer_continuous = prefer_continuous


class Autopilot:
    """
    The Arboric scheduling brain.

    Scans forecast windows to identify optimal execution times
    based on a weighted combination of cost and carbon metrics.
    """

    def __init__(self, config: OptimizationConfig | None = None):
        self.config = config or OptimizationConfig()
        self._optimization_log: list[str] = []

    def _log(self, message: str):
        """Internal logging for debugging and display."""
        self._optimization_log.append(message)

    def get_log(self) -> list[str]:
        """Get optimization log messages."""
        return self._optimization_log.copy()

    def clear_log(self):
        """Clear the optimization log."""
        self._optimization_log = []

    def _calculate_window_score(
        self,
        forecast_slice: pd.DataFrame,
        workload: Workload,
    ) -> tuple[float, float, float]:
        """
        Calculate the composite score for a potential execution window.

        Returns:
            Tuple of (composite_score, total_cost, total_carbon_kg)
        """
        if forecast_slice.empty:
            return float("inf"), 0, 0

        # Calculate metrics for this window
        avg_price = forecast_slice["price"].mean()
        avg_carbon = forecast_slice["co2_intensity"].mean()

        # Total cost = price * energy
        energy_kwh = workload.energy_kwh
        total_cost = avg_price * energy_kwh

        # Total carbon = intensity * energy / 1000 (convert g to kg)
        total_carbon_kg = (avg_carbon * energy_kwh) / 1000

        # Normalize for scoring (scale to comparable ranges)
        # Price: assume $0.30/kWh is "bad", $0.05/kWh is "good"
        price_normalized = min(avg_price / 0.30, 1.0) * 100

        # Carbon: assume 600 gCO2/kWh is "bad", 100 gCO2/kWh is "good"
        carbon_normalized = min(avg_carbon / 600, 1.0) * 100

        # Weighted composite score (lower is better)
        composite = (
            price_normalized * self.config.price_weight
            + carbon_normalized * self.config.carbon_weight
        )

        return composite, total_cost, total_carbon_kg

    def optimize_schedule(
        self,
        workload: Workload,
        forecast_df: pd.DataFrame,
    ) -> ScheduleResult:
        """
        Find the optimal start time for a workload.

        Algorithm:
        1. Calculate baseline metrics (immediate start)
        2. Scan all feasible start times within deadline
        3. For each window, calculate composite score
        4. Return the window with minimum score

        Args:
            workload: The workload to schedule
            forecast_df: Grid forecast DataFrame with timestamp index

        Returns:
            ScheduleResult with optimal vs baseline comparison
        """
        self.clear_log()
        self._log(f"Initializing optimization for: {workload.name}")

        if forecast_df.empty:
            raise ValueError("Forecast data is empty")

        # Ensure datetime index
        if not isinstance(forecast_df.index, pd.DatetimeIndex):
            forecast_df.index = pd.to_datetime(forecast_df.index)

        # Get time resolution from forecast
        if len(forecast_df) > 1:
            resolution = forecast_df.index[1] - forecast_df.index[0]
            resolution_hours = resolution.total_seconds() / 3600
        else:
            resolution_hours = 1.0

        # Calculate number of windows needed for workload
        windows_needed = max(1, int(workload.duration_hours / resolution_hours))

        baseline_start = forecast_df.index[0]
        deadline = baseline_start + timedelta(hours=workload.deadline_hours)

        self._log(f"Workload duration: {workload.duration_hours}h ({windows_needed} windows)")
        self._log(f"Deadline: {deadline.strftime('%Y-%m-%d %H:%M')}")
        self._log(f"Scanning {len(forecast_df)} forecast windows...")

        # Priority handling
        if workload.priority == WorkloadPriority.CRITICAL:
            self._log("CRITICAL priority - forcing immediate execution")
            # For critical workloads, return baseline as optimal
            baseline_slice = forecast_df.iloc[:windows_needed]
            _, baseline_cost, baseline_carbon = self._calculate_window_score(
                baseline_slice, workload
            )
            return ScheduleResult(
                workload=workload,
                optimal_start=baseline_start,
                optimal_end=baseline_start + timedelta(hours=workload.duration_hours),
                baseline_start=baseline_start,
                baseline_end=baseline_start + timedelta(hours=workload.duration_hours),
                optimized_cost=baseline_cost,
                optimized_carbon_kg=baseline_carbon,
                optimized_avg_price=baseline_slice["price"].mean(),
                optimized_avg_carbon=baseline_slice["co2_intensity"].mean(),
                baseline_cost=baseline_cost,
                baseline_carbon_kg=baseline_carbon,
                baseline_avg_price=baseline_slice["price"].mean(),
                baseline_avg_carbon=baseline_slice["co2_intensity"].mean(),
            )

        # Calculate baseline (immediate start)
        baseline_slice = forecast_df.iloc[:windows_needed]
        baseline_score, baseline_cost, baseline_carbon = self._calculate_window_score(
            baseline_slice, workload
        )
        baseline_avg_price = baseline_slice["price"].mean()
        baseline_avg_carbon = baseline_slice["co2_intensity"].mean()

        self._log(
            f"Baseline score: {baseline_score:.2f} (${baseline_cost:.2f}, {baseline_carbon:.2f}kg CO2)"
        )

        # Scan all feasible start times
        best_score = float("inf")
        best_start_idx = 0
        best_cost = baseline_cost
        best_carbon = baseline_carbon

        # Minimum delay handling
        min_delay_windows = int(self.config.min_delay_hours / resolution_hours)

        # Calculate latest possible start (must finish by deadline)
        max_start_idx = len(forecast_df) - windows_needed

        # Also limit by deadline
        for idx in range(len(forecast_df)):
            potential_end = forecast_df.index[idx] + timedelta(hours=workload.duration_hours)
            if potential_end > deadline:
                max_start_idx = min(max_start_idx, idx - 1)
                break

        self._log(f"Feasible start window: index {min_delay_windows} to {max_start_idx}")

        scores_by_hour = []

        for start_idx in range(min_delay_windows, max_start_idx + 1):
            end_idx = start_idx + windows_needed
            if end_idx > len(forecast_df):
                break

            window_slice = forecast_df.iloc[start_idx:end_idx]
            score, cost, carbon = self._calculate_window_score(window_slice, workload)
            scores_by_hour.append((start_idx, score, cost, carbon))

            if score < best_score:
                best_score = score
                best_start_idx = start_idx
                best_cost = cost
                best_carbon = carbon

        # Find optimal window details
        optimal_start = forecast_df.index[best_start_idx]
        optimal_end = optimal_start + timedelta(hours=workload.duration_hours)
        optimal_slice = forecast_df.iloc[best_start_idx : best_start_idx + windows_needed]

        self._log(f"Optimal start: {optimal_start.strftime('%Y-%m-%d %H:%M')}")
        self._log(f"Optimal score: {best_score:.2f} (${best_cost:.2f}, {best_carbon:.2f}kg CO2)")

        if best_start_idx > 0:
            delay_hours = (optimal_start - baseline_start).total_seconds() / 3600
            self._log(f"Delaying workload by {delay_hours:.1f} hours for optimization")

        return ScheduleResult(
            workload=workload,
            optimal_start=optimal_start,
            optimal_end=optimal_end,
            baseline_start=baseline_start,
            baseline_end=baseline_start + timedelta(hours=workload.duration_hours),
            optimized_cost=best_cost,
            optimized_carbon_kg=best_carbon,
            optimized_avg_price=optimal_slice["price"].mean(),
            optimized_avg_carbon=optimal_slice["co2_intensity"].mean(),
            baseline_cost=baseline_cost,
            baseline_carbon_kg=baseline_carbon,
            baseline_avg_price=baseline_avg_price,
            baseline_avg_carbon=baseline_avg_carbon,
        )

    def optimize_fleet(
        self,
        workloads: list[Workload],
        forecast_df: pd.DataFrame,
    ) -> FleetOptimizationResult:
        """
        Optimize scheduling for multiple workloads with dependency constraints.

        Algorithm:
        1. Validates dependency graph for cycles and invalid references
        2. Sorts workloads topologically (prerequisites first)
        3. Optimizes each workload while respecting dependency constraints
        4. Ensures dependent workloads start after prerequisites complete

        Args:
            workloads: List of workloads (may have dependencies)
            forecast_df: Grid forecast DataFrame

        Returns:
            FleetOptimizationResult with constraint-aware schedules

        Raises:
            DependencyGraphError: If dependency graph is invalid
            ValueError: If constraints cannot be satisfied
        """
        from arboric.core.constraints import DependencyGraph

        # Handle empty workload list
        if not workloads:
            return FleetOptimizationResult(
                schedules=[],
                total_cost_savings=0.0,
                total_carbon_savings_kg=0.0,
                total_workloads=0,
                dependency_order=[],
            )

        # Build and validate dependency graph
        dep_graph = DependencyGraph(workloads)
        execution_order = dep_graph.topological_sort()

        self._log(f"Optimizing {len(workloads)} workloads with dependencies")

        schedules: list[ScheduleResult] = []
        completed_schedules: dict[UUID, ScheduleResult] = {}
        total_cost_savings = 0.0
        total_carbon_savings = 0.0

        # Process workloads in topological order
        for workload_id in execution_order:
            workload = dep_graph.workloads[workload_id]
            level = dep_graph.get_workload_level(workload_id)

            self._log(
                f"Processing {workload.name} "
                f"(level {level}, {len(workload.dependencies)} dependencies)"
            )

            # Apply dependency constraints to forecast
            constrained_forecast = self._apply_dependency_constraints(
                workload=workload,
                forecast_df=forecast_df,
                completed_schedules=completed_schedules,
            )

            # Optimize with constrained forecast
            result = self.optimize_schedule(workload, constrained_forecast)

            # Validate constraints satisfied
            self._validate_schedule_constraints(
                result=result,
                workload=workload,
                completed_schedules=completed_schedules,
            )

            schedules.append(result)
            completed_schedules[workload_id] = result
            total_cost_savings += result.cost_savings
            total_carbon_savings += result.carbon_savings_kg

        return FleetOptimizationResult(
            schedules=schedules,
            total_cost_savings=total_cost_savings,
            total_carbon_savings_kg=total_carbon_savings,
            total_workloads=len(workloads),
            dependency_order=execution_order,
        )

    def _apply_dependency_constraints(
        self,
        workload: Workload,
        forecast_df: pd.DataFrame,
        completed_schedules: dict[UUID, ScheduleResult],
    ) -> pd.DataFrame:
        """
        Create forecast window that enforces dependency timing constraints.

        Shifts forecast so workload can only be scheduled after all
        prerequisites complete (plus any minimum delays).

        Args:
            workload: Workload to schedule
            forecast_df: Original forecast
            completed_schedules: Already-scheduled prerequisites

        Returns:
            Constrained forecast DataFrame

        Raises:
            ValueError: If constraints cannot be satisfied
        """
        if not workload.dependencies:
            return forecast_df

        baseline_start = forecast_df.index[0]
        earliest_start = baseline_start

        # Calculate earliest start based on all dependencies
        for dep in workload.dependencies:
            prereq_id = dep.source_workload_id
            prereq_schedule = completed_schedules.get(prereq_id)

            if prereq_schedule is None:
                raise ValueError(
                    f"{workload.name} depends on {prereq_id}, but that "
                    "workload has not been scheduled. This indicates a bug."
                )

            if dep.depends_on_completion:
                # Must wait for prerequisite completion + delay
                constraint_time = prereq_schedule.optimal_end + timedelta(hours=dep.min_delay_hours)
                earliest_start = max(earliest_start, constraint_time)

        # Check if deadline can be satisfied
        workload_deadline = baseline_start + timedelta(hours=workload.deadline_hours)
        latest_possible_end = earliest_start + timedelta(hours=workload.duration_hours)

        if latest_possible_end > workload_deadline:
            prereq_names = [
                completed_schedules[dep.source_workload_id].workload.name
                for dep in workload.dependencies
            ]
            raise ValueError(
                f"Cannot satisfy deadline for '{workload.name}'. "
                f"Dependencies on {prereq_names} force start at "
                f"{earliest_start.strftime('%Y-%m-%d %H:%M')}, but workload "
                f"must complete by {workload_deadline.strftime('%Y-%m-%d %H:%M')}. "
                f"Consider extending deadline or removing dependencies."
            )

        # Shift forecast if needed
        if earliest_start > baseline_start:
            time_shift = earliest_start - baseline_start
            self._log(
                f"Dependency constraints shift {workload.name} start by "
                f"{time_shift.total_seconds() / 3600:.1f} hours"
            )

            # Create shifted forecast
            shifted_forecast = forecast_df.copy()
            shifted_forecast.index = forecast_df.index + time_shift
            shifted_forecast = shifted_forecast[shifted_forecast.index >= earliest_start]

            if shifted_forecast.empty:
                raise ValueError(
                    f"Cannot schedule {workload.name}. Prerequisites complete at "
                    f"{earliest_start}, but forecast ends at {forecast_df.index[-1]}. "
                    f"Provide longer forecast window."
                )

            return shifted_forecast

        return forecast_df

    def _validate_schedule_constraints(
        self,
        result: ScheduleResult,
        workload: Workload,
        completed_schedules: dict[UUID, ScheduleResult],
    ) -> None:
        """
        Validate that schedule satisfies all dependency constraints.

        Raises ValueError if constraints violated.

        Args:
            result: The schedule result to validate
            workload: The workload being scheduled
            completed_schedules: Already-scheduled workloads
        """
        for dep in workload.dependencies:
            prereq_schedule = completed_schedules[dep.source_workload_id]

            if dep.depends_on_completion:
                min_start = prereq_schedule.optimal_end + timedelta(hours=dep.min_delay_hours)

                if result.optimal_start < min_start:
                    raise ValueError(
                        f"Constraint violation: {workload.name} starts at "
                        f"{result.optimal_start}, but must wait until {min_start}"
                    )

    def generate_tradeoff_frontier(
        self, workload: Workload, forecast_df: pd.DataFrame, num_points: int = 10
    ) -> list[dict]:
        """
        Generate cost/carbon tradeoff frontier using weight-blending.

        Varies cost/carbon weights from (100% cost, 0% carbon) to (0% cost, 100% carbon),
        finding the optimal window for each weight combination. Returns distinct points
        showing different scheduling tradeoff options.

        Args:
            workload: The workload to analyze
            forecast_df: Grid forecast DataFrame
            num_points: Number of tradeoff points to return (default 10)

        Returns:
            List of dicts with keys: start_time, cost, carbon, cost_savings, carbon_savings
        """
        self.clear_log()
        self._log(f"Generating tradeoff frontier for: {workload.name}")

        if forecast_df.empty:
            raise ValueError("Forecast data is empty")

        # Ensure datetime index
        if not isinstance(forecast_df.index, pd.DatetimeIndex):
            forecast_df.index = pd.to_datetime(forecast_df.index)

        # Get time resolution from forecast
        if len(forecast_df) > 1:
            resolution = forecast_df.index[1] - forecast_df.index[0]
            resolution_hours = resolution.total_seconds() / 3600
        else:
            resolution_hours = 1.0

        windows_needed = max(1, int(workload.duration_hours / resolution_hours))
        baseline_start = forecast_df.index[0]
        deadline = baseline_start + timedelta(hours=workload.deadline_hours)

        # Calculate baseline
        baseline_slice = forecast_df.iloc[:windows_needed]
        _, baseline_cost, baseline_carbon = self._calculate_window_score(baseline_slice, workload)

        # Find max feasible start index
        max_start_idx = len(forecast_df) - windows_needed
        for idx in range(len(forecast_df)):
            potential_end = forecast_df.index[idx] + timedelta(hours=workload.duration_hours)
            if potential_end > deadline:
                max_start_idx = min(max_start_idx, idx - 1)
                break

        # Pre-calculate all windows with their metrics
        all_windows = []
        for start_idx in range(max_start_idx + 1):
            end_idx = start_idx + windows_needed
            if end_idx > len(forecast_df):
                break

            window_slice = forecast_df.iloc[start_idx:end_idx]
            _, cost, carbon = self._calculate_window_score(window_slice, workload)

            all_windows.append(
                {
                    "start_idx": start_idx,
                    "start_time": forecast_df.index[start_idx],
                    "cost": cost,
                    "carbon": carbon,
                    "cost_savings": baseline_cost - cost,
                    "carbon_savings": baseline_carbon - carbon,
                    "avg_price": window_slice["price"].mean(),
                    "avg_carbon": window_slice["co2_intensity"].mean(),
                }
            )

        # Normalize costs and carbon for weight-blending
        if all_windows:
            min_cost = min(w["cost"] for w in all_windows)
            max_cost = max(w["cost"] for w in all_windows)
            min_carbon = min(w["carbon"] for w in all_windows)
            max_carbon = max(w["carbon"] for w in all_windows)

            cost_range = max_cost - min_cost if max_cost > min_cost else 1.0
            carbon_range = max_carbon - min_carbon if max_carbon > min_carbon else 1.0

            # Generate tradeoff points by varying weights
            selected_points = {}  # Use dict to track unique windows by start_idx

            for i in range(num_points):
                # Weight varies from 100% cost to 0% cost (and opposite for carbon)
                alpha = i / (num_points - 1) if num_points > 1 else 0.5
                cost_weight = 1.0 - alpha
                carbon_weight = alpha

                # Find window with best score for this weight combination
                best_window = None
                best_score = float("inf")

                for window in all_windows:
                    # Normalize metrics to 0-1 range
                    norm_cost = (window["cost"] - min_cost) / cost_range
                    norm_carbon = (window["carbon"] - min_carbon) / carbon_range

                    # Weighted score (lower is better)
                    score = (norm_cost * cost_weight) + (norm_carbon * carbon_weight)

                    if score < best_score:
                        best_score = score
                        best_window = window

                if best_window:
                    # Store by start_idx to avoid duplicates
                    selected_points[best_window["start_idx"]] = best_window

            # Convert dict to sorted list and return
            result = sorted(selected_points.values(), key=lambda x: x["cost"])
            return result

        return []


def create_autopilot(
    price_weight: float = DEFAULT_PRICE_WEIGHT,
    carbon_weight: float = DEFAULT_CARBON_WEIGHT,
) -> Autopilot:
    """Factory function to create an Autopilot instance."""
    config = OptimizationConfig(
        price_weight=price_weight,
        carbon_weight=carbon_weight,
    )
    return Autopilot(config=config)
