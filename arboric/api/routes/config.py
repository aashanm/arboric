"""
Configuration endpoint.
"""

from fastapi import APIRouter, Depends

from arboric.api.dependencies import get_arboric_config
from arboric.api.utils import create_api_response
from arboric.core.config import ArboricConfig

router = APIRouter()


@router.get("/config")
async def get_config(config: ArboricConfig = Depends(get_arboric_config)):
    """
    Get current Arboric configuration.

    Returns optimization settings, default workload parameters,
    and API configuration.

    Args:
        config: Arboric configuration (injected)

    Returns:
        Standardized API response with configuration data
    """
    data = {
        "optimization": {
            "price_weight": config.optimization.price_weight,
            "carbon_weight": config.optimization.carbon_weight,
            "min_delay_hours": config.optimization.min_delay_hours,
            "prefer_continuous": config.optimization.prefer_continuous,
        },
        "defaults": {
            "duration_hours": config.defaults.duration_hours,
            "power_draw_kw": config.defaults.power_draw_kw,
            "deadline_hours": config.defaults.deadline_hours,
            "region": config.defaults.region,
        },
        "api": {"watttime_enabled": config.api.watttime_enabled},
    }

    return create_api_response("config", data)
