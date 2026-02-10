"""
Fleet optimization endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from arboric.api.dependencies import get_autopilot
from arboric.api.models.requests import FleetOptimizeRequest
from arboric.api.utils import create_api_response, serialize_fleet_for_api
from arboric.core.autopilot import Autopilot
from arboric.core.grid_oracle import MockGrid
from arboric.core.models import FleetOptimizationResult

router = APIRouter()


@router.post("/optimize")
async def optimize_fleet(
    request: FleetOptimizeRequest,
    autopilot: Autopilot = Depends(get_autopilot),
):
    """
    Optimize multiple workloads together (fleet optimization).

    Optimizes each workload independently and returns aggregated metrics
    including total cost savings, total carbon savings, and individual
    schedules for each workload.

    Args:
        request: Fleet optimization request with multiple workloads
        autopilot: Configured autopilot instance (injected)

    Returns:
        Standardized API response with fleet optimization results

    Raises:
        HTTPException: 400 for business logic errors, 500 for unexpected errors
    """
    try:
        # Get grid forecast
        grid = MockGrid(region=request.region)
        forecast_hours = request.forecast_hours or 48
        forecast = grid.get_forecast(hours=forecast_hours)

        # Run fleet optimization
        result = autopilot.optimize_fleet(request.workloads, forecast)

        # Serialize and return
        data = serialize_fleet_for_api(result)
        return create_api_response("fleet", data)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fleet optimization failed: {str(e)}",
        )
