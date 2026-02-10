"""
Arboric Grid Oracle

Simulation engine for electricity grid forecasting.
Generates realistic synthetic data modeling the California "duck curve"
and time-of-use pricing patterns.

In production, this module would integrate with:
- WattTime API (real-time carbon data)
- ISO market APIs (CAISO, ERCOT, PJM)
- Weather services for renewable forecasting
"""

import math
import random
from datetime import datetime, timedelta

import pandas as pd

from arboric.core.models import GridWindow

# Regional grid profiles (baseline characteristics)
REGION_PROFILES = {
    "US-WEST": {
        "base_carbon": 350,  # gCO2/kWh
        "carbon_amplitude": 200,  # Swing from solar
        "base_price": 0.12,  # $/kWh
        "price_amplitude": 0.08,
        "solar_peak_hour": 13,  # 1 PM
        "price_peak_hour": 18,  # 6 PM (evening ramp)
        "timezone_offset": -8,
    },
    "US-EAST": {
        "base_carbon": 420,
        "carbon_amplitude": 150,
        "base_price": 0.14,
        "price_amplitude": 0.07,
        "solar_peak_hour": 13,
        "price_peak_hour": 17,
        "timezone_offset": -5,
    },
    "EU-WEST": {
        "base_carbon": 280,
        "carbon_amplitude": 180,
        "base_price": 0.18,
        "price_amplitude": 0.10,
        "solar_peak_hour": 14,
        "price_peak_hour": 19,
        "timezone_offset": 1,
    },
    "NORDIC": {
        "base_carbon": 80,  # Hydro-dominated
        "carbon_amplitude": 40,
        "base_price": 0.08,
        "price_amplitude": 0.04,
        "solar_peak_hour": 13,
        "price_peak_hour": 18,
        "timezone_offset": 1,
    },
}


class MockGrid:
    """
    Simulates realistic electricity grid behavior.

    Models two key phenomena:
    1. The "Duck Curve" - Midday solar depression in carbon intensity
    2. TOU Pricing - Evening peak pricing from demand surge

    The simulation uses overlapping sine waves with randomization
    to produce realistic, varied forecasts for demo purposes.
    """

    def __init__(self, region: str = "US-WEST", seed: int | None = None):
        """
        Initialize the grid simulator.

        Args:
            region: Grid region identifier (US-WEST, US-EAST, EU-WEST, NORDIC)
            seed: Random seed for reproducible forecasts (None for varied demos)
        """
        self.region = region
        if region not in REGION_PROFILES:
            raise ValueError(f"Unknown region: {region}. Available: {list(REGION_PROFILES.keys())}")

        self.profile = REGION_PROFILES[region]

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

    def _calculate_price(self, hour: float) -> float:
        """
        Calculate electricity price for a given hour.

        Models wholesale electricity pricing with STRONG solar correlation:
        - Solar Peak (11am-3pm): LOWEST prices due to oversupply
        - Evening Peak (5pm-9pm): HIGHEST prices (demand + no solar)
        - Night: Moderate prices

        Key insight: In high-solar markets (CAISO, ERCOT), midday solar
        creates negative wholesale prices. This means BOTH cheap AND clean!
        """
        base = self.profile["base_price"]
        amplitude = self.profile["price_amplitude"]

        # Solar suppression - SAME factor as carbon, creating correlation
        # During solar peak, prices drop significantly due to oversupply
        solar_factor = self._calculate_solar_factor(hour)
        solar_price_reduction = amplitude * 1.5 * solar_factor  # Strong price drop

        # Evening demand spike (5pm-9pm) - highest prices
        evening_peak = 18.5
        evening_width = 2.0
        evening_component = 0
        if 15 <= hour <= 22:
            evening_distance = abs(hour - evening_peak)
            evening_component = (
                amplitude * 1.2 * math.exp(-(evening_distance**2) / (2 * evening_width**2))
            )

        # Night baseline (moderate - neither peak nor solar)
        night_component = 0
        if hour < 6 or hour > 22:
            night_component = amplitude * 0.3

        # Random market noise (reduced for predictable demo)
        noise = self._random.gauss(0, 0.005)

        price = (
            base
            - solar_price_reduction
            + evening_component
            + night_component
            + self._daily_price_shift
            + noise
        )
        return max(0.02, min(0.50, price))  # Clamp to realistic range

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

    def get_forecast(self, hours: int = 24, resolution_minutes: int = 60, start_time: datetime | None = None) -> pd.DataFrame:
        """
        Generate a grid forecast for the specified time horizon.

        Args:
            hours: Forecast horizon in hours
            resolution_minutes: Time resolution (default 60 = hourly)
            start_time: Optional start time (defaults to current time for realistic forecasts)

        Returns:
            DataFrame with timestamp, co2_intensity, price, renewable_percentage
        """
        now = (start_time or datetime.now()).replace(minute=0, second=0, microsecond=0)
        windows = []

        intervals = (hours * 60) // resolution_minutes

        for i in range(intervals):
            timestamp = now + timedelta(minutes=i * resolution_minutes)
            hour_of_day = timestamp.hour + timestamp.minute / 60

            # Add slight trend drift for longer forecasts
            trend_factor = 1 + (i / intervals) * self._random.uniform(-0.05, 0.05)

            # Calculate values with trend factor and ensure they stay in valid ranges
            co2 = self._calculate_carbon_intensity(hour_of_day) * trend_factor
            price = self._calculate_price(hour_of_day) * trend_factor

            window = GridWindow(
                timestamp=timestamp,
                co2_intensity=max(50, min(800, co2)),  # Re-clamp after trend factor
                price=max(0.02, min(0.50, price)),  # Re-clamp after trend factor
                renewable_percentage=self._calculate_renewable_percentage(hour_of_day),
                region=self.region,
                confidence=max(0.5, 1.0 - (i / intervals) * 0.3),  # Confidence decreases with time
            )
            windows.append(window)

        # Convert to DataFrame
        df = pd.DataFrame([w.model_dump() for w in windows])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        return df

    def get_current_conditions(self) -> GridWindow:
        """Get current grid conditions (single window)."""
        now = datetime.now()
        hour_of_day = now.hour + now.minute / 60

        return GridWindow(
            timestamp=now,
            co2_intensity=self._calculate_carbon_intensity(hour_of_day),
            price=self._calculate_price(hour_of_day),
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

        # Detect price spikes
        price_threshold = self.profile["base_price"] + self.profile["price_amplitude"] * 0.8
        high_price_periods = forecast_df[forecast_df["price"] > price_threshold]
        if not high_price_periods.empty:
            events.append(
                {
                    "type": "PRICE_SPIKE",
                    "severity": "warning",
                    "start": high_price_periods.index[0],
                    "description": f"Price spike expected (${high_price_periods['price'].max():.3f}/kWh)",
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

        # Detect cheap windows
        cheap_threshold = self.profile["base_price"] - self.profile["price_amplitude"] * 0.5
        cheap_periods = forecast_df[forecast_df["price"] < cheap_threshold]
        if not cheap_periods.empty:
            events.append(
                {
                    "type": "LOW_PRICE",
                    "severity": "opportunity",
                    "start": cheap_periods.index[0],
                    "description": f"Low-price window available (${cheap_periods['price'].min():.3f}/kWh)",
                }
            )

        return events


def get_grid(region: str = "US-WEST") -> MockGrid:
    """Factory function to create a grid oracle for a region."""
    return MockGrid(region=region)
