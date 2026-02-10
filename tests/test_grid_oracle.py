"""
Tests for Arboric Grid Oracle

Tests forecast generation, regional profiles, and grid event detection.
"""

import pytest
import pandas as pd
from datetime import datetime
from arboric.core.grid_oracle import MockGrid, REGION_PROFILES


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
        """Test that prices are lower during solar peak hours."""
        grid = MockGrid(region="US-WEST", seed=42)
        forecast = grid.get_forecast(hours=24)

        # Midday prices should generally be lower than evening peak
        midday_price = forecast.iloc[11:15]["price"].mean()  # 11am-2pm
        evening_price = forecast.iloc[17:20]["price"].mean()  # 5-7pm

        # Evening should be more expensive (demand peak, no solar)
        assert evening_price > midday_price

    def test_deterministic_with_seed(self):
        """Test that using a seed produces reproducible results."""
        grid1 = MockGrid(region="US-WEST", seed=123)
        grid2 = MockGrid(region="US-WEST", seed=123)

        forecast1 = grid1.get_forecast(hours=12)
        forecast2 = grid2.get_forecast(hours=12)

        # With same seed, forecasts should be identical
        pd.testing.assert_frame_equal(forecast1, forecast2)
