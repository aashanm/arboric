"""Tests for receipt data models."""

import json
from datetime import datetime
from uuid import uuid4

from arboric.core.models import Workload, WorkloadType
from arboric.receipts.models import CarbonReceipt, HourlyMOEREntry


def test_hourly_moer_entry_construction():
    """HourlyMOEREntry accepts all required fields."""
    now = datetime.utcnow()
    entry = HourlyMOEREntry(
        timestamp=now,
        co2_intensity=450.0,
        marginal_price=0.12,
        renewable_percentage=65.0,
        region="eastus",
        confidence=0.95,
        carbon_kg_for_hour=54.0,
        cost_for_hour=1.44,
    )

    assert entry.timestamp == now
    assert entry.co2_intensity == 450.0
    assert entry.marginal_price == 0.12
    assert entry.renewable_percentage == 65.0
    assert entry.region == "eastus"
    assert entry.confidence == 0.95
    assert entry.carbon_kg_for_hour == 54.0
    assert entry.cost_for_hour == 1.44


def test_carbon_receipt_canonical_json_excludes_signature():
    """canonical_json() excludes the signature field."""
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
    )

    canonical = receipt.canonical_json()
    parsed = json.loads(canonical)

    # Verify signature is not in canonical JSON
    assert "signature" not in parsed

    # Verify other fields are present
    assert parsed["receipt_id"] == str(receipt.receipt_id)
    assert parsed["cost_savings"] == 50.0


def test_carbon_receipt_canonical_json_deterministic():
    """canonical_json() produces identical output for identical receipts."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )
    receipt_id = uuid4()

    receipt1 = CarbonReceipt(
        receipt_id=receipt_id,
        generated_at=datetime(2025, 1, 1, 10, 0),
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

    receipt2 = CarbonReceipt(
        receipt_id=receipt_id,
        generated_at=datetime(2025, 1, 1, 10, 0),
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

    assert receipt1.canonical_json() == receipt2.canonical_json()


def test_carbon_receipt_canonical_json_changes_on_modification():
    """Modifying receipt data changes canonical_json output."""
    workload = Workload(
        name="Test Job",
        workload_type=WorkloadType.BATCH_PROCESSING,
        power_draw_kw=100.0,
        duration_hours=4.0,
        deadline_hours=24.0,
    )
    receipt_id = uuid4()

    receipt1 = CarbonReceipt(
        receipt_id=receipt_id,
        generated_at=datetime(2025, 1, 1, 10, 0),
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

    canonical1 = receipt1.canonical_json()

    # Create modified receipt (different cost)
    receipt2 = receipt1.model_copy(update={"optimized_cost": 105.0})
    canonical2 = receipt2.canonical_json()

    # Canonical JSONs should differ
    assert canonical1 != canonical2
