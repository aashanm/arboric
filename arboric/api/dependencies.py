"""
FastAPI dependency injection functions.

Provides dependencies for accessing configured instances of Arboric components.
"""

from fastapi import Depends

from arboric.core.autopilot import Autopilot, OptimizationConfig
from arboric.core.config import ArboricConfig, get_config


def get_arboric_config() -> ArboricConfig:
    """
    Dependency for getting Arboric configuration.

    Returns:
        Loaded Arboric configuration from file or defaults
    """
    return get_config()


def get_autopilot(config: ArboricConfig = Depends(get_arboric_config)) -> Autopilot:
    """
    Dependency for getting configured Autopilot instance.

    Creates an Autopilot with optimization settings from the configuration file.

    Args:
        config: Arboric configuration (injected dependency)

    Returns:
        Configured Autopilot instance
    """
    opt_config = OptimizationConfig(
        price_weight=config.optimization.price_weight,
        carbon_weight=config.optimization.carbon_weight,
        min_delay_hours=config.optimization.min_delay_hours,
        prefer_continuous=config.optimization.prefer_continuous,
    )
    return Autopilot(config=opt_config)
