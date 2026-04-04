"""
Fleet optimization endpoint.
"""

from datetime import datetime
from datetime import timezone as tz

from fastapi import APIRouter, Depends, HTTPException, status

from arboric.api.dependencies import get_autopilot
from arboric.api.models.requests import FleetOptimizeRequest
from arboric.api.utils import create_api_response, serialize_fleet_for_api
from arboric.core.autopilot import Autopilot
from arboric.core.config import get_config
from arboric.core.grid_oracle import get_grid

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
        # Get grid forecast (use first workload's instance type if specified)
        instance_type = None
        cloud_provider = None
        if request.workloads and request.workloads[0].instance_type:
            instance_type = request.workloads[0].instance_type
            cloud_provider = request.workloads[0].cloud_provider

        grid = get_grid(
            region=request.region,
            config=get_config(),
            instance_type=instance_type,
            cloud_provider=cloud_provider,
        )
        forecast_hours = request.forecast_hours or 48
        # Pass appropriate time based on grid type
        now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
        if type(grid).__name__ == "LiveGrid":
            now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
        else:
            now_for_forecast = now_local
        forecast = grid.get_forecast(hours=forecast_hours, start_time=now_for_forecast)

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
