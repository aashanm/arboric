"""
Tests for Arboric Export Functionality

Tests format detection, JSON/CSV serialization, and file I/O.
"""

import json
import csv
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from arboric.cli.export import (
    ExportError,
    ExportFormat,
    detect_format,
    export_schedule_result,
    export_fleet_result,
    export_forecast,
)
from arboric.core.models import (
    Workload,
    WorkloadType,
    WorkloadPriority,
    ScheduleResult,
    FleetOptimizationResult,
)


class TestFormatDetection:
    """Test format detection from file extensions."""

    def test_detect_json(self):
        """Test JSON format detection."""
        assert detect_format("results.json") == ExportFormat.JSON
        assert detect_format("/path/to/results.json") == ExportFormat.JSON

    def test_detect_csv(self):
        """Test CSV format detection."""
        assert detect_format("results.csv") == ExportFormat.CSV
        assert detect_format("/path/to/results.csv") == ExportFormat.CSV

    def test_detect_unknown(self):
        """Test unknown format returns None."""
        assert detect_format("results.txt") is None
        assert detect_format("results.xml") is None

    def test_detect_stdout(self):
        """Test stdout requires explicit format."""
        assert detect_format("-") is None


class TestScheduleResultExport:
    """Test ScheduleResult export functionality."""

    @pytest.fixture
    def sample_workload(self):
        """Create a sample workload."""
        return Workload(
            name="Test Job",
            duration_hours=4.0,
            power_draw_kw=50.0,
            deadline_hours=12.0,
            workload_type=WorkloadType.ML_TRAINING,
            priority=WorkloadPriority.NORMAL,
        )

    @pytest.fixture
    def sample_schedule_result(self, sample_workload):
        """Create a sample ScheduleResult."""
        baseline_start = datetime(2026, 2, 10, 15, 0, 0)
        optimal_start = baseline_start + timedelta(hours=2.5)

        return ScheduleResult(
            workload=sample_workload,
            optimal_start=optimal_start,
            optimal_end=optimal_start + timedelta(hours=4),
            baseline_start=baseline_start,
            baseline_end=baseline_start + timedelta(hours=4),
            optimized_cost=15.50,
            optimized_carbon_kg=60.0,
            optimized_avg_price=0.0775,
            optimized_avg_carbon=300.0,
            baseline_cost=20.00,
            baseline_carbon_kg=80.0,
            baseline_avg_price=0.10,
            baseline_avg_carbon=400.0,
        )

    def test_export_json_to_file(self, sample_schedule_result, tmp_path):
        """Test JSON export to file."""
        output_file = tmp_path / "result.json"
        export_schedule_result(sample_schedule_result, output_file, ExportFormat.JSON)

        # Verify file exists
        assert output_file.exists()

        # Load and validate JSON structure
        with open(output_file) as f:
            data = json.load(f)

        assert data["command"] == "optimize"
        assert "timestamp" in data
        assert "version" in data
        assert "data" in data

        # Check workload fields
        assert data["data"]["workload"]["name"] == "Test Job"
        assert data["data"]["workload"]["duration_hours"] == 4.0
        assert data["data"]["workload"]["energy_kwh"] == 200.0  # Computed property

        # Check optimization fields
        assert data["data"]["optimization"]["delay_hours"] == 2.5  # Computed property

        # Check savings (computed properties)
        assert data["data"]["metrics"]["savings"]["cost"] == 4.5
        assert data["data"]["metrics"]["savings"]["cost_percent"] == 22.5
        assert data["data"]["metrics"]["savings"]["carbon_kg"] == 20.0

    def test_export_csv_to_file(self, sample_schedule_result, tmp_path):
        """Test CSV export to file."""
        output_file = tmp_path / "result.csv"
        export_schedule_result(sample_schedule_result, output_file, ExportFormat.CSV)

        # Verify file exists
        assert output_file.exists()

        # Load and validate CSV
        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]

        # Check workload fields
        assert row["workload_name"] == "Test Job"
        assert float(row["workload_duration_hours"]) == 4.0
        assert float(row["workload_energy_kwh"]) == 200.0  # Computed property

        # Check computed properties are present
        assert "delay_hours" in row
        assert float(row["delay_hours"]) == 2.5
        assert "cost_savings" in row
        assert float(row["cost_savings"]) == 4.5
        assert "cost_savings_percent" in row
        assert "carbon_savings_kg" in row

    def test_export_json_includes_all_computed_properties(self, sample_schedule_result, tmp_path):
        """Test that JSON export includes all computed properties."""
        output_file = tmp_path / "result.json"
        export_schedule_result(sample_schedule_result, output_file, ExportFormat.JSON)

        with open(output_file) as f:
            data = json.load(f)

        # Check all computed properties are present
        savings = data["data"]["metrics"]["savings"]
        assert "cost" in savings
        assert "cost_percent" in savings
        assert "carbon_kg" in savings
        assert "carbon_percent" in savings

        assert data["data"]["optimization"]["delay_hours"] == 2.5
        assert data["data"]["workload"]["energy_kwh"] == 200.0

    def test_export_to_stdout(self, sample_schedule_result, capsys):
        """Test export to stdout."""
        export_schedule_result(sample_schedule_result, "-", ExportFormat.JSON)

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["command"] == "optimize"
        assert data["data"]["workload"]["name"] == "Test Job"


class TestFleetResultExport:
    """Test FleetOptimizationResult export functionality."""

    @pytest.fixture
    def sample_fleet_result(self):
        """Create a sample FleetOptimizationResult."""
        workloads = []
        schedules = []

        for i in range(3):
            workload = Workload(
                name=f"Job {i+1}",
                duration_hours=2.0,
                power_draw_kw=30.0,
                deadline_hours=12.0,
                workload_type=WorkloadType.ML_TRAINING,
            )
            workloads.append(workload)

            baseline_start = datetime(2026, 2, 10, 15, 0, 0)
            optimal_start = baseline_start + timedelta(hours=i * 1.5)

            schedule = ScheduleResult(
                workload=workload,
                optimal_start=optimal_start,
                optimal_end=optimal_start + timedelta(hours=2),
                baseline_start=baseline_start,
                baseline_end=baseline_start + timedelta(hours=2),
                optimized_cost=10.0 + i,
                optimized_carbon_kg=40.0 + i * 5,
                optimized_avg_price=0.08,
                optimized_avg_carbon=250.0,
                baseline_cost=12.0 + i,
                baseline_carbon_kg=50.0 + i * 5,
                baseline_avg_price=0.10,
                baseline_avg_carbon=300.0,
            )
            schedules.append(schedule)

        return FleetOptimizationResult(
            schedules=schedules,
            total_cost_savings=sum(s.cost_savings for s in schedules),
            total_carbon_savings_kg=sum(s.carbon_savings_kg for s in schedules),
            total_workloads=len(schedules),
        )

    def test_export_fleet_json(self, sample_fleet_result, tmp_path):
        """Test fleet JSON export."""
        output_file = tmp_path / "fleet.json"
        export_fleet_result(sample_fleet_result, output_file, ExportFormat.JSON)

        with open(output_file) as f:
            data = json.load(f)

        assert data["command"] == "demo"
        assert "summary" in data["data"]
        assert "schedules" in data["data"]

        # Check summary
        summary = data["data"]["summary"]
        assert summary["total_workloads"] == 3
        assert "total_cost_savings" in summary
        assert "total_carbon_savings_kg" in summary
        assert "average_cost_savings_percent" in summary  # Computed property

        # Check schedules
        assert len(data["data"]["schedules"]) == 3
        assert data["data"]["schedules"][0]["workload"]["name"] == "Job 1"

    def test_export_fleet_csv_has_summary_and_detail_rows(self, sample_fleet_result, tmp_path):
        """Test fleet CSV has summary row + detail rows."""
        output_file = tmp_path / "fleet.csv"
        export_fleet_result(sample_fleet_result, output_file, ExportFormat.CSV)

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should have 1 summary row + 3 detail rows
        assert len(rows) == 4

        # First row should be summary
        assert rows[0]["record_type"] == "summary"
        assert rows[0]["fleet_total_workloads"] == "3"

        # Remaining rows should be details
        for i in range(1, 4):
            assert rows[i]["record_type"] == "detail"
            assert rows[i]["workload_name"] == f"Job {i}"


class TestForecastExport:
    """Test forecast export functionality."""

    @pytest.fixture
    def sample_forecast(self):
        """Create a sample forecast DataFrame."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        hours = 24

        data = {
            "timestamp": [now + timedelta(hours=i) for i in range(hours)],
            "co2_intensity": [300.0 + i * 10 for i in range(hours)],
            "price": [0.10 + i * 0.01 for i in range(hours)],
            "renewable_percentage": [50.0] * hours,
            "region": ["US-WEST"] * hours,
            "confidence": [1.0] * hours,
        }

        df = pd.DataFrame(data)
        df = df.set_index("timestamp")
        return df

    def test_export_forecast_json(self, sample_forecast, tmp_path):
        """Test forecast JSON export includes metadata."""
        output_file = tmp_path / "forecast.json"
        export_forecast(sample_forecast, "US-WEST", 24, output_file, ExportFormat.JSON)

        with open(output_file) as f:
            data = json.load(f)

        assert data["command"] == "forecast"
        assert "metadata" in data
        assert data["metadata"]["region"] == "US-WEST"
        assert data["metadata"]["hours"] == 24
        assert data["metadata"]["data_points"] == 24

        assert "data" in data
        assert len(data["data"]) == 24
        assert "timestamp" in data["data"][0]
        assert "co2_intensity" in data["data"][0]

    def test_export_forecast_csv(self, sample_forecast, tmp_path):
        """Test forecast CSV export."""
        output_file = tmp_path / "forecast.csv"
        export_forecast(sample_forecast, "US-WEST", 24, output_file, ExportFormat.CSV)

        # Load and verify
        df = pd.read_csv(output_file, index_col=0, parse_dates=True)

        assert len(df) == 24
        assert "co2_intensity" in df.columns
        assert "price" in df.columns
        assert "renewable_percentage" in df.columns


class TestErrorHandling:
    """Test error handling in export functions."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample result for testing."""
        workload = Workload(
            name="Test",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )

        baseline_start = datetime(2026, 2, 10, 15, 0, 0)

        return ScheduleResult(
            workload=workload,
            optimal_start=baseline_start,
            optimal_end=baseline_start + timedelta(hours=2),
            baseline_start=baseline_start,
            baseline_end=baseline_start + timedelta(hours=2),
            optimized_cost=10.0,
            optimized_carbon_kg=40.0,
            optimized_avg_price=0.08,
            optimized_avg_carbon=250.0,
            baseline_cost=12.0,
            baseline_carbon_kg=50.0,
            baseline_avg_price=0.10,
            baseline_avg_carbon=300.0,
        )

    def test_invalid_path_raises_export_error(self, sample_result):
        """Test that invalid paths raise ExportError."""
        with pytest.raises(ExportError):
            export_schedule_result(
                sample_result, "/nonexistent/invalid/path/file.json", ExportFormat.JSON
            )

    def test_permission_error_wrapped(self, sample_result, tmp_path, monkeypatch):
        """Test that permission errors are wrapped in ExportError."""
        output_file = tmp_path / "result.json"

        # Create file and make it read-only
        output_file.touch()
        output_file.chmod(0o444)

        with pytest.raises(ExportError, match="Permission denied"):
            export_schedule_result(sample_result, output_file, ExportFormat.JSON)
