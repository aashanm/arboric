"""
Certified Carbon Receipt endpoint (Enterprise).
"""

import base64
from datetime import datetime
from datetime import timezone as tz

from fastapi import APIRouter, Depends, HTTPException, status

from arboric.api.dependencies import get_autopilot
from arboric.api.models.requests import OptimizeRequest
from arboric.api.utils import create_api_response
from arboric.core.autopilot import Autopilot
from arboric.core.config import get_config
from arboric.core.grid_oracle import get_grid
from arboric.receipts.exceptions import EnterpriseFeatureNotAvailableError

router = APIRouter()


@router.post("/receipt")
async def generate_receipt_endpoint(
    request: OptimizeRequest,
    autopilot: Autopilot = Depends(get_autopilot),
):
    """
    Generate a certified carbon receipt PDF for a single workload optimization.

    Combines optimization scheduling with cryptographic signing and PDF generation
    to produce a tamper-evident, audit-ready certification document suitable for
    SB 253 Scope 3 compliance.

    Args:
        request: Optimization request with workload details
        autopilot: Configured autopilot instance (injected)

    Returns:
        Standardized API response with receipt metadata and base64-encoded PDF

    Raises:
        HTTPException: 501 if enterprise dependencies not installed,
                      400 for business logic errors,
                      500 for unexpected errors
    """
    try:
        # Check if enterprise deps are available
        try:
            from arboric.receipts import generate_receipt
        except EnterpriseFeatureNotAvailableError:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Enterprise features not available. Install: pip install arboric[enterprise]",
            )

        # Get grid forecast
        grid = get_grid(region=request.region, config=get_config())
        forecast_hours = request.forecast_hours or 48
        # Pass appropriate time based on grid type
        now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
        if getattr(grid, "is_live", False):
            now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
        else:
            now_for_forecast = now_local
        forecast = grid.get_forecast(hours=forecast_hours, start_time=now_for_forecast)

        # Run optimization
        schedule = autopilot.optimize_schedule(request.workload, forecast)

        # Generate receipt (includes signing and PDF generation)
        carbon_receipt, pdf_bytes = generate_receipt(schedule, forecast, autopilot.config)

        # Encode PDF as base64 for JSON serialization
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # Build response
        data = {
            "receipt_id": str(carbon_receipt.receipt_id),
            "generated_at": carbon_receipt.generated_at.isoformat(),
            "compliance_framework": carbon_receipt.compliance_framework,
            "moer_data_source": carbon_receipt.moer_data_source,
            "workload": {
                "name": carbon_receipt.workload.name,
                "workload_type": carbon_receipt.workload.workload_type.value,
                "power_draw_kw": carbon_receipt.workload.power_draw_kw,
                "duration_hours": carbon_receipt.workload.duration_hours,
            },
            "optimization": {
                "optimal_start": carbon_receipt.optimal_start.isoformat(),
                "optimal_end": carbon_receipt.optimal_end.isoformat(),
                "baseline_start": carbon_receipt.baseline_start.isoformat(),
                "baseline_end": carbon_receipt.baseline_end.isoformat(),
            },
            "metrics": {
                "cost_savings": carbon_receipt.cost_savings,
                "cost_savings_percent": carbon_receipt.cost_savings_percent,
                "carbon_savings_kg": carbon_receipt.carbon_savings_kg,
                "carbon_savings_percent": carbon_receipt.carbon_savings_percent,
                "baseline_cost": carbon_receipt.baseline_cost,
                "optimized_cost": carbon_receipt.optimized_cost,
                "baseline_carbon_kg": carbon_receipt.baseline_carbon_kg,
                "optimized_carbon_kg": carbon_receipt.optimized_carbon_kg,
            },
            "signature": {
                "algorithm": carbon_receipt.signature.algorithm,
                "public_key_fingerprint": carbon_receipt.signature.public_key_fingerprint,
                "data_hash": carbon_receipt.signature.data_hash,
                "signed_at": carbon_receipt.signature.signed_at.isoformat(),
            }
            if carbon_receipt.signature
            else None,
            "pdf_base64": pdf_base64,
        }

        return create_api_response("receipt", data)

    except EnterpriseFeatureNotAvailableError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Enterprise features not available. Install: pip install arboric[enterprise]",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Receipt generation failed: {str(e)}",
        )
