"""
Tests for Arboric Autopilot

Tests optimization algorithm, scheduling logic, and fleet management.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from arboric.core.autopilot import Autopilot, OptimizationConfig
from arboric.core.grid_oracle import MockGrid
from arboric.core.models import Workload, WorkloadPriority, WorkloadType


class TestOptimizationConfig:
    """Test cases for OptimizationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = OptimizationConfig()
        assert config.price_weight == 0.7
        assert config.carbon_weight == 0.3
        assert config.min_delay_hours == 0
        assert config.prefer_continuous is True

    def test_custom_weights(self):
        """Test custom weight configuration."""
        config = OptimizationConfig(price_weight=0.5, carbon_weight=0.5)
        assert config.price_weight == 0.5
        assert config.carbon_weight == 0.5

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            OptimizationConfig(price_weight=0.6, carbon_weight=0.5)

    def test_weights_must_be_in_range(self):
        """Test that weights must be between 0 and 1."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            OptimizationConfig(price_weight=1.5, carbon_weight=-0.5)


class TestAutopilot:
    """Test cases for Autopilot scheduling engine."""

    @pytest.fixture
    def simple_forecast(self):
        """Create a simple test forecast."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        hours = 24

        data = {
            "timestamp": [now + timedelta(hours=i) for i in range(hours)],
            "co2_intensity": [400.0 - (i % 12) * 20 for i in range(hours)],  # Varies by hour
            "price": [0.15 - (i % 12) * 0.01 for i in range(hours)],  # Varies by hour
            "renewable_percentage": [50.0] * hours,
            "region": ["US-WEST"] * hours,
            "confidence": [1.0] * hours,
        }

        df = pd.DataFrame(data)
        df = df.set_index("timestamp")
        return df

    @pytest.fixture
    def simple_workload(self):
        """Create a simple test workload."""
        return Workload(
            name="Test Workload",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
            workload_type=WorkloadType.ML_TRAINING,
        )

    def test_autopilot_initialization(self):
        """Test basic autopilot initialization."""
        autopilot = Autopilot()
        assert autopilot.config is not None
        assert autopilot.config.price_weight == 0.7
        assert autopilot.config.carbon_weight == 0.3

    def test_autopilot_with_custom_config(self):
        """Test autopilot with custom configuration."""
        config = OptimizationConfig(price_weight=0.5, carbon_weight=0.5)
        autopilot = Autopilot(config=config)
        assert autopilot.config.price_weight == 0.5

    def test_optimize_schedule_returns_result(self, simple_workload, simple_forecast):
        """Test that optimize_schedule returns a valid ScheduleResult."""
        autopilot = Autopilot()
        result = autopilot.optimize_schedule(simple_workload, simple_forecast)

        assert result.workload == simple_workload
        assert result.optimal_start is not None
        assert result.optimal_end is not None
        assert result.baseline_start is not None
        assert result.baseline_end is not None

    def test_optimize_schedule_finds_cheaper_window(self):
        """Test that optimization finds a cheaper execution window."""
        # Create a forecast with clear price variation
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        data = {
            "timestamp": [now + timedelta(hours=i) for i in range(24)],
            "co2_intensity": [300.0] * 24,  # Constant carbon
            "price": [
                0.20 if i < 6 else 0.08 for i in range(24)
            ],  # Expensive first 6h, cheap after
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [1.0] * 24,
        }
        forecast = pd.DataFrame(data).set_index("timestamp")

        workload = Workload(
            name="Price Test",
            duration_hours=3.0,
            power_draw_kw=100.0,
            deadline_hours=18.0,
        )

        autopilot = Autopilot()
        result = autopilot.optimize_schedule(workload, forecast)

        # Should delay to find cheaper window
        assert result.delay_hours > 0
        assert result.cost_savings > 0
        assert result.optimized_cost < result.baseline_cost

    def test_optimize_schedule_finds_greener_window(self):
        """Test that optimization considers carbon intensity."""
        # Create a forecast with clear carbon variation
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        data = {
            "timestamp": [now + timedelta(hours=i) for i in range(24)],
            "co2_intensity": [
                600.0 if i < 6 else 200.0 for i in range(24)
            ],  # Dirty first 6h, green after
            "price": [0.12] * 24,  # Constant price
            "renewable_percentage": [30.0 if i < 6 else 70.0 for i in range(24)],
            "region": ["US-WEST"] * 24,
            "confidence": [1.0] * 24,
        }
        forecast = pd.DataFrame(data).set_index("timestamp")

        workload = Workload(
            name="Carbon Test",
            duration_hours=3.0,
            power_draw_kw=100.0,
            deadline_hours=18.0,
        )

        # Use carbon-focused optimization
        config = OptimizationConfig(price_weight=0.2, carbon_weight=0.8)
        autopilot = Autopilot(config=config)
        result = autopilot.optimize_schedule(workload, forecast)

        # Should delay to find greener window
        assert result.delay_hours > 0
        assert result.carbon_savings_kg > 0
        assert result.optimized_carbon_kg < result.baseline_carbon_kg

    def test_critical_priority_runs_immediately(self, simple_workload, simple_forecast):
        """Test that CRITICAL priority workloads run immediately."""
        workload = Workload(
            name="Critical Job",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
            priority=WorkloadPriority.CRITICAL,
        )

        autopilot = Autopilot()
        result = autopilot.optimize_schedule(workload, simple_forecast)

        # Critical workloads should not be delayed
        assert result.delay_hours == 0
        assert result.optimal_start == result.baseline_start

    def test_respects_deadline_constraint(self):
        """Test that optimization respects the deadline constraint."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        data = {
            "timestamp": [now + timedelta(hours=i) for i in range(48)],
            "co2_intensity": [300.0] * 48,
            "price": [0.20 if i < 30 else 0.05 for i in range(48)],  # Very cheap window at hour 30+
            "renewable_percentage": [50.0] * 48,
            "region": ["US-WEST"] * 48,
            "confidence": [1.0] * 48,
        }
        forecast = pd.DataFrame(data).set_index("timestamp")

        workload = Workload(
            name="Deadline Test",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,  # Must complete by hour 12
        )

        autopilot = Autopilot()
        result = autopilot.optimize_schedule(workload, forecast)

        # Should not schedule beyond deadline (even though hour 30+ is cheaper)
        deadline = result.baseline_start + timedelta(hours=12)
        assert result.optimal_end <= deadline

    def test_optimize_fleet(self):
        """Test fleet optimization for multiple workloads."""
        grid = MockGrid(region="US-WEST", seed=42)
        forecast = grid.get_forecast(hours=24)

        workloads = [
            Workload(
                name=f"Job {i}",
                duration_hours=2.0,
                power_draw_kw=30.0,
                deadline_hours=12.0,
            )
            for i in range(3)
        ]

        autopilot = Autopilot()
        fleet_result = autopilot.optimize_fleet(workloads, forecast)

        assert fleet_result.total_workloads == 3
        assert len(fleet_result.schedules) == 3
        assert fleet_result.total_cost_savings >= 0  # May be positive or zero
        assert fleet_result.total_carbon_savings_kg >= 0

    def test_empty_forecast_raises_error(self, simple_workload):
        """Test that empty forecast raises an error."""
        autopilot = Autopilot()
        empty_forecast = pd.DataFrame()

        with pytest.raises(ValueError, match="Forecast data is empty"):
            autopilot.optimize_schedule(simple_workload, empty_forecast)

    def test_optimization_log(self, simple_workload, simple_forecast):
        """Test that optimization generates log messages."""
        autopilot = Autopilot()
        autopilot.optimize_schedule(simple_workload, simple_forecast)

        log = autopilot.get_log()
        assert len(log) > 0
        assert any("Initializing optimization" in msg for msg in log)

    def test_log_clear(self, simple_workload, simple_forecast):
        """Test that log can be cleared."""
        autopilot = Autopilot()
        autopilot.optimize_schedule(simple_workload, simple_forecast)

        assert len(autopilot.get_log()) > 0

        autopilot.clear_log()
        assert len(autopilot.get_log()) == 0

    def test_realistic_scenario_with_mock_grid(self):
        """Test a realistic optimization scenario using MockGrid."""
        grid = MockGrid(region="US-WEST", seed=123)
        forecast = grid.get_forecast(hours=24)

        workload = Workload(
            name="LLM Training",
            duration_hours=6.0,
            power_draw_kw=120.0,
            deadline_hours=24.0,
            workload_type=WorkloadType.ML_TRAINING,
        )

        autopilot = Autopilot()
        result = autopilot.optimize_schedule(workload, forecast)

        # Verify result has all required attributes
        assert result.workload == workload
        assert result.optimized_cost > 0
        assert result.optimized_carbon_kg > 0
        assert result.baseline_cost > 0
        assert result.baseline_carbon_kg > 0

        # Cost and carbon should be non-negative
        assert result.optimized_cost >= 0
        assert result.optimized_carbon_kg >= 0

        # Optimal should be as good or better than baseline
        assert (
            result.optimized_cost <= result.baseline_cost
            or abs(result.optimized_cost - result.baseline_cost) < 0.01
        )
