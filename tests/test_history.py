"""Tests for historical optimization tracking."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from arboric.core.history import HistoryStore
from arboric.core.models import ScheduleResult, Workload, WorkloadType


@pytest.fixture
def temp_history_db(tmp_path):
    """Create a temporary history database."""
    db_path = tmp_path / "test_history.db"
    return HistoryStore(db_path)


@pytest.fixture
def sample_result():
    """Create a sample ScheduleResult for testing."""
    now = datetime.now(timezone.utc)
    workload = Workload(
        name="Test Job",
        duration_hours=6.0,
        power_draw_kw=120.0,
        deadline_hours=24.0,
        workload_type=WorkloadType.ML_TRAINING,
    )
    return ScheduleResult(
        workload=workload,
        optimal_start=now + timedelta(hours=4),
        optimal_end=now + timedelta(hours=10),
        baseline_start=now,
        baseline_end=now + timedelta(hours=6),
        optimized_cost=64.80,
        optimized_carbon_kg=79.92,
        optimized_avg_price=0.09,
        optimized_avg_carbon=111.0,
        baseline_cost=110.37,
        baseline_carbon_kg=273.60,
        baseline_avg_price=0.153,
        baseline_avg_carbon=380.0,
    )


class TestHistoryStore:
    """Test HistoryStore CRUD operations."""

    def test_record_inserts_row(self, temp_history_db, sample_result):
        """Test that record() inserts a row."""
        temp_history_db.record(sample_result, region="US-WEST", data_source="mockgrid")

        rows = temp_history_db.query(limit=100)
        assert len(rows) == 1
        assert rows[0]["workload_name"] == "Test Job"
        assert rows[0]["region"] == "US-WEST"
        assert rows[0]["data_source"] == "mockgrid"

    def test_query_returns_newest_first(self, temp_history_db, sample_result):
        """Test that query() returns rows newest first."""
        # Insert 3 jobs with different UUIDs and names
        temp_history_db.record(sample_result, region="US-WEST")

        # Create new workload with different UUID and name
        result2 = ScheduleResult(
            workload=Workload(
                name="Second Job",
                duration_hours=6.0,
                power_draw_kw=120.0,
                deadline_hours=24.0,
                workload_type=WorkloadType.ML_TRAINING,
            ),
            optimal_start=sample_result.optimal_start,
            optimal_end=sample_result.optimal_end,
            baseline_start=sample_result.baseline_start,
            baseline_end=sample_result.baseline_end,
            optimized_cost=sample_result.optimized_cost,
            optimized_carbon_kg=sample_result.optimized_carbon_kg,
            optimized_avg_price=sample_result.optimized_avg_price,
            optimized_avg_carbon=sample_result.optimized_avg_carbon,
            baseline_cost=sample_result.baseline_cost,
            baseline_carbon_kg=sample_result.baseline_carbon_kg,
            baseline_avg_price=sample_result.baseline_avg_price,
            baseline_avg_carbon=sample_result.baseline_avg_carbon,
        )
        temp_history_db.record(result2, region="US-WEST")

        result3 = ScheduleResult(
            workload=Workload(
                name="Third Job",
                duration_hours=6.0,
                power_draw_kw=120.0,
                deadline_hours=24.0,
                workload_type=WorkloadType.ML_TRAINING,
            ),
            optimal_start=sample_result.optimal_start,
            optimal_end=sample_result.optimal_end,
            baseline_start=sample_result.baseline_start,
            baseline_end=sample_result.baseline_end,
            optimized_cost=sample_result.optimized_cost,
            optimized_carbon_kg=sample_result.optimized_carbon_kg,
            optimized_avg_price=sample_result.optimized_avg_price,
            optimized_avg_carbon=sample_result.optimized_avg_carbon,
            baseline_cost=sample_result.baseline_cost,
            baseline_carbon_kg=sample_result.baseline_carbon_kg,
            baseline_avg_price=sample_result.baseline_avg_price,
            baseline_avg_carbon=sample_result.baseline_avg_carbon,
        )
        temp_history_db.record(result3, region="US-WEST")

        rows = temp_history_db.query(limit=100)
        assert len(rows) == 3
        assert rows[0]["workload_name"] == "Third Job"  # newest
        assert rows[1]["workload_name"] == "Second Job"
        assert rows[2]["workload_name"] == "Test Job"  # oldest

    def test_query_respects_limit(self, temp_history_db, sample_result):
        """Test that query() respects limit parameter."""
        # Create 10 separate results with unique IDs
        for i in range(10):
            result = ScheduleResult(
                workload=Workload(
                    name=f"Job {i}",
                    duration_hours=6.0,
                    power_draw_kw=120.0,
                    deadline_hours=24.0,
                    workload_type=WorkloadType.ML_TRAINING,
                ),
                optimal_start=sample_result.optimal_start,
                optimal_end=sample_result.optimal_end,
                baseline_start=sample_result.baseline_start,
                baseline_end=sample_result.baseline_end,
                optimized_cost=sample_result.optimized_cost,
                optimized_carbon_kg=sample_result.optimized_carbon_kg,
                optimized_avg_price=sample_result.optimized_avg_price,
                optimized_avg_carbon=sample_result.optimized_avg_carbon,
                baseline_cost=sample_result.baseline_cost,
                baseline_carbon_kg=sample_result.baseline_carbon_kg,
                baseline_avg_price=sample_result.baseline_avg_price,
                baseline_avg_carbon=sample_result.baseline_avg_carbon,
            )
            temp_history_db.record(result, region="US-WEST")

        rows = temp_history_db.query(limit=5)
        assert len(rows) == 5

    def test_query_filters_by_region(self, temp_history_db, sample_result):
        """Test that query() filters by region."""
        temp_history_db.record(sample_result, region="US-WEST")

        # Create new result with different UUID
        result2 = ScheduleResult(
            workload=Workload(
                name="East Job",
                duration_hours=6.0,
                power_draw_kw=120.0,
                deadline_hours=24.0,
                workload_type=WorkloadType.ML_TRAINING,
            ),
            optimal_start=sample_result.optimal_start,
            optimal_end=sample_result.optimal_end,
            baseline_start=sample_result.baseline_start,
            baseline_end=sample_result.baseline_end,
            optimized_cost=sample_result.optimized_cost,
            optimized_carbon_kg=sample_result.optimized_carbon_kg,
            optimized_avg_price=sample_result.optimized_avg_price,
            optimized_avg_carbon=sample_result.optimized_avg_carbon,
            baseline_cost=sample_result.baseline_cost,
            baseline_carbon_kg=sample_result.baseline_carbon_kg,
            baseline_avg_price=sample_result.baseline_avg_price,
            baseline_avg_carbon=sample_result.baseline_avg_carbon,
        )
        temp_history_db.record(result2, region="US-EAST")

        rows_west = temp_history_db.query(region="US-WEST")
        rows_east = temp_history_db.query(region="US-EAST")

        assert len(rows_west) == 1
        assert rows_west[0]["workload_name"] == "Test Job"

        assert len(rows_east) == 1
        assert rows_east[0]["workload_name"] == "East Job"

    def test_query_filters_by_since_days(self, temp_history_db, sample_result):
        """Test that query() filters by since_days."""
        # Insert one run now
        temp_history_db.record(sample_result, region="US-WEST")

        # Query for last 1 day — should return 1
        rows = temp_history_db.query(since_days=1)
        assert len(rows) == 1

        # Query for last 1 hour — should return 0 (too old)
        rows = temp_history_db.query(since_days=0)
        assert len(rows) == 0

    def test_aggregate_computes_totals(self, temp_history_db, sample_result):
        """Test that aggregate() computes correct totals."""
        temp_history_db.record(sample_result, region="US-WEST")

        # Create second result with different UUID
        result2 = ScheduleResult(
            workload=Workload(
                name="Second Job",
                duration_hours=6.0,
                power_draw_kw=120.0,
                deadline_hours=24.0,
                workload_type=WorkloadType.ML_TRAINING,
            ),
            optimal_start=sample_result.optimal_start,
            optimal_end=sample_result.optimal_end,
            baseline_start=sample_result.baseline_start,
            baseline_end=sample_result.baseline_end,
            optimized_cost=sample_result.optimized_cost,
            optimized_carbon_kg=sample_result.optimized_carbon_kg,
            optimized_avg_price=sample_result.optimized_avg_price,
            optimized_avg_carbon=sample_result.optimized_avg_carbon,
            baseline_cost=sample_result.baseline_cost,
            baseline_carbon_kg=sample_result.baseline_carbon_kg,
            baseline_avg_price=sample_result.baseline_avg_price,
            baseline_avg_carbon=sample_result.baseline_avg_carbon,
        )
        temp_history_db.record(result2, region="US-WEST")

        agg = temp_history_db.aggregate()

        assert agg["total_jobs"] == 2
        assert agg["total_cost_savings"] == pytest.approx(45.57 * 2, rel=0.01)
        assert agg["total_carbon_savings_kg"] == pytest.approx(193.68 * 2, rel=0.01)
        assert agg["avg_cost_savings_percent"] > 0
        assert agg["avg_carbon_savings_percent"] > 0

    def test_aggregate_with_no_data_returns_zeros(self, temp_history_db):
        """Test that aggregate() returns zeros when no data."""
        agg = temp_history_db.aggregate()

        assert agg["total_jobs"] == 0
        assert agg["total_cost_savings"] == 0.0
        assert agg["total_carbon_savings_kg"] == 0.0
        assert agg["best_region"] is None
        assert agg["top_workload"] is None

    def test_aggregate_finds_best_region(self, temp_history_db, sample_result):
        """Test that aggregate() identifies best region."""
        # Insert 3 in US-WEST, 1 in US-EAST
        for _ in range(3):
            temp_history_db.record(sample_result, region="US-WEST")

        sample_result.workload.name = "East Job"
        temp_history_db.record(sample_result, region="US-EAST")

        agg = temp_history_db.aggregate()
        assert agg["best_region"] == "US-WEST"

    def test_aggregate_finds_top_workload(self, temp_history_db, sample_result):
        """Test that aggregate() identifies top workload."""
        # Insert 2 "Training" and 1 "Pipeline"
        sample_result.workload.name = "LLM Training"
        temp_history_db.record(sample_result, region="US-WEST")
        temp_history_db.record(sample_result, region="US-WEST")

        sample_result.workload.name = "ETL Pipeline"
        temp_history_db.record(sample_result, region="US-WEST")

        agg = temp_history_db.aggregate()
        assert agg["top_workload"] == "LLM Training"

    def test_clear_deletes_all_rows(self, temp_history_db, sample_result):
        """Test that clear() deletes all history."""
        temp_history_db.record(sample_result, region="US-WEST")

        # Create second result with different UUID
        result2 = ScheduleResult(
            workload=Workload(
                name="Second Job",
                duration_hours=6.0,
                power_draw_kw=120.0,
                deadline_hours=24.0,
                workload_type=WorkloadType.ML_TRAINING,
            ),
            optimal_start=sample_result.optimal_start,
            optimal_end=sample_result.optimal_end,
            baseline_start=sample_result.baseline_start,
            baseline_end=sample_result.baseline_end,
            optimized_cost=sample_result.optimized_cost,
            optimized_carbon_kg=sample_result.optimized_carbon_kg,
            optimized_avg_price=sample_result.optimized_avg_price,
            optimized_avg_carbon=sample_result.optimized_avg_carbon,
            baseline_cost=sample_result.baseline_cost,
            baseline_carbon_kg=sample_result.baseline_carbon_kg,
            baseline_avg_price=sample_result.baseline_avg_price,
            baseline_avg_carbon=sample_result.baseline_avg_carbon,
        )
        temp_history_db.record(result2, region="US-WEST")

        rows = temp_history_db.query(limit=100)
        assert len(rows) == 2

        temp_history_db.clear()

        rows = temp_history_db.query(limit=100)
        assert len(rows) == 0

    def test_record_fails_silently_on_bad_path(self, sample_result):
        """Test that record() fails silently if DB path is inaccessible."""
        # Use a path we can't write to
        store = HistoryStore(Path("/nonexistent/path/history.db"))

        # Should not raise an exception
        store.record(sample_result, region="US-WEST")

    def test_duplicate_ids_are_ignored(self, temp_history_db, sample_result):
        """Test that duplicate IDs don't insert duplicate rows."""
        # Insert same result twice (same UUID)
        temp_history_db.record(sample_result, region="US-WEST")
        temp_history_db.record(sample_result, region="US-WEST")

        rows = temp_history_db.query(limit=100)
        # Should only have 1 row due to PRIMARY KEY constraint
        assert len(rows) == 1
