"""Certified Carbon Receipts (Enterprise) — tamper-evident audit artifacts for SB 253 compliance."""

from arboric.receipts.exceptions import (
    EnterpriseFeatureNotAvailableError,
    PDFGenerationError,
    SigningError,
)
from arboric.receipts.models import (
    CarbonReceipt,
    CryptoSignature,
    HourlyMOEREntry,
)

# Lazy import enterprise features - only raise error if actually used
try:
    from arboric.receipts.service import generate_receipt
    from arboric.receipts.signing import verify_receipt
except EnterpriseFeatureNotAvailableError:
    # Enterprise dependencies not available - export placeholder
    def generate_receipt(*args, **kwargs):  # type: ignore
        raise EnterpriseFeatureNotAvailableError(
            "Enterprise features not available. Install: pip install arboric[enterprise]"
        )

    def verify_receipt(*args, **kwargs):  # type: ignore
        raise EnterpriseFeatureNotAvailableError(
            "Enterprise features not available. Install: pip install arboric[enterprise]"
        )


__all__ = [
    "generate_receipt",
    "verify_receipt",
    "CarbonReceipt",
    "CryptoSignature",
    "HourlyMOEREntry",
    "EnterpriseFeatureNotAvailableError",
    "SigningError",
    "PDFGenerationError",
]
