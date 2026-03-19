"""Pydantic models for certified carbon receipts."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from arboric.core.models import Workload


class HourlyMOEREntry(BaseModel):
    """Per-hour grid emissions data for a specific timestamp."""

    timestamp: datetime
    co2_intensity: float  # gCO2/kWh
    marginal_price: float  # $/kWh
    renewable_percentage: float  # 0-100
    region: str
    confidence: float  # 0-1
    carbon_kg_for_hour: float  # co2_intensity * power_draw_kw / 1000
    cost_for_hour: float  # marginal_price * power_draw_kw / 1000


class CryptoSignature(BaseModel):
    """ECDSA-P256-SHA256 cryptographic signature."""

    algorithm: str = "ECDSA-P256-SHA256"
    public_key_fingerprint: str  # SHA256(DER public key).hexdigest()
    signature_hex: str  # DER signature bytes as hex
    data_hash: str  # SHA256(canonical_json()).hexdigest()
    signed_at: datetime


class CarbonReceipt(BaseModel):
    """Certified carbon avoidance receipt — tamper-evident audit artifact."""

    receipt_id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    compliance_framework: str = "CA SB 253 / Scope 3"
    moer_data_source: str  # "live_emissions_provider" | "mock_simulation"

    # Workload (full object embedded)
    workload: Workload

    # Schedule (datetime fields)
    optimal_start: datetime
    optimal_end: datetime
    baseline_start: datetime
    baseline_end: datetime

    # Financials (all materialized, not computed)
    optimized_cost: float
    baseline_cost: float
    cost_savings: float
    cost_savings_percent: float

    # Carbon (all materialized)
    optimized_carbon_kg: float
    baseline_carbon_kg: float
    carbon_savings_kg: float
    carbon_savings_percent: float

    # Average metrics (materialized for display)
    optimized_avg_price: float
    baseline_avg_price: float
    optimized_avg_carbon: float
    baseline_avg_carbon: float

    # Optimization weights used
    cost_weight: float
    carbon_weight: float

    # Per-hour grid data
    hourly_moer: list[HourlyMOEREntry]

    # Signature (excluded from canonical_json)
    signature: CryptoSignature | None = None

    def canonical_json(self) -> str:
        """
        Deterministic JSON string for cryptographic hashing.
        Excludes the signature field itself.
        """
        return json.dumps(
            self.model_dump(exclude={"signature"}, mode="json"),
            sort_keys=True,
            default=str,
        )
