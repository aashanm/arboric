"""
Tests for Arboric Data Models

Tests validation, computed properties, and business logic for
Workload, GridWindow, and ScheduleResult models.
"""

from datetime import datetime, timedelta

import pytest

from arboric.core.models import (
    GridWindow,
    ScheduleResult,
    Workload,
    WorkloadDependency,
    WorkloadPriority,
    WorkloadType,
)


class TestWorkload:
    """Test cases for Workload model."""

    def test_workload_creation(self):
        """Test basic workload creation with valid parameters."""
        workload = Workload(
            name="Test Job",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )
        assert workload.name == "Test Job"
        assert workload.duration_hours == 4.0
        assert workload.power_draw_kw == 50.0
        assert workload.deadline_hours == 12.0

    def test_workload_energy_calculation(self):
        """Test that energy_kwh is correctly calculated."""
        workload = Workload(
            name="Energy Test",
            duration_hours=5.0,
            power_draw_kw=100.0,
            deadline_hours=10.0,
        )
        assert workload.energy_kwh == 500.0  # 5h * 100kW

    def test_workload_deadline_validation(self):
        """Test that deadline must be >= duration."""
        with pytest.raises(ValueError, match="deadline_hours must be >= duration_hours"):
            Workload(
                name="Invalid Job",
                duration_hours=10.0,
                power_draw_kw=50.0,
                deadline_hours=5.0,  # Invalid: deadline < duration
            )

    def test_workload_validation_positive_values(self):
        """Test that duration and power must be positive."""
        with pytest.raises(ValueError):
            Workload(
                name="Bad Duration",
                duration_hours=-1.0,
                power_draw_kw=50.0,
                deadline_hours=10.0,
            )

        with pytest.raises(ValueError):
            Workload(
                name="Bad Power",
                duration_hours=5.0,
                power_draw_kw=0.0,
                deadline_hours=10.0,
            )

    def test_workload_defaults(self):
        """Test default values for optional fields."""
        workload = Workload(
            name="Defaults Test",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )
        assert workload.workload_type == WorkloadType.GENERIC
        assert workload.priority == WorkloadPriority.NORMAL
        assert workload.description is None

    def test_workload_with_no_dependencies(self):
        """Test workload defaults to empty dependencies list."""
        workload = Workload(
            name="No Dependencies",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )
        assert workload.dependencies == []

    def test_workload_with_single_dependency(self):
        """Test workload with one dependency."""
        from uuid import UUID

        dep_id = UUID("12345678-1234-5678-1234-567812345678")
        dependency = WorkloadDependency(
            source_workload_id=dep_id,
            depends_on_completion=True,
            min_delay_hours=0.0,
        )
        workload = Workload(
            name="Dependent Job",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
            dependencies=[dependency],
        )
        assert len(workload.dependencies) == 1
        assert workload.dependencies[0].source_workload_id == dep_id

    def test_workload_with_multiple_dependencies(self):
        """Test workload with multiple dependencies."""
        dep1 = WorkloadDependency(source_workload_id="11111111-1111-1111-1111-111111111111")
        dep2 = WorkloadDependency(source_workload_id="22222222-2222-2222-2222-222222222222")
        workload = Workload(
            name="Multi-Dependent",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
            dependencies=[dep1, dep2],
        )
        assert len(workload.dependencies) == 2


class TestWorkloadDependency:
    """Test cases for WorkloadDependency model."""

    def test_valid_dependency_creation(self):
        """Test creating a valid dependency."""
        dep = WorkloadDependency(
            source_workload_id="12345678-1234-5678-1234-567812345678",
            depends_on_completion=True,
            min_delay_hours=1.5,
        )
        assert str(dep.source_workload_id) == "12345678-1234-5678-1234-567812345678"
        assert dep.depends_on_completion is True
        assert dep.min_delay_hours == 1.5

    def test_dependency_defaults(self):
        """Test default values for dependency fields."""
        dep = WorkloadDependency(source_workload_id="12345678-1234-5678-1234-567812345678")
        assert dep.depends_on_completion is True
        assert dep.min_delay_hours == 0.0

    def test_negative_min_delay_rejected(self):
        """Test that negative min_delay_hours is rejected."""
        with pytest.raises(ValueError):
            WorkloadDependency(
                source_workload_id="12345678-1234-5678-1234-567812345678",
                min_delay_hours=-1.0,
            )

    def test_excessive_min_delay_rejected(self):
        """Test that min_delay_hours > 168 is rejected."""
        with pytest.raises(ValueError):
            WorkloadDependency(
                source_workload_id="12345678-1234-5678-1234-567812345678",
                min_delay_hours=169.0,
            )

    def test_min_delay_boundary_values(self):
        """Test boundary values for min_delay_hours."""
        # Test 0.0 (minimum valid)
        dep_min = WorkloadDependency(
            source_workload_id="12345678-1234-5678-1234-567812345678",
            min_delay_hours=0.0,
        )
        assert dep_min.min_delay_hours == 0.0

        # Test 168.0 (maximum valid)
        dep_max = WorkloadDependency(
            source_workload_id="12345678-1234-5678-1234-567812345678",
            min_delay_hours=168.0,
        )
        assert dep_max.min_delay_hours == 168.0


class TestGridWindow:
    """Test cases for GridWindow model."""

    def test_grid_window_creation(self):
        """Test basic grid window creation."""
        timestamp = datetime.now()
        window = GridWindow(
            timestamp=timestamp,
            co2_intensity=300.0,
            price=0.12,
            renewable_percentage=40.0,
        )
        assert window.timestamp == timestamp
        assert window.co2_intensity == 300.0
        assert window.price == 0.12
        assert window.renewable_percentage == 40.0

    def test_grid_window_is_green_window(self):
        """Test green window detection (< 200 gCO2/kWh)."""
        green_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=150.0,
            price=0.10,
        )
        assert green_window.is_green_window is True

        dirty_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=400.0,
            price=0.15,
        )
        assert dirty_window.is_green_window is False

    def test_grid_window_is_cheap_window(self):
        """Test cheap window detection (< $0.08/kWh)."""
        cheap_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=300.0,
            price=0.07,
        )
        assert cheap_window.is_cheap_window is True

        expensive_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=300.0,
            price=0.15,
        )
        assert expensive_window.is_cheap_window is False

    def test_grid_window_composite_score(self):
        """Test composite score calculation (lower is better)."""
        good_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=100.0,  # Low carbon
            price=0.05,  # Low price
        )
        bad_window = GridWindow(
            timestamp=datetime.now(),
            co2_intensity=600.0,  # High carbon
            price=0.25,  # High price
        )
        assert good_window.composite_score < bad_window.composite_score

    def test_grid_window_validation(self):
        """Test validation constraints."""
        # Carbon intensity must be >= 0
        with pytest.raises(ValueError):
            GridWindow(
                timestamp=datetime.now(),
                co2_intensity=-10.0,
                price=0.10,
            )

        # Price must be >= 0
        with pytest.raises(ValueError):
            GridWindow(
                timestamp=datetime.now(),
                co2_intensity=300.0,
                price=-0.05,
            )


class TestScheduleResult:
    """Test cases for ScheduleResult model."""

    def test_schedule_result_savings_calculations(self):
        """Test cost and carbon savings calculations."""
        workload = Workload(
            name="Test",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )

        baseline_start = datetime.now()
        optimal_start = baseline_start + timedelta(hours=3)

        result = ScheduleResult(
            workload=workload,
            optimal_start=optimal_start,
            optimal_end=optimal_start + timedelta(hours=4),
            baseline_start=baseline_start,
            baseline_end=baseline_start + timedelta(hours=4),
            optimized_cost=15.0,
            optimized_carbon_kg=60.0,
            optimized_avg_price=0.075,
            optimized_avg_carbon=300.0,
            baseline_cost=20.0,
            baseline_carbon_kg=80.0,
            baseline_avg_price=0.10,
            baseline_avg_carbon=400.0,
        )

        assert result.cost_savings == 5.0  # $20 - $15
        assert result.carbon_savings_kg == 20.0  # 80kg - 60kg
        assert result.cost_savings_percent == 25.0  # 5/20 * 100
        assert result.carbon_savings_percent == 25.0  # 20/80 * 100

    def test_schedule_result_delay_calculation(self):
        """Test delay hours calculation."""
        workload = Workload(
            name="Test",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )

        baseline_start = datetime.now()
        optimal_start = baseline_start + timedelta(hours=5)

        result = ScheduleResult(
            workload=workload,
            optimal_start=optimal_start,
            optimal_end=optimal_start + timedelta(hours=4),
            baseline_start=baseline_start,
            baseline_end=baseline_start + timedelta(hours=4),
            optimized_cost=15.0,
            optimized_carbon_kg=60.0,
            optimized_avg_price=0.075,
            optimized_avg_carbon=300.0,
            baseline_cost=20.0,
            baseline_carbon_kg=80.0,
            baseline_avg_price=0.10,
            baseline_avg_carbon=400.0,
        )

        assert result.delay_hours == 5.0
