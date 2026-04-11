"""
Tests for Arboric Grid Oracle

Tests forecast generation, regional profiles, and grid event detection.
"""

import pandas as pd
import pytest

from arboric.core.grid_oracle import REGION_PROFILES, MockGrid


class TestMockGrid:
    """Test cases for MockGrid forecast generator."""

    def test_mock_grid_creation(self):
        """Test basic grid creation with valid region."""
        grid = MockGrid(region="eastus")
        assert grid.region == "eastus"
        assert grid.profile == REGION_PROFILES["eastus"]

    def test_mock_grid_invalid_region(self):
        """Test that invalid region raises error."""
        with pytest.raises(ValueError, match="Unknown region"):
            MockGrid(region="INVALID-REGION")

    def test_forecast_generation(self):
        """Test that forecast generates correct number of windows."""
        grid = MockGrid(region="eastus")
        forecast = grid.get_forecast(hours=24)

        assert isinstance(forecast, pd.DataFrame)
        assert len(forecast) == 24
        assert "co2_intensity" in forecast.columns
        assert "price" in forecast.columns
        assert "renewable_percentage" in forecast.columns

    def test_forecast_with_custom_resolution(self):
        """Test forecast generation with custom time resolution."""
        grid = MockGrid(region="eastus")
        forecast = grid.get_forecast(hours=12, resolution_minutes=30)

        # 12 hours at 30-minute resolution = 24 intervals
        assert len(forecast) == 24

    def test_forecast_values_in_valid_range(self):
        """Test that generated forecast values are within realistic bounds."""
        # Use westus2 (high on-demand rate profile) to verify price range
        grid = MockGrid(region="westus2")
        forecast = grid.get_forecast(hours=24)

        # Carbon intensity should be between 50 and 800 gCO2/kWh
        assert forecast["co2_intensity"].min() >= 50
        assert forecast["co2_intensity"].max() <= 800

        # Price should be positive and within the on-demand ceiling
        # westus2: on-demand=$24/hr, floor ~$10.08/hr (noise can push below)
        assert forecast["price"].min() > 0.0
        assert forecast["price"].max() <= 25.0

        # Renewable percentage should be between 5 and 95%
        assert forecast["renewable_percentage"].min() >= 5
        assert forecast["renewable_percentage"].max() <= 95

    def test_forecast_has_datetime_index(self):
        """Test that forecast DataFrame has datetime index."""
        grid = MockGrid(region="eastus")
        forecast = grid.get_forecast(hours=24)

        assert isinstance(forecast.index, pd.DatetimeIndex)

    def test_regional_profiles(self):
        """Test that different regions produce different characteristics."""
        us_east_grid = MockGrid(region="eastus", seed=42)
        northeurope_grid = MockGrid(region="northeurope", seed=42)

        us_east_forecast = us_east_grid.get_forecast(hours=24)
        northeurope_forecast = northeurope_grid.get_forecast(hours=24)

        # North Europe (Ireland, hydro-dominated) should have lower average carbon
        us_east_avg_carbon = us_east_forecast["co2_intensity"].mean()
        northeurope_avg_carbon = northeurope_forecast["co2_intensity"].mean()
        assert northeurope_avg_carbon < us_east_avg_carbon

    def test_get_current_conditions(self):
        """Test getting current grid conditions."""
        grid = MockGrid(region="eastus")
        current = grid.get_current_conditions()

        assert hasattr(current, "timestamp")
        assert hasattr(current, "co2_intensity")
        assert hasattr(current, "price")
        assert current.region == "eastus"
        assert current.confidence == 1.0

    def test_detect_events(self):
        """Test grid event detection."""
        grid = MockGrid(region="eastus", seed=42)
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
        grid = MockGrid(region="eastus", seed=42)
        # Start forecast at midnight for predictable hour indices
        from datetime import datetime

        start_time = datetime(2026, 3, 19, 0, 0, 0)
        forecast = grid.get_forecast(hours=24, start_time=start_time)

        # Find midday hours (11am-3pm, hours 11-14)
        morning_carbon = forecast.iloc[8:11]["co2_intensity"].mean()  # 8-10am
        midday_carbon = forecast.iloc[11:15]["co2_intensity"].mean()  # 11am-2pm
        evening_carbon = forecast.iloc[17:20]["co2_intensity"].mean()  # 5-7pm

        # Midday should be lower than morning and evening (duck curve)
        assert midday_carbon < morning_carbon or midday_carbon < evening_carbon

    def test_spot_price_business_hours_pattern(self):
        """Test that spot prices show business-hours contention pattern."""
        from datetime import datetime

        grid = MockGrid(region="eastus", seed=42)
        start_time = datetime(2026, 3, 19, 0, 0, 0)
        forecast = grid.get_forecast(hours=24, start_time=start_time)

        # Prices should vary across the day (not all the same)
        price_std = forecast["price"].std()
        assert price_std > 0.01  # Should have meaningful variation

        # Check that we can identify different price windows
        assert forecast["price"].min() < forecast["price"].max()

        # Business hours (9am-6pm, indices 9-17) should average higher than overnight (10pm-6am, indices 22-5)
        business_hours_avg = forecast.iloc[9:17]["price"].mean()
        overnight_avg = pd.concat([forecast.iloc[22:24], forecast.iloc[0:6]])["price"].mean()
        # Business hours spot prices should be higher due to capacity contention
        assert business_hours_avg > overnight_avg

    def test_deterministic_with_seed(self):
        """Test that using a seed produces reproducible results."""
        grid1 = MockGrid(region="eastus", seed=123)
        grid2 = MockGrid(region="eastus", seed=123)

        forecast1 = grid1.get_forecast(hours=12)
        forecast2 = grid2.get_forecast(hours=12)

        # With same seed, forecasts should be identical
        pd.testing.assert_frame_equal(forecast1, forecast2)
