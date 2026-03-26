"""
Arboric Grid Oracle

Simulation engine for cloud compute forecasting.
Generates realistic synthetic data modeling regional spot pricing and carbon patterns:
- Cloud spot instance pricing (driven by capacity contention)
- Carbon intensity fluctuations (duck curve effect from solar generation)

Note: These signals are independent. Carbon is based on grid electricity generation mix,
while spot prices are based on spare cloud capacity (business-hours peaks).

For real-time grid data (live APIs), install: pip install arboric[cloud]
This package provides MockGrid simulation; live integrations are available separately.
"""

import math
import random
from datetime import datetime, timedelta

import pandas as pd

from arboric.core.models import GridWindow

# Regional profiles (carbon patterns + cloud spot pricing)
# Carbon fields: model electricity grid generation mix (solar duck curve, evening peaker ramps)
# Pricing fields: model cloud spot instance rates (business-hours capacity contention)
REGION_PROFILES = {
    "US-WEST": {
        # Carbon (unchanged from original - still models grid generation mix)
        "base_carbon": 350,  # gCO2/kWh
        "carbon_amplitude": 200,  # Swing from solar duck curve
        "solar_peak_hour": 13,  # 1 PM peak solar generation
        # Spot pricing (replaces electricity TOU model)
        "on_demand_rate_per_hr": 24.00,  # Reference GPU on-demand rate ($/hr)
        "spot_floor_discount": 0.58,  # 58% off = $10.08/hr floor (overnight cheap)
        "spot_peak_discount": 0.25,  # 25% off = $18.00/hr peak (business hours)
        "contention_peak_hour": 14,  # 2 PM PT - peak ML batch job submission
        "timezone_offset": -8,
    },
    "US-EAST": {
        "base_carbon": 420,
        "carbon_amplitude": 150,
        "solar_peak_hour": 13,
        "on_demand_rate_per_hr": 22.00,
        "spot_floor_discount": 0.55,  # → floor=$9.90/hr, peak=$17.60/hr
        "spot_peak_discount": 0.20,
        "contention_peak_hour": 14,  # 2 PM ET - peak ML batch job submission
        "timezone_offset": -5,
    },
    "EU-WEST": {
        "base_carbon": 280,
        "carbon_amplitude": 180,
        "solar_peak_hour": 14,
        "on_demand_rate_per_hr": 20.00,
        "spot_floor_discount": 0.50,  # → floor=$10.00/hr, peak=$17.00/hr
        "spot_peak_discount": 0.15,
        "contention_peak_hour": 13,  # 1 PM CET - peak ML batch job submission
        "timezone_offset": 1,
    },
    "NORDIC": {
        "base_carbon": 80,  # Hydro-dominated
        "carbon_amplitude": 40,
        "solar_peak_hour": 13,
        "on_demand_rate_per_hr": 18.00,
        "spot_floor_discount": 0.60,  # → floor=$7.20/hr, peak=$12.60/hr
        "spot_peak_discount": 0.30,
        "contention_peak_hour": 13,  # 1 PM CET - peak ML batch job submission
        "timezone_offset": 1,
    },
}

# Cloud instance profiles for spot pricing simulation
# Maps (provider, instance_type) → (on_demand rate, spot floor discount)
INSTANCE_PROFILES = {
    "aws": {
        "p3.2xlarge": {
            "on_demand": 3.06,
            "spot_floor_discount": 0.70,
            "gpu": "V100 (1x)",
            "use_case": "ML training / inference",
        },
        "p3.8xlarge": {
            "on_demand": 12.24,
            "spot_floor_discount": 0.68,
            "gpu": "V100 (4x)",
            "use_case": "Distributed training",
        },
        "p3.16xlarge": {
            "on_demand": 24.48,
            "spot_floor_discount": 0.65,
            "gpu": "V100 (8x)",
            "use_case": "Large model training",
        },
        "p4d.24xlarge": {
            "on_demand": 32.77,
            "spot_floor_discount": 0.60,
            "gpu": "A100 (8x)",
            "use_case": "Foundation model training",
        },
        "g5.xlarge": {
            "on_demand": 1.006,
            "spot_floor_discount": 0.72,
            "gpu": "A10G (1x)",
            "use_case": "Inference / fine-tuning",
        },
        "g5.12xlarge": {
            "on_demand": 5.672,
            "spot_floor_discount": 0.68,
            "gpu": "A10G (4x)",
            "use_case": "Mid-scale training",
        },
        "g4dn.xlarge": {
            "on_demand": 0.526,
            "spot_floor_discount": 0.75,
            "gpu": "T4 (1x)",
            "use_case": "Inference / small training",
        },
        "g4dn.12xlarge": {
            "on_demand": 3.912,
            "spot_floor_discount": 0.71,
            "gpu": "T4 (4x)",
            "use_case": "Batch inference",
        },
    },
    "gcp": {
        "n1-standard-8-v100": {
            "on_demand": 2.48,
            "spot_floor_discount": 0.72,
            "gpu": "V100 (1x)",
            "use_case": "ML training",
        },
        "a2-highgpu-1g": {
            "on_demand": 3.67,
            "spot_floor_discount": 0.67,
            "gpu": "A100 (1x)",
            "use_case": "Training / inference",
        },
        "a2-highgpu-4g": {
            "on_demand": 14.69,
            "spot_floor_discount": 0.65,
            "gpu": "A100 (4x)",
            "use_case": "Distributed training",
        },
        "a2-highgpu-8g": {
            "on_demand": 29.39,
            "spot_floor_discount": 0.63,
            "gpu": "A100 (8x)",
            "use_case": "Large model training",
        },
        "g2-standard-4": {
            "on_demand": 0.90,
            "spot_floor_discount": 0.73,
            "gpu": "L4 (1x)",
            "use_case": "Inference",
        },
        "g2-standard-16": {
            "on_demand": 3.59,
            "spot_floor_discount": 0.70,
            "gpu": "L4 (4x)",
            "use_case": "Batch inference",
        },
    },
    "azure": {
        "Standard_NC6s_v3": {
            "on_demand": 3.06,
            "spot_floor_discount": 0.68,
            "gpu": "V100 (1x)",
            "use_case": "ML training",
        },
        "Standard_NC24s_v3": {
            "on_demand": 12.24,
            "spot_floor_discount": 0.65,
            "gpu": "V100 (4x)",
            "use_case": "Distributed training",
        },
        "Standard_ND96asr_v4": {
            "on_demand": 27.20,
            "spot_floor_discount": 0.60,
            "gpu": "A100 (8x)",
            "use_case": "Foundation model training",
        },
        "Standard_NC4as_T4_v3": {
            "on_demand": 0.526,
            "spot_floor_discount": 0.74,
            "gpu": "T4 (1x)",
            "use_case": "Inference",
        },
        "Standard_NC16as_T4_v3": {
            "on_demand": 1.204,
            "spot_floor_discount": 0.71,
            "gpu": "T4 (4x)",
            "use_case": "Batch inference",
        },
    },
}

DEFAULT_INSTANCE = {
    "on_demand": 12.24,
    "spot_floor_discount": 0.68,
    "gpu": "GPU (unspecified)",
    "use_case": "General ML workload",
}


class MockGrid:
    """
    Simulates cloud compute forecasts with spot pricing and carbon intensity.

    Models two INDEPENDENT phenomena:
    1. Carbon Intensity (Duck Curve) - Solar generation suppresses grid carbon 11am-3pm
    2. Spot Pricing (Business Hours) - Cloud capacity contention peaks 9am-6pm (driven by job queuing, not solar)

    These signals are uncorrelated by design: sometimes the cheapest spot window overlaps with
    the greenest carbon window, sometimes they don't. This tension creates the scheduling tradeoff.
    """

    def __init__(
        self,
        region: str = "US-WEST",
        instance_type: str | None = None,
        cloud_provider: str | None = None,
        seed: int | None = None,
    ):
        """
        Initialize the grid simulator.

        Args:
            region: Grid region identifier (US-WEST, US-EAST, EU-WEST, NORDIC)
            instance_type: Cloud instance type (e.g., 'p3.8xlarge'). Use with cloud_provider.
            cloud_provider: Cloud provider ('aws', 'gcp', 'azure'). Use with instance_type.
            seed: Random seed for reproducible forecasts (None for varied demos)
        """
        self.region = region.upper()
        if self.region not in REGION_PROFILES:
            raise ValueError(
                f"Unknown region: {self.region}. Available: {list(REGION_PROFILES.keys())}"
            )

        self.profile = REGION_PROFILES[self.region]

        # Resolve instance profile
        if cloud_provider and instance_type:
            provider_profiles = INSTANCE_PROFILES.get(cloud_provider.lower(), {})
            self.instance_profile = provider_profiles.get(instance_type, DEFAULT_INSTANCE)
        else:
            self.instance_profile = DEFAULT_INSTANCE

        # Use instance-specific random generator for reproducible results
        self._random = random.Random(seed)

        # Add daily variation factors
        self._daily_carbon_shift = self._random.uniform(-30, 30)
        self._daily_price_shift = self._random.uniform(-0.02, 0.02)
        self._weather_factor = self._random.uniform(0.8, 1.2)  # Cloud cover impact

    def _calculate_solar_factor(self, hour: float) -> float:
        """
        Calculate the solar generation factor (0-1) for a given hour.

        This factor drives BOTH carbon reduction AND price reduction,
        creating the correlated "win-win" window during solar peak.
        Peak solar window: 11 AM - 3 PM (centered at 1 PM).
        """
        solar_peak = 13.0  # 1 PM is peak solar

        # Gaussian-shaped solar curve - strongest 11 AM to 3 PM
        solar_width = 2.5  # Controls the width of the peak window
        solar_factor = math.exp(-((hour - solar_peak) ** 2) / (2 * solar_width**2))

        # Apply weather variation
        solar_factor *= self._weather_factor

        # Zero out solar at night
        if hour < 6 or hour > 20:
            solar_factor = 0.0

        return min(1.0, max(0.0, solar_factor))

    def _calculate_carbon_intensity(self, hour: float) -> float:
        """
        Calculate carbon intensity for a given hour.

        Models the duck curve: Low carbon during solar hours (11am-3pm),
        high carbon during evening ramp and overnight.

        Key insight: Solar generation directly displaces fossil fuel generation,
        creating LOWEST carbon during PEAK solar hours.
        """
        base = self.profile["base_carbon"]
        amplitude = self.profile["carbon_amplitude"]

        # Solar suppression - strongest effect during 11 AM - 3 PM
        solar_factor = self._calculate_solar_factor(hour)
        solar_reduction = amplitude * 1.2 * solar_factor  # Strong solar impact

        # Evening ramp (additional carbon from peaker plants 5-9pm)
        evening_peak = 19
        evening_width = 2.5
        evening_component = 0
        if 16 <= hour <= 22:
            evening_distance = abs(hour - evening_peak)
            evening_component = 120 * math.exp(-(evening_distance**2) / (2 * evening_width**2))

        # Night baseline bump (less wind, no solar)
        night_component = 0
        if hour < 6 or hour > 21:
            night_component = 80

        # Random noise (reduced for more predictable demo)
        noise = self._random.gauss(0, 10)

        intensity = (
            base
            - solar_reduction
            + evening_component
            + night_component
            + self._daily_carbon_shift
            + noise
        )
        return max(50, min(800, intensity))  # Clamp to realistic range

    def _calculate_price(self, hour: float, instance_profile: dict | None = None) -> float:
        """
        Calculate cloud spot instance price for a given hour.

        Models capacity contention pricing (NOT electricity wholesale pricing):
        - Off-Peak (10pm-6am): LOWEST prices, spare cloud capacity → floor discount
        - Business Hours (9am-6pm): HIGHEST prices, peak job queuing → minimal discount
        - Ramp-up (6am-9am): Linear transition from floor to peak
        - Evening Decay (6pm-10pm): Fall-back from peak toward floor

        Key insight: Spot prices driven by spare cloud capacity and job queue length,
        completely independent from grid carbon (which depends on solar/peaker plants).

        Args:
            hour: Hour of day (0-24)
            instance_profile: Instance profile dict with 'on_demand' and 'spot_floor_discount'.
                            If None, uses self.instance_profile
        """
        if instance_profile is None:
            instance_profile = self.instance_profile

        on_demand = instance_profile["on_demand"]
        floor_price = on_demand * (1 - instance_profile["spot_floor_discount"])
        peak_price = on_demand * (1 - self.profile["spot_peak_discount"])
        price_range = peak_price - floor_price

        contention_peak = self.profile["contention_peak_hour"]
        contention_width = 5.0  # Gaussian width in hours (wider peak, extends further)

        # Business-hours contention spike (9am-6pm, Gaussian centered at peak hour)
        # Gaussian extends naturally beyond boundaries, so we apply it to all hours
        # but the formula naturally decreases outside the main window
        distance = abs(hour - contention_peak)
        contention_component = price_range * math.exp(-(distance**2) / (2 * contention_width**2))

        # Morning ramp-up (6am-9am, linear)
        ramp_component = 0
        if 6 <= hour < 9:
            ramp_fraction = (hour - 6) / 3.0
            ramp_component = price_range * 0.35 * ramp_fraction

        # Evening decay (6pm-10pm, linear fall-off)
        evening_component = 0
        if 18 < hour <= 22:
            decay_fraction = (hour - 18) / 4.0
            evening_component = price_range * 0.4 * (1 - decay_fraction)

        # Random market noise (~1% of on-demand rate)
        noise = self._random.gauss(0, on_demand * 0.01)

        price = floor_price + contention_component + ramp_component + evening_component + noise

        # Clamp: allow slight undercut below floor due to noise, never exceed on-demand
        return max(floor_price * 0.85, min(on_demand, price))

    def _calculate_renewable_percentage(self, hour: float) -> float:
        """Calculate renewable energy percentage based on solar/wind patterns."""
        solar_peak = self.profile["solar_peak_hour"]

        # Solar contribution (peaks midday)
        solar = 40 * self._weather_factor * max(0, math.cos(2 * math.pi * (hour - solar_peak) / 24))

        # Wind contribution (slightly higher at night in many regions)
        wind_base = 15 + self._random.uniform(-5, 5)
        wind = wind_base + 10 * math.cos(2 * math.pi * (hour - 4) / 24)  # Peaks around 4am

        # Base hydro/nuclear (constant)
        base_renewable = 10 if self.region != "NORDIC" else 60

        total = base_renewable + solar + max(0, wind)
        return min(95, max(5, total + self._random.gauss(0, 3)))

    def get_forecast(
        self, hours: int = 24, resolution_minutes: int = 60, start_time: datetime | None = None
    ) -> pd.DataFrame:
        """
        Generate a grid forecast for the specified time horizon.

        Args:
            hours: Forecast horizon in hours
            resolution_minutes: Time resolution (default 60 = hourly)
            start_time: Optional start time (defaults to current time for realistic forecasts)

        Returns:
            DataFrame with timestamp, co2_intensity, price, renewable_percentage
        """
        # Round UP to next hour if past the :00 minute, ensuring forecast never starts from past
        dt = start_time or datetime.now()
        now = dt.replace(minute=0, second=0, microsecond=0)
        if dt != now:  # Time had to be adjusted, so we were past the hour boundary
            now += timedelta(hours=1)
        windows = []

        intervals = (hours * 60) // resolution_minutes

        for i in range(intervals):
            timestamp = now + timedelta(minutes=i * resolution_minutes)
            hour_of_day = timestamp.hour + timestamp.minute / 60

            # Add slight trend drift for longer forecasts
            trend_factor = 1 + (i / intervals) * self._random.uniform(-0.05, 0.05)

            # Calculate values with trend factor and ensure they stay in valid ranges
            co2 = self._calculate_carbon_intensity(hour_of_day) * trend_factor
            price = self._calculate_price(hour_of_day, self.instance_profile) * trend_factor

            # Clamp price using dynamic bounds based on instance profile
            floor = (
                self.instance_profile["on_demand"]
                * (1 - self.instance_profile["spot_floor_discount"])
                * 0.85
            )
            ceiling = self.instance_profile["on_demand"]

            window = GridWindow(
                timestamp=timestamp,
                co2_intensity=max(50, min(800, co2)),  # Re-clamp after trend factor
                price=max(
                    floor, min(ceiling, price)
                ),  # Re-clamp after trend factor, using spot price bounds
                renewable_percentage=self._calculate_renewable_percentage(hour_of_day),
                region=self.region,
                confidence=max(0.5, 1.0 - (i / intervals) * 0.3),  # Confidence decreases with time
            )
            windows.append(window)

        # Convert to DataFrame
        df = pd.DataFrame([w.model_dump() for w in windows])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        # Add instance pricing metadata columns
        df["on_demand_rate"] = self.instance_profile["on_demand"]
        df["spot_discount_pct"] = 1 - (df["price"] / self.instance_profile["on_demand"])

        return df

    def get_current_conditions(self) -> GridWindow:
        """Get current grid conditions (single window)."""
        now = datetime.now()
        hour_of_day = now.hour + now.minute / 60

        return GridWindow(
            timestamp=now,
            co2_intensity=self._calculate_carbon_intensity(hour_of_day),
            price=self._calculate_price(hour_of_day, self.instance_profile),
            renewable_percentage=self._calculate_renewable_percentage(hour_of_day),
            region=self.region,
            confidence=1.0,
        )

    def detect_events(self, forecast_df: pd.DataFrame) -> list[dict]:
        """
        Detect notable grid events in the forecast.

        Returns list of events for logging/display purposes.
        """
        events = []

        # Detect carbon peaks
        carbon_threshold = self.profile["base_carbon"] + self.profile["carbon_amplitude"] * 0.7
        high_carbon_periods = forecast_df[forecast_df["co2_intensity"] > carbon_threshold]
        if not high_carbon_periods.empty:
            events.append(
                {
                    "type": "HIGH_CARBON",
                    "severity": "warning",
                    "start": high_carbon_periods.index[0],
                    "description": f"High-carbon period detected ({high_carbon_periods['co2_intensity'].max():.0f} gCO2/kWh)",
                }
            )

        # Detect spot price spikes (10% above nominal peak contention rate)
        peak_price = self.instance_profile["on_demand"] * (1 - self.profile["spot_peak_discount"])
        spike_threshold = peak_price * 1.10
        high_price_periods = forecast_df[forecast_df["price"] > spike_threshold]
        if not high_price_periods.empty:
            events.append(
                {
                    "type": "PRICE_SPIKE",
                    "severity": "warning",
                    "start": high_price_periods.index[0],
                    "description": f"Spot price spike expected (${high_price_periods['price'].max():.2f}/hr)",
                }
            )

        # Detect green windows (solar peak)
        green_threshold = self.profile["base_carbon"] - self.profile["carbon_amplitude"] * 0.5
        green_periods = forecast_df[forecast_df["co2_intensity"] < green_threshold]
        if not green_periods.empty:
            events.append(
                {
                    "type": "GREEN_WINDOW",
                    "severity": "opportunity",
                    "start": green_periods.index[0],
                    "description": f"Low-carbon window available ({green_periods['co2_intensity'].min():.0f} gCO2/kWh)",
                }
            )

        # Detect cheap windows (within 15% above floor = genuine buying opportunity)
        floor_price = self.instance_profile["on_demand"] * (
            1 - self.instance_profile["spot_floor_discount"]
        )
        cheap_threshold = floor_price * 1.15
        cheap_periods = forecast_df[forecast_df["price"] < cheap_threshold]
        if not cheap_periods.empty:
            events.append(
                {
                    "type": "LOW_PRICE",
                    "severity": "opportunity",
                    "start": cheap_periods.index[0],
                    "description": f"Low spot price window available (${cheap_periods['price'].min():.2f}/hr)",
                }
            )

        return events


def get_grid(
    region: str = "US-WEST",
    config=None,
    seed: int | None = None,
    instance_type: str | None = None,
    cloud_provider: str | None = None,
) -> MockGrid:  # type: ignore
    """Factory function to create a grid oracle for a region.

    Returns LiveGrid (from arboric-cloud) if available and credentials configured,
    otherwise returns MockGrid (pure simulation, always available).

    Args:
        region: Grid region identifier
        config: Optional ArboricConfig instance (loaded from file if None)
        seed: Optional random seed. If None and using MockGrid, seeds based on current date
              for reproducibility within a day.
        instance_type: Cloud instance type (e.g., 'p3.8xlarge'). Use with cloud_provider.
        cloud_provider: Cloud provider ('aws', 'gcp', 'azure'). Use with instance_type.
                       Note: ignored for LiveGrid (passed through but not used).

    Returns:
        Grid provider instance (LiveGrid or MockGrid)
    """
    # Normalize region to uppercase
    region = region.upper()

    if config is None:
        from arboric.core.config import get_config

        config = get_config()

    live_data = config.live_data

    # Only attempt LiveGrid if live mode is enabled and arboric-cloud is available
    if live_data.enabled and live_data.api_key and live_data.api_secret:
        try:
            # Try to import from the optional arboric-cloud package
            from arboric_cloud import create_live_grid

            return create_live_grid(
                username=live_data.api_key,
                password=live_data.api_secret,
                region=region,
                pricing_by_region=live_data.pricing_by_region,
                pricing_api_keys=live_data.pricing_api_keys,
                strict_pricing=live_data.strict_pricing,
            )
        except ImportError:
            # arboric-cloud not installed, fall back to MockGrid
            import logging

            logging.info(
                "arboric-cloud not installed or LiveGrid unavailable. "
                "Using MockGrid simulation. Install with: pip install arboric[cloud]"
            )
        except Exception as e:
            # Other error (auth, connection, etc.), log and fall back
            import logging

            logging.warning(f"Failed to initialize LiveGrid: {e}. Falling back to MockGrid.")

    # Default: return MockGrid simulation
    # Use date-based seed for reproducibility (same day = same forecast)
    if seed is None:
        from datetime import datetime as dt

        seed = int(dt.now().strftime("%Y%m%d"))
    return MockGrid(
        region=region,
        instance_type=instance_type,
        cloud_provider=cloud_provider,
        seed=seed,
    )
