"""Tests for PDF generation."""

from datetime import datetime

import pytest

from arboric.core.models import Workload, WorkloadType
from arboric.receipts.models import CarbonReceipt, HourlyMOEREntry

# Skip entire module if cryptography is not available
try:
    from arboric.receipts.pdf_generator import generate_receipt_pdf
    from arboric.receipts.signing import sign_receipt
except ImportError:
    pytest.skip("cryptography not installed", allow_module_level=True)


def test_generate_receipt_pdf_returns_bytes():
    """generate_receipt_pdf() returns bytes."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )
    receipt = CarbonReceipt(
        moer_data_source="mock_simulation",
        workload=workload,
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimized_cost=100.0,
        baseline_cost=150.0,
        cost_savings=50.0,
        cost_savings_percent=33.33,
        optimized_carbon_kg=50.0,
        baseline_carbon_kg=100.0,
        carbon_savings_kg=50.0,
        carbon_savings_percent=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
        cost_weight=0.7,
        carbon_weight=0.3,
        hourly_moer=[],
        signature=sign_receipt(
            CarbonReceipt(
                moer_data_source="mock_simulation",
                workload=workload,
                optimal_start=datetime(2025, 1, 1, 12, 0),
                optimal_end=datetime(2025, 1, 1, 16, 0),
                baseline_start=datetime(2025, 1, 1, 18, 0),
                baseline_end=datetime(2025, 1, 1, 22, 0),
                optimized_cost=100.0,
                baseline_cost=150.0,
                cost_savings=50.0,
                cost_savings_percent=33.33,
                optimized_carbon_kg=50.0,
                baseline_carbon_kg=100.0,
                carbon_savings_kg=50.0,
                carbon_savings_percent=50.0,
                optimized_avg_price=0.10,
                baseline_avg_price=0.15,
                optimized_avg_carbon=300.0,
                baseline_avg_carbon=400.0,
                cost_weight=0.7,
                carbon_weight=0.3,
                hourly_moer=[],
            )
        ),
    )

    pdf_bytes = generate_receipt_pdf(receipt)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_generate_receipt_pdf_starts_with_magic_bytes():
    """PDF output starts with %PDF- magic bytes."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )
    receipt = CarbonReceipt(
        moer_data_source="mock_simulation",
        workload=workload,
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimized_cost=100.0,
        baseline_cost=150.0,
        cost_savings=50.0,
        cost_savings_percent=33.33,
        optimized_carbon_kg=50.0,
        baseline_carbon_kg=100.0,
        carbon_savings_kg=50.0,
        carbon_savings_percent=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
        cost_weight=0.7,
        carbon_weight=0.3,
        hourly_moer=[],
        signature=sign_receipt(
            CarbonReceipt(
                moer_data_source="mock_simulation",
                workload=workload,
                optimal_start=datetime(2025, 1, 1, 12, 0),
                optimal_end=datetime(2025, 1, 1, 16, 0),
                baseline_start=datetime(2025, 1, 1, 18, 0),
                baseline_end=datetime(2025, 1, 1, 22, 0),
                optimized_cost=100.0,
                baseline_cost=150.0,
                cost_savings=50.0,
                cost_savings_percent=33.33,
                optimized_carbon_kg=50.0,
                baseline_carbon_kg=100.0,
                carbon_savings_kg=50.0,
                carbon_savings_percent=50.0,
                optimized_avg_price=0.10,
                baseline_avg_price=0.15,
                optimized_avg_carbon=300.0,
                baseline_avg_carbon=400.0,
                cost_weight=0.7,
                carbon_weight=0.3,
                hourly_moer=[],
            )
        ),
    )

    pdf_bytes = generate_receipt_pdf(receipt)

    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_receipt_pdf_handles_unsigned_receipt():
    """generate_receipt_pdf() works with signature=None (unsigned receipt)."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )
    receipt = CarbonReceipt(
        moer_data_source="mock_simulation",
        workload=workload,
        optimal_start=datetime(2025, 1, 1, 12, 0),
        optimal_end=datetime(2025, 1, 1, 16, 0),
        baseline_start=datetime(2025, 1, 1, 18, 0),
        baseline_end=datetime(2025, 1, 1, 22, 0),
        optimized_cost=100.0,
        baseline_cost=150.0,
        cost_savings=50.0,
        cost_savings_percent=33.33,
        optimized_carbon_kg=50.0,
        baseline_carbon_kg=100.0,
        carbon_savings_kg=50.0,
        carbon_savings_percent=50.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
        cost_weight=0.7,
        carbon_weight=0.3,
        hourly_moer=[],
        signature=None,
    )

    # Should not raise
    pdf_bytes = generate_receipt_pdf(receipt)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_generate_receipt_pdf_with_24_hourly_entries():
    """generate_receipt_pdf() renders 24-hour window without error (stress test)."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=24.0,
        deadline_hours=24.0,
    )

    # Create 24 hourly entries
    hourly_moer = [
        HourlyMOEREntry(
            timestamp=datetime(2025, 1, 1, hour, 0),
            co2_intensity=300.0 + (hour % 6) * 50,  # Vary 300-550
            marginal_price=0.08 + (hour % 4) * 0.05,
            renewable_percentage=30.0 + (hour % 8) * 8,  # Vary 30-86%
            region="eastus",
            confidence=0.9,
            carbon_kg_for_hour=30.0 + (hour % 6) * 5,
            cost_for_hour=0.8 + (hour % 4) * 0.5,
        )
        for hour in range(24)
    ]

    receipt = CarbonReceipt(
        moer_data_source="mock_simulation",
        workload=workload,
        optimal_start=datetime(2025, 1, 1, 0, 0),
        optimal_end=datetime(2025, 1, 2, 0, 0),
        baseline_start=datetime(2025, 1, 1, 6, 0),
        baseline_end=datetime(2025, 1, 2, 6, 0),
        optimized_cost=960.0,
        baseline_cost=2400.0,
        cost_savings=1440.0,
        cost_savings_percent=60.0,
        optimized_carbon_kg=720.0,
        baseline_carbon_kg=2400.0,
        carbon_savings_kg=1680.0,
        carbon_savings_percent=70.0,
        optimized_avg_price=0.10,
        baseline_avg_price=0.15,
        optimized_avg_carbon=300.0,
        baseline_avg_carbon=400.0,
        cost_weight=0.7,
        carbon_weight=0.3,
        hourly_moer=hourly_moer,
        signature=sign_receipt(
            CarbonReceipt(
                moer_data_source="mock_simulation",
                workload=workload,
                optimal_start=datetime(2025, 1, 1, 0, 0),
                optimal_end=datetime(2025, 1, 2, 0, 0),
                baseline_start=datetime(2025, 1, 1, 6, 0),
                baseline_end=datetime(2025, 1, 2, 6, 0),
                optimized_cost=960.0,
                baseline_cost=2400.0,
                cost_savings=1440.0,
                cost_savings_percent=60.0,
                optimized_carbon_kg=720.0,
                baseline_carbon_kg=2400.0,
                carbon_savings_kg=1680.0,
                carbon_savings_percent=70.0,
                optimized_avg_price=0.10,
                baseline_avg_price=0.15,
                optimized_avg_carbon=300.0,
                baseline_avg_carbon=400.0,
                cost_weight=0.7,
                carbon_weight=0.3,
                hourly_moer=[],
            )
        ),
    )

    pdf_bytes = generate_receipt_pdf(receipt)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000  # Reasonable PDF size
