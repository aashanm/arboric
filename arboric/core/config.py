"""
Arboric Configuration

Handles loading and validation of user configuration from ~/.arboric/config.yaml.
Provides sensible defaults for all settings.
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class OptimizationSettings(BaseModel):
    """Optimization algorithm settings."""

    price_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for cost optimization (0-1)"
    )
    carbon_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for carbon optimization (0-1)"
    )
    min_delay_hours: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum delay before starting workloads (hours)"
    )
    prefer_continuous: bool = Field(
        default=True,
        description="Prefer continuous execution windows"
    )

    @field_validator('price_weight', 'carbon_weight')
    @classmethod
    def validate_weights(cls, v, info):
        """Ensure weights sum to 1.0."""
        if info.field_name == 'carbon_weight':
            # Only validate when both fields are present
            data = info.data
            if 'price_weight' in data:
                price_weight = data['price_weight']
                if abs(price_weight + v - 1.0) > 0.01:
                    raise ValueError('price_weight and carbon_weight must sum to 1.0')
        return v


class DefaultWorkloadSettings(BaseModel):
    """Default settings for workload definitions."""

    duration_hours: float = Field(default=4.0, gt=0, description="Default workload duration")
    power_draw_kw: float = Field(default=50.0, gt=0, description="Default power draw in kW")
    deadline_hours: float = Field(default=12.0, gt=0, description="Default deadline in hours")
    region: str = Field(default="US-WEST", description="Default grid region")


class APISettings(BaseModel):
    """Settings for external API integrations."""

    watttime_username: Optional[str] = Field(default=None, description="WattTime API username")
    watttime_password: Optional[str] = Field(default=None, description="WattTime API password")
    watttime_enabled: bool = Field(default=False, description="Enable WattTime integration")


class CLISettings(BaseModel):
    """CLI display and behavior settings."""

    show_banner: bool = Field(default=True, description="Show ASCII banner on startup")
    color_theme: str = Field(default="default", description="Color theme (default, minimal, mono)")
    quiet_mode: bool = Field(default=False, description="Minimize output")
    auto_approve: bool = Field(default=False, description="Skip confirmation prompts")


class ArboricConfig(BaseModel):
    """
    Main Arboric configuration model.

    Loads from ~/.arboric/config.yaml or uses defaults.
    """

    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings)
    defaults: DefaultWorkloadSettings = Field(default_factory=DefaultWorkloadSettings)
    api: APISettings = Field(default_factory=APISettings)
    cli: CLISettings = Field(default_factory=CLISettings)

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the config file."""
        config_dir = Path.home() / ".arboric"
        return config_dir / "config.yaml"

    @classmethod
    def ensure_config_dir(cls) -> Path:
        """Ensure the config directory exists."""
        config_dir = Path.home() / ".arboric"
        config_dir.mkdir(exist_ok=True)
        return config_dir

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "ArboricConfig":
        """
        Load configuration from file or use defaults.

        Args:
            config_path: Optional custom config path. If None, uses ~/.arboric/config.yaml

        Returns:
            ArboricConfig instance with loaded or default settings
        """
        if config_path is None:
            config_path = cls.get_config_path()

        # If config file doesn't exist, return defaults
        if not config_path.exists():
            return cls()

        # Load and parse YAML
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}

            # Handle empty file
            if not config_data:
                return cls()

            return cls(**config_data)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading config file: {e}")

    def save(self, config_path: Optional[Path] = None) -> None:
        """
        Save configuration to file.

        Args:
            config_path: Optional custom config path. If None, uses ~/.arboric/config.yaml
        """
        if config_path is None:
            config_path = self.get_config_path()

        # Ensure directory exists
        self.ensure_config_dir()

        # Convert to dict and save as YAML
        config_dict = self.model_dump(exclude_none=True)

        with open(config_path, 'w') as f:
            yaml.safe_dump(
                config_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                indent=2
            )

    @classmethod
    def create_default_config(cls, config_path: Optional[Path] = None) -> "ArboricConfig":
        """
        Create a default config file if it doesn't exist.

        Args:
            config_path: Optional custom config path. If None, uses ~/.arboric/config.yaml

        Returns:
            Default ArboricConfig instance
        """
        if config_path is None:
            config_path = cls.get_config_path()

        # Only create if it doesn't exist
        if config_path.exists():
            return cls.load(config_path)

        # Create default config and save
        config = cls()
        config.save(config_path)
        return config


# Global config instance (lazy loaded)
_config: Optional[ArboricConfig] = None


def get_config(reload: bool = False) -> ArboricConfig:
    """
    Get the global Arboric configuration.

    Args:
        reload: Force reload from file

    Returns:
        ArboricConfig instance
    """
    global _config

    if _config is None or reload:
        _config = ArboricConfig.load()

    return _config


def reset_config() -> None:
    """Reset the global config (mainly for testing)."""
    global _config
    _config = None
