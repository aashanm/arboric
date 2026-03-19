"""Tests for cryptographic signing and verification."""

from datetime import datetime

import pytest

from arboric.core.models import Workload, WorkloadType
from arboric.receipts.models import CarbonReceipt

# Skip entire module if cryptography is not available
try:
    from arboric.receipts.signing import (
        default_backend,
        fingerprint,
        generate_keypair,
        load_pem_public_key,
        sign_receipt,
        verify_receipt,
    )
except ImportError:
    pytest.skip("cryptography not installed", allow_module_level=True)


def test_generate_keypair_returns_pem_bytes():
    """generate_keypair() returns (private_pem, public_pem) as bytes."""
    private_pem, public_pem = generate_keypair()

    assert isinstance(private_pem, bytes)
    assert isinstance(public_pem, bytes)
    assert private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")


def test_fingerprint_returns_64_char_hex():
    """fingerprint() returns a 64-character hex string (SHA256)."""
    private_pem, public_pem = generate_keypair()
    public_key = load_pem_public_key(public_pem, backend=default_backend())

    fp = fingerprint(public_key)

    assert isinstance(fp, str)
    assert len(fp) == 64
    # All characters should be hex
    assert all(c in "0123456789abcdef" for c in fp)


def test_sign_receipt_returns_signature():
    """sign_receipt() returns CryptoSignature with algorithm, fingerprint, signature_hex, data_hash, signed_at."""
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

    sig = sign_receipt(receipt)

    assert sig.algorithm == "ECDSA-P256-SHA256"
    assert len(sig.public_key_fingerprint) == 64
    assert len(sig.signature_hex) > 0
    assert len(sig.data_hash) == 64
    assert isinstance(sig.signed_at, datetime)


def test_verify_receipt_returns_true_for_valid_signature():
    """verify_receipt() returns True for a signed receipt."""
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

    # Sign the receipt
    receipt.signature = sign_receipt(receipt)

    # Verify it
    assert verify_receipt(receipt) is True


def test_verify_receipt_returns_false_for_tampered_receipt():
    """verify_receipt() returns False when receipt is tampered (canonical_json changed)."""
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

    # Sign the receipt
    receipt.signature = sign_receipt(receipt)

    # Tamper with the receipt (change cost_savings)
    tampered_receipt = receipt.model_copy(update={"cost_savings": 75.0})

    # Verify should fail
    assert verify_receipt(tampered_receipt) is False


def test_verify_receipt_returns_false_for_none_signature():
    """verify_receipt() returns False when signature is None."""
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

    # Verify unsigned receipt should fail
    assert verify_receipt(receipt) is False
