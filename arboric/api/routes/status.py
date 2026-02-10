"""
System status endpoint.
"""

from datetime import datetime

from fastapi import APIRouter, Depends

from arboric.api.dependencies import get_arboric_config
from arboric.api.utils import create_api_response
from arboric.core.config import ArboricConfig

router = APIRouter()

# Track server start time
_server_start_time = datetime.now()


@router.get("/status")
async def get_status(config: ArboricConfig = Depends(get_arboric_config)):
    """
    Get system status and configuration information.

    Returns health status, component availability, and supported regions.

    Args:
        config: Arboric configuration (injected)

    Returns:
        Standardized API response with status information
    """
    uptime_seconds = (datetime.now() - _server_start_time).total_seconds()

    data = {
        "service": {
            "name": "arboric-api",
            "version": "0.1.0",
            "status": "online",
            "uptime_seconds": uptime_seconds,
        },
        "components": {
            "grid_oracle": {"status": "online", "type": "MockGrid", "mode": "simulation"},
            "autopilot": {"status": "ready", "version": "1.0.0"},
            "supported_regions": ["US-WEST", "US-EAST", "EU-WEST", "NORDIC"],
        },
        "configuration": {
            "default_price_weight": config.optimization.price_weight,
            "default_carbon_weight": config.optimization.carbon_weight,
            "default_region": config.defaults.region,
        },
    }

    return create_api_response("status", data)
