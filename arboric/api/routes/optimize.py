"""
Single workload optimization endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from arboric.api.dependencies import get_autopilot
from arboric.api.models.requests import OptimizeRequest
from arboric.api.utils import create_api_response, serialize_schedule_for_api
from arboric.core.autopilot import Autopilot
from arboric.core.grid_oracle import MockGrid

router = APIRouter()


@router.post("/optimize")
async def optimize_workload(
    request: OptimizeRequest,
    autopilot: Autopilot = Depends(get_autopilot),
):
    """
    Optimize a single workload for cost and carbon efficiency.

    Returns the optimal start time and comparative metrics against
    immediate execution, including cost savings, carbon savings, and
    the recommended delay.

    Args:
        request: Optimization request with workload details
        autopilot: Configured autopilot instance (injected)

    Returns:
        Standardized API response with optimization results

    Raises:
        HTTPException: 400 for business logic errors, 500 for unexpected errors
    """
    try:
        # Get grid forecast
        grid = MockGrid(region=request.region)
        forecast_hours = request.forecast_hours or 48
        forecast = grid.get_forecast(hours=forecast_hours)

        # Run optimization
        result = autopilot.optimize_schedule(request.workload, forecast)

        # Serialize and return
        data = serialize_schedule_for_api(result)
        return create_api_response("optimize", data)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization failed: {str(e)}",
        )
