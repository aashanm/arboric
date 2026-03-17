"""
Electricity Maps API Integration

Integrates with Electricity Maps API v3 for real-time carbon intensity,
electricity prices, and renewable percentage data.

API docs: https://api.electricitymap.org/
"""

from datetime import datetime
import logging

import httpx

logger = logging.getLogger(__name__)

# Region mapping from Arboric regions to Electricity Maps zones
EM_REGION_MAP = {
    "US-WEST": "US-CAL-CISO",
    "US-EAST": "US-PJM",
    "EU-WEST": "DE",
    "NORDIC": "SE",
}


class ElectricityMapsError(Exception):
    """Raised when an Electricity Maps API call fails."""

    pass


class ElectricityMapsClient:
    """Client for Electricity Maps API v3.

    Provides access to real-time carbon intensity, electricity prices, and
    renewable energy percentages.
    """

    BASE_URL = "https://api.electricitymap.org/v3"

    def __init__(self, api_key: str) -> None:
        """Initialize Electricity Maps client with API key.

        Args:
            api_key: Electricity Maps API key
        """
        self._api_key = api_key
        self._client = httpx.Client(
            timeout=30.0,
            headers={"auth-token": api_key},
        )

    def get_carbon_intensity(self, region: str) -> float:
        """Fetch current carbon intensity for a region.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)

        Returns:
            Current CO2 intensity in gCO2/kWh

        Raises:
            ElectricityMapsError: If API call fails or region not supported
        """
        if region not in EM_REGION_MAP:
            raise ElectricityMapsError(f"Region {region} not supported by Electricity Maps")

        zone = EM_REGION_MAP[region]

        try:
            response = self._client.get(
                f"{self.BASE_URL}/carbon-intensity/latest",
                params={"zone": zone},
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get("carbonIntensity", 0.0))
        except httpx.HTTPError as e:
            raise ElectricityMapsError(
                f"Failed to fetch carbon intensity for {region}: {e}"
            )

    def get_carbon_forecast(self, region: str) -> list[dict]:
        """Fetch carbon intensity forecast for a region.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)

        Returns:
            List of dicts with 'timestamp' (datetime) and 'co2_intensity' (gCO2/kWh)

        Raises:
            ElectricityMapsError: If API call fails or region not supported
        """
        if region not in EM_REGION_MAP:
            raise ElectricityMapsError(f"Region {region} not supported by Electricity Maps")

        zone = EM_REGION_MAP[region]

        try:
            response = self._client.get(
                f"{self.BASE_URL}/carbon-intensity/forecast",
                params={"zone": zone},
            )
            response.raise_for_status()
            data = response.json()

            forecast = []
            for point in data.get("forecast", []):
                # Parse ISO 8601 datetime
                timestamp = datetime.fromisoformat(point["datetime"].replace("Z", "+00:00"))
                co2_intensity = float(point.get("carbonIntensity", 0.0))
                forecast.append(
                    {
                        "timestamp": timestamp,
                        "co2_intensity": co2_intensity,
                    }
                )
            return forecast
        except httpx.HTTPError as e:
            raise ElectricityMapsError(
                f"Failed to fetch carbon forecast for {region}: {e}"
            )

    def get_price(self, region: str) -> float | None:
        """Fetch current electricity price for a region.

        Note: Not all zones have price data available.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)

        Returns:
            Current price in $/kWh, or None if not available

        Raises:
            ElectricityMapsError: If API call fails (other than price unavailable)
        """
        if region not in EM_REGION_MAP:
            raise ElectricityMapsError(f"Region {region} not supported by Electricity Maps")

        zone = EM_REGION_MAP[region]

        try:
            response = self._client.get(
                f"{self.BASE_URL}/price/latest",
                params={"zone": zone},
            )
            # Some zones don't have price data, return None instead of raising
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            price = data.get("price")
            # Price is in $/MWh, convert to $/kWh
            if price is not None:
                return float(price) / 1000.0
            return None
        except httpx.HTTPError as e:
            if "404" in str(e):
                return None
            raise ElectricityMapsError(f"Failed to fetch price for {region}: {e}")

    def get_renewable_percentage(self, region: str) -> float | None:
        """Fetch renewable energy percentage for a region.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)

        Returns:
            Percentage of renewable energy (0-100), or None if not available

        Raises:
            ElectricityMapsError: If API call fails (other than data unavailable)
        """
        if region not in EM_REGION_MAP:
            raise ElectricityMapsError(f"Region {region} not supported by Electricity Maps")

        zone = EM_REGION_MAP[region]

        try:
            response = self._client.get(
                f"{self.BASE_URL}/power-breakdown/latest",
                params={"zone": zone},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            power_data = data.get("powerBreakdown", {})

            # Calculate renewable percentage from power breakdown
            renewable_sources = ["wind", "solar", "hydro", "nuclear"]
            renewable_capacity = sum(
                power_data.get(source, 0) for source in renewable_sources
            )
            total_capacity = sum(power_data.values())

            if total_capacity == 0:
                return None

            percentage = (renewable_capacity / total_capacity) * 100
            return min(100.0, max(0.0, percentage))
        except httpx.HTTPError as e:
            if "404" in str(e):
                return None
            raise ElectricityMapsError(
                f"Failed to fetch renewable percentage for {region}: {e}"
            )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "ElectricityMapsClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Context manager exit."""
        self.close()
