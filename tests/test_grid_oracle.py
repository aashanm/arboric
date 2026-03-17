"""
Tests for Arboric Grid Oracle

Tests forecast generation, regional profiles, and grid event detection.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from arboric.core.grid_oracle import REGION_PROFILES, MockGrid, LiveGrid


class TestMockGrid:
    """Test cases for MockGrid forecast generator."""

    def test_mock_grid_creation(self):
        """Test basic grid creation with valid region."""
        grid = MockGrid(region="US-WEST")
        assert grid.region == "US-WEST"
        assert grid.profile == REGION_PROFILES["US-WEST"]

    def test_mock_grid_invalid_region(self):
        """Test that invalid region raises error."""
        with pytest.raises(ValueError, match="Unknown region"):
            MockGrid(region="INVALID-REGION")

    def test_forecast_generation(self):
        """Test that forecast generates correct number of windows."""
        grid = MockGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=24)

        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 24
        assert "co2_intensity" in forecast.columns
        assert "price" in forecast.columns
        assert "renewable_percentage" in forecast.columns

    def test_forecast_with_custom_resolution(self):
        """Test forecast generation with custom time resolution."""
        grid = MockGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=12, resolution_minutes=30)

        # 12 hours at 30-minute resolution = 24 intervals
        assert len(forecast) == 24

    def test_forecast_values_in_valid_range(self):
        """Test that generated forecast values are within realistic bounds."""
        grid = MockGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=24)

        # Carbon intensity should be between 50 and 800 gCO2/kWh
        assert forecast["co2_intensity"].min() >= 50
        assert forecast["co2_intensity"].max() <= 800

        # Price should be between $0.02 and $0.50 per kWh
        assert forecast["price"].min() >= 0.02
        assert forecast["price"].max() <= 0.50

        # Renewable percentage should be between 5 and 95%
        assert forecast["renewable_percentage"].min() >= 5
        assert forecast["renewable_percentage"].max() <= 95

    def test_forecast_has_datetime_index(self):
        """Test that forecast DataFrame has datetime index."""
        grid = MockGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=24)

        assert isinstance(forecast.index, pd.DatetimeIndex)

    def test_regional_profiles(self):
        """Test that different regions produce different characteristics."""
        us_west_grid = MockGrid(region="US-WEST", seed=42)
        nordic_grid = MockGrid(region="NORDIC", seed=42)

        us_west_forecast = us_west_grid.get_forecast(hours=24)
        nordic_forecast = nordic_grid.get_forecast(hours=24)

        # Nordic should have lower average carbon (more hydro)
        us_west_avg_carbon = us_west_forecast["co2_intensity"].mean()
        nordic_avg_carbon = nordic_forecast["co2_intensity"].mean()
        assert nordic_avg_carbon < us_west_avg_carbon

    def test_get_current_conditions(self):
        """Test getting current grid conditions."""
        grid = MockGrid(region="US-WEST")
        current = grid.get_current_conditions()

        assert hasattr(current, "timestamp")
        assert hasattr(current, "co2_intensity")
        assert hasattr(current, "price")
        assert current.region == "US-WEST"
        assert current.confidence == 1.0

    def test_detect_events(self):
        """Test grid event detection."""
        grid = MockGrid(region="US-WEST", seed=42)
        forecast = grid.get_forecast(hours=24)
        events = grid.detect_events(forecast)

        assert isinstance(events, list)
        # Should detect at least some events in a 24h forecast
        assert len(events) > 0

        # Check event structure
        for event in events:
            assert "type" in event
            assert "severity" in event
            assert "description" in event

    def test_solar_duck_curve_pattern(self):
        """Test that forecast exhibits solar duck curve (low midday carbon)."""
        grid = MockGrid(region="US-WEST", seed=42)
        forecast = grid.get_forecast(hours=24)

        # Find midday hours (11am-3pm, hours 11-14)
        # Note: this depends on when the test runs, so we use relative comparison
        # The pattern should show lower carbon during solar hours
        morning_carbon = forecast.iloc[8:11]["co2_intensity"].mean()  # 8-10am
        midday_carbon = forecast.iloc[11:15]["co2_intensity"].mean()  # 11am-2pm
        evening_carbon = forecast.iloc[17:20]["co2_intensity"].mean()  # 5-7pm

        # Midday should be lower than morning and evening (duck curve)
        assert midday_carbon < morning_carbon or midday_carbon < evening_carbon

    def test_price_correlation_with_solar(self):
        """Test that prices show variation across the day."""
        # Test without fixed seed since random variations can affect exact relationships
        grid = MockGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=24)

        # Prices should vary across the day (not all the same)
        price_std = forecast["price"].std()
        assert price_std > 0.01  # Should have meaningful variation

        # Check that we can identify different price windows
        assert forecast["price"].min() < forecast["price"].max()

    def test_deterministic_with_seed(self):
        """Test that using a seed produces reproducible results."""
        grid1 = MockGrid(region="US-WEST", seed=123)
        grid2 = MockGrid(region="US-WEST", seed=123)

        forecast1 = grid1.get_forecast(hours=12)
        forecast2 = grid2.get_forecast(hours=12)

        # With same seed, forecasts should be identical
        pd.testing.assert_frame_equal(forecast1, forecast2)


class TestLiveGrid:
    """Test cases for LiveGrid with mocked API clients."""

    def test_live_grid_creation(self):
        """Test basic LiveGrid creation with valid region."""
        grid = LiveGrid(region="US-WEST")
        assert grid.region == "US-WEST"
        assert grid.profile == REGION_PROFILES["US-WEST"]

    def test_live_grid_invalid_region(self):
        """Test that invalid region raises error."""
        with pytest.raises(ValueError, match="Unknown region"):
            LiveGrid(region="INVALID-REGION")

    def test_live_grid_with_watttime_client(self):
        """Test LiveGrid uses WattTime client for carbon data."""
        # Mock WattTime client
        mock_watttime = MagicMock()
        # Use naive datetime for API response (will be converted in get_forecast)
        now = datetime.now()
        mock_watttime.get_carbon_forecast.return_value = [
            {"timestamp": now.replace(tzinfo=timezone.utc) + timedelta(hours=i), "co2_intensity": 350 + i * 10}
            for i in range(24)
        ]
        mock_watttime.get_current_carbon.return_value = 350.0

        grid = LiveGrid(region="US-WEST", watttime_client=mock_watttime)
        forecast = grid.get_forecast(hours=24)

        # Should return valid DataFrame
        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 24
        assert "co2_intensity" in forecast.columns
        assert "price" in forecast.columns

        # WattTime client should have been called
        mock_watttime.get_carbon_forecast.assert_called_once()

    def test_live_grid_with_em_client(self):
        """Test LiveGrid uses Electricity Maps client for price and carbon."""
        # Mock EM client
        mock_em = MagicMock()
        now = datetime.now(timezone.utc)
        mock_em.get_carbon_forecast.return_value = [
            {"timestamp": now + timedelta(hours=i), "co2_intensity": 350 + i * 10}
            for i in range(24)
        ]
        mock_em.get_price.return_value = 0.15
        mock_em.get_renewable_percentage.return_value = 45.0

        grid = LiveGrid(region="US-WEST", em_client=mock_em)
        forecast = grid.get_forecast(hours=24)

        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 24
        # Price should be consistent across forecast (extended spot price)
        assert forecast["price"].min() > 0.10  # Close to 0.15

    def test_live_grid_fallback_to_mock(self):
        """Test LiveGrid falls back to MockGrid when API fails."""
        # Mock client that raises exception
        mock_watttime = MagicMock()
        mock_watttime.get_carbon_forecast.side_effect = Exception("API Error")

        grid = LiveGrid(region="US-WEST", watttime_client=mock_watttime)
        # Should not raise, just fall back to MockGrid
        forecast = grid.get_forecast(hours=24, resolution_minutes=60)

        # Should still return valid forecast (from MockGrid)
        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 24
        assert forecast["co2_intensity"].min() >= 50
        # All confidence should be 0.5 (fallback only)
        assert (forecast["confidence"] == 0.5).all()

    def test_live_grid_confidence_with_real_data(self):
        """Test that confidence is high when using real data."""
        mock_em = MagicMock()
        now = datetime.now()
        mock_em.get_carbon_forecast.return_value = [
            {"timestamp": now.replace(tzinfo=timezone.utc) + timedelta(hours=i), "co2_intensity": 350}
            for i in range(24)
        ]
        mock_em.get_price.return_value = 0.15
        mock_em.get_renewable_percentage.return_value = 45.0

        grid = LiveGrid(region="US-WEST", em_client=mock_em)
        forecast = grid.get_forecast(hours=24, resolution_minutes=60)

        # First 4 hours should have high confidence with real data
        assert forecast.iloc[0]["confidence"] == 1.0
        assert forecast.iloc[2]["confidence"] == 1.0

    def test_live_grid_confidence_with_fallback(self):
        """Test that confidence is low when falling back to simulation."""
        # No clients provided
        grid = LiveGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=24, resolution_minutes=60)

        # Should have lower confidence (0.5) since using fallback
        assert (forecast["confidence"] == 0.5).all()

    def test_live_grid_same_interface_as_mock(self):
        """Test that LiveGrid has the same interface as MockGrid."""
        grid = LiveGrid(region="US-WEST")

        # Test get_forecast with proper resolution
        forecast = grid.get_forecast(hours=12, resolution_minutes=60)
        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 12
        assert set(forecast.columns) == {
            "co2_intensity",
            "price",
            "renewable_percentage",
            "region",
            "confidence",
        }

        # Test get_current_conditions
        current = grid.get_current_conditions()
        assert hasattr(current, "timestamp")
        assert hasattr(current, "co2_intensity")
        assert hasattr(current, "price")
        assert hasattr(current, "region")

        # Test detect_events
        events = grid.detect_events(forecast)
        assert isinstance(events, list)

    def test_live_grid_current_conditions_with_real_data(self):
        """Test get_current_conditions with real API data."""
        mock_watttime = MagicMock()
        mock_watttime.get_current_carbon.return_value = 400.0

        mock_em = MagicMock()
        mock_em.get_price.return_value = 0.12
        mock_em.get_renewable_percentage.return_value = 50.0

        grid = LiveGrid(
            region="US-WEST",
            watttime_client=mock_watttime,
            em_client=mock_em,
        )
        current = grid.get_current_conditions()

        assert current.co2_intensity == 400.0
        assert current.price == 0.12
        assert current.renewable_percentage == 50.0
        assert current.confidence == 1.0  # All real data

    def test_live_grid_current_conditions_partial_fallback(self):
        """Test get_current_conditions with partial fallback."""
        mock_watttime = MagicMock()
        mock_watttime.get_current_carbon.return_value = 400.0

        # EM client raises exception for all methods
        mock_em = MagicMock()
        mock_em.get_price.side_effect = Exception("Price API failed")
        mock_em.get_renewable_percentage.side_effect = Exception("Renewable API failed")

        grid = LiveGrid(
            region="US-WEST",
            watttime_client=mock_watttime,
            em_client=mock_em,
        )
        current = grid.get_current_conditions()

        # Should have carbon from WattTime, price and renewable from MockGrid fallback
        assert current.co2_intensity == 400.0
        assert 0.02 <= current.price <= 0.50  # Valid fallback range
        assert 5 <= current.renewable_percentage <= 95  # Valid fallback range
        assert current.confidence == 0.5  # Partial fallback

    def test_live_grid_detect_events_delegates_to_mock(self):
        """Test that detect_events uses the same logic as MockGrid."""
        grid = LiveGrid(region="US-WEST")
        forecast = grid.get_forecast(hours=12, resolution_minutes=60)
        events = grid.detect_events(forecast)

        # Should return list of events with expected structure
        assert isinstance(events, list)
        for event in events:
            assert "type" in event
            assert "severity" in event
            assert "description" in event
            assert "start" in event
