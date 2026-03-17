"""
WattTime API Integration

Integrates with the WattTime API v3 for real-time and forecast
carbon intensity (MOER - Marginal Operating Emissions Rate) data.

API docs: https://www.watttime.org/api-documentation/
"""

from datetime import datetime, timedelta, timezone
import logging

import httpx

logger = logging.getLogger(__name__)

# Region mapping from Arboric regions to WattTime balancing authority abbreviations
WATTTIME_REGION_MAP = {
    "US-WEST": "CAISO_NP15",
    "US-EAST": "PJM",
    "EU-WEST": "DE",
    "NORDIC": "SE",
}

# Conversion factor: lbs CO2/MWh (MOER) → gCO2/kWh
# 1 lbs = 0.453592 kg, 1 MWh = 1000 kWh
# lbs CO2/MWh * 0.453592 = kg CO2/MWh = g CO2/kWh
LBS_CO2_MWH_TO_G_CO2_KWH = 0.453592

# Token cache validity: WattTime tokens expire after ~60 minutes, refresh at 55 minutes
TOKEN_REFRESH_INTERVAL = timedelta(minutes=55)


class WattTimeAuthError(Exception):
    """Raised when WattTime authentication fails."""

    pass


class WattTimeAPIError(Exception):
    """Raised when a WattTime API call fails."""

    pass


class WattTimeClient:
    """Client for WattTime API v3.

    Handles authentication, token caching, and forecast/current conditions fetching.
    """

    BASE_URL = "https://api.watttime.org/v3"

    def __init__(self, username: str, password: str) -> None:
        """Initialize WattTime client with credentials.

        Args:
            username: WattTime API username
            password: WattTime API password
        """
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._client = httpx.Client(timeout=30.0)

    def _authenticate(self) -> str:
        """Authenticate with WattTime API and cache token.

        Returns:
            Bearer token for authorization

        Raises:
            WattTimeAuthError: If authentication fails
        """
        try:
            response = self._client.post(
                f"{self.BASE_URL}/login",
                json={"username": self._username, "password": self._password},
            )
            response.raise_for_status()
            data = response.json()
            token = data.get("token")
            if not token:
                raise WattTimeAuthError("No token in authentication response")
            self._token = token
            self._token_expiry = datetime.now(timezone.utc) + TOKEN_REFRESH_INTERVAL
            logger.debug("WattTime authentication successful")
            return token
        except httpx.HTTPError as e:
            raise WattTimeAuthError(f"WattTime authentication failed: {e}")

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers, refreshing token if needed.

        Returns:
            Dictionary with Authorization header
        """
        # Check if token exists and is still valid
        if (
            self._token
            and self._token_expiry
            and datetime.now(timezone.utc) < self._token_expiry
        ):
            return {"Authorization": f"Bearer {self._token}"}

        # Token expired or doesn't exist, re-authenticate
        token = self._authenticate()
        return {"Authorization": f"Bearer {token}"}

    def get_carbon_forecast(self, region: str, hours: int = 24) -> list[dict]:
        """Fetch carbon intensity forecast for a region.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)
            hours: Forecast horizon in hours (default 24)

        Returns:
            List of dicts with 'timestamp' (datetime) and 'co2_intensity' (gCO2/kWh)

        Raises:
            WattTimeAPIError: If API call fails
        """
        if region not in WATTTIME_REGION_MAP:
            raise WattTimeAPIError(f"Region {region} not supported by WattTime")

        ba_abbrev = WATTTIME_REGION_MAP[region]
        headers = self._get_headers()

        try:
            response = self._client.get(
                f"{self.BASE_URL}/forecast",
                headers=headers,
                params={
                    "signal_type": "co2_moer",
                    "region": ba_abbrev,
                    "horizon_hours": hours,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Convert MOER data to standard format
            forecast = []
            for point in data.get("data", []):
                timestamp = datetime.fromisoformat(point["point_time"].replace("Z", "+00:00"))
                # Convert lbs CO2/MWh to gCO2/kWh
                co2_intensity = point["value"] * LBS_CO2_MWH_TO_G_CO2_KWH
                forecast.append(
                    {
                        "timestamp": timestamp,
                        "co2_intensity": co2_intensity,
                    }
                )
            return forecast
        except httpx.HTTPError as e:
            raise WattTimeAPIError(f"Failed to fetch WattTime forecast: {e}")

    def get_current_carbon(self, region: str) -> float:
        """Fetch current carbon intensity for a region.

        Args:
            region: Arboric region (US-WEST, US-EAST, EU-WEST, NORDIC)

        Returns:
            Current CO2 intensity in gCO2/kWh

        Raises:
            WattTimeAPIError: If API call fails
        """
        if region not in WATTTIME_REGION_MAP:
            raise WattTimeAPIError(f"Region {region} not supported by WattTime")

        ba_abbrev = WATTTIME_REGION_MAP[region]
        headers = self._get_headers()

        try:
            response = self._client.get(
                f"{self.BASE_URL}/signal-index",
                headers=headers,
                params={
                    "signal_type": "co2_moer",
                    "region": ba_abbrev,
                },
            )
            response.raise_for_status()
            data = response.json()
            # Convert lbs CO2/MWh to gCO2/kWh
            moer = data.get("data", [{}])[0].get("value", 0.0)
            return moer * LBS_CO2_MWH_TO_G_CO2_KWH
        except httpx.HTTPError as e:
            raise WattTimeAPIError(f"Failed to fetch current WattTime carbon: {e}")

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "WattTimeClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Context manager exit."""
        self.close()
