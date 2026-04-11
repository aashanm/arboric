"""
Grid forecast endpoint.
"""

from datetime import datetime
from datetime import timezone as tz

from fastapi import APIRouter, HTTPException, Query, status

from arboric.api.utils import create_api_response
from arboric.core.config import get_config
from arboric.core.grid_oracle import get_grid

router = APIRouter()


@router.get("/forecast")
async def get_forecast(
    region: str = Query(default="eastus", description="Grid region"),
    hours: int = Query(default=24, ge=1, le=168, description="Forecast hours (1-168)"),
):
    """
    Get grid electricity forecast for a region.

    Returns hourly forecast data including carbon intensity, price,
    renewable percentage, and confidence scores.

    Args:
        region: Grid region (eastus, westus2, uksouth, northeurope)
        hours: Number of forecast hours (1-168)

    Returns:
        Standardized API response with forecast data

    Raises:
        HTTPException: 400 for invalid region, 500 for unexpected errors
    """
    try:
        # Get grid forecast
        grid = get_grid(region=region, config=get_config())
        # Pass appropriate time based on grid type
        now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
        if getattr(grid, "is_live", False):
            now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
        else:
            now_for_forecast = now_local
        forecast_df = grid.get_forecast(hours=hours, start_time=now_for_forecast)

        # Convert DataFrame to list of dicts
        forecast_data = forecast_df.reset_index().to_dict(orient="records")

        # Format response
        data = {
            "metadata": {
                "region": region,
                "hours": hours,
                "data_points": len(forecast_data),
                "resolution_minutes": 60,
            },
            "data": forecast_data,
        }

        return create_api_response("forecast", data)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast retrieval failed: {str(e)}",
        )
