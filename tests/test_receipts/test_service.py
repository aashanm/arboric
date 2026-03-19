"""Tests for receipt service orchestration."""

from datetime import datetime

import pandas as pd

from arboric.core.config import ArboricConfig, OptimizationSettings
from arboric.core.models import ScheduleResult, Workload, WorkloadType
from arboric.receipts.service import generate_receipt
from arboric.receipts.signing import verify_receipt


def test_generate_receipt_returns_tuple():
    """generate_receipt() returns (CarbonReceipt, bytes) tuple."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    # Mock forecast DataFrame
    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0 + (i % 6) * 50 for i in range(24)],
            "price": [0.08 + (i % 4) * 0.05 for i in range(24)],
            "renewable_percentage": [30.0 + (i % 8) * 8 for i in range(24)],
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, pdf_bytes = generate_receipt(schedule, forecast_df, config)

    assert receipt is not None
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_generate_receipt_pdf_size_reasonable():
    """Generated PDF size should be > 1000 bytes."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0 + (i % 6) * 50 for i in range(24)],
            "price": [0.08 + (i % 4) * 0.05 for i in range(24)],
            "renewable_percentage": [30.0 + (i % 8) * 8 for i in range(24)],
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, pdf_bytes = generate_receipt(schedule, forecast_df, config)

    assert len(pdf_bytes) > 1000


def test_moer_source_mock_simulation_when_no_live_data():
    """moer_data_source is 'mock_simulation' when config.live_data.provider is None."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0] * 24,
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    assert receipt.moer_data_source == "mock_simulation"


def test_moer_source_live_when_configured():
    """moer_data_source is 'live_emissions_provider' when config.live_data is enabled."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0] * 24,
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(
        optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3),
    )
    # Enable live external emissions data
    config.live_data.enabled = True
    config.live_data.provider = "external_emissions_provider"

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    assert receipt.moer_data_source == "live_emissions_provider"


def test_hourly_moer_length_matches_window():
    """hourly_moer list length matches the optimal execution window duration (in hours)."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),  # 4 hours
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0] * 24,
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    # 4-hour window = 4 hourly entries
    assert len(receipt.hourly_moer) == 4


def test_carbon_kg_for_hour_computation():
    """carbon_kg_for_hour is computed correctly: co2_intensity * power_draw_kw / 1000."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    # Hour 12: 400.0 gCO2/kWh
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0 if i != 12 else 400.0 for i in range(24)],
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    # Hour 12 (first entry): 400.0 * 100.0 / 1000 = 40.0 kg
    assert receipt.hourly_moer[0].carbon_kg_for_hour == 40.0


def test_receipt_signature_populated_after_generation():
    """Receipt signature is populated and valid after generation."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [300.0] * 24,
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    assert receipt.signature is not None
    assert receipt.signature.algorithm == "ECDSA-P256-SHA256"
    assert verify_receipt(receipt) is True


def test_forecast_window_sliced_correctly():
    """Forecast window is sliced to only include optimal_start to optimal_end rows."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=2.0,
        deadline_hours=24.0,
    )

    schedule = ScheduleResult(
        workload=workload,
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 20, 0),
        optimal_start=datetime(2025, 1, 1, 13, 0),  # Only hours 13-14
        optimal_end=datetime(2025, 1, 1, 15, 0),
        baseline_cost=150.0,
        optimized_cost=100.0,
        baseline_carbon_kg=100.0,
        optimized_carbon_kg=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
    )

    dates = pd.date_range("2025-01-01 00:00", periods=24, freq="h")
    # All hours use intensity, but we should only see hours 13-14 in receipt
    forecast_df = pd.DataFrame(
        {
            "co2_intensity": [100.0 + (i * 10) for i in range(24)],  # 100, 110, 120, ... 330
            "price": [0.10] * 24,
            "renewable_percentage": [50.0] * 24,
            "region": ["US-WEST"] * 24,
            "confidence": [0.9] * 24,
        },
        index=dates,
    )

    config = ArboricConfig(optimization=OptimizationSettings(cost_weight=0.7, carbon_weight=0.3))

    receipt, _ = generate_receipt(schedule, forecast_df, config)

    # Should only have 2 entries (hours 13-14)
    assert len(receipt.hourly_moer) == 2
    # Hour 13: co2_intensity = 100 + (13 * 10) = 230
    assert receipt.hourly_moer[0].co2_intensity == 230.0
    # Hour 14: co2_intensity = 100 + (14 * 10) = 240
    assert receipt.hourly_moer[1].co2_intensity == 240.0
