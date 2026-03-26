"""
Parity Tests: JS Frontend vs Python Backend

This test suite validates that the JavaScript implementation (site/index.html)
and Python implementation (arboric/core/autopilot.py) produce identical results
on the same inputs within an acceptable epsilon.

Purpose: Catch any drift between implementations before it ships.
Any change to the Python optimization algorithm must pass these tests.
"""

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from arboric.core.autopilot import Autopilot, OptimizationConfig
from arboric.core.models import Workload

# Constants from site/index.html (source of truth for JS)
JS_PRICE_CEILING = 35.0
JS_CARBON_CEILING = 600.0
JS_DEFAULT_PRICE_WEIGHT = 0.7
JS_DEFAULT_CARBON_WEIGHT = 0.3


class JavaScriptOptimizationPort:
    """
    Python implementation of the JavaScript optimizeSchedule function from site/index.html.

    This is NOT an optimization algorithm itself, but a 1:1 port of the JS logic
    to validate parity. Do not modify this without updating the JS version first.

    Algorithm differences from Python autopilot.py:
    - Simplified window calculation: Math.round(durationHours) instead of resolution-aware
    - Simpler deadline handling: linear index-based instead of timestamp-based
    - No support for cost constraints or priority handling
    - Array-based instead of DataFrame-based
    """

    def __init__(
        self,
        cost_weight: float = JS_DEFAULT_PRICE_WEIGHT,
        carbon_weight: float = JS_DEFAULT_CARBON_WEIGHT,
    ):
        self.cost_weight = cost_weight
        self.carbon_weight = carbon_weight
        self.price_ceiling = JS_PRICE_CEILING
        self.carbon_ceiling = JS_CARBON_CEILING

    def score_window(self, forecast_slice: list[dict[str, float]]) -> dict[str, Any]:
        """Score a single window (JS version)."""
        if not forecast_slice:
            return {"score": float("inf"), "avgPrice": 0, "avgCarbon": 0, "cost": 0, "carbonKg": 0}

        avg_price = sum(w["price"] for w in forecast_slice) / len(forecast_slice)
        avg_carbon = sum(w["co2_intensity"] for w in forecast_slice) / len(forecast_slice)

        p_norm = min(avg_price / self.price_ceiling, 1.0) * 100
        c_norm = min(avg_carbon / self.carbon_ceiling, 1.0) * 100

        return {
            "score": p_norm * self.cost_weight + c_norm * self.carbon_weight,
            "avgPrice": avg_price,
            "avgCarbon": avg_carbon,
            "cost": avg_price * 1.0,  # placeholder duration
            "carbonKg": (avg_carbon * 1.0) / 1000,  # placeholder energy
        }

    def optimize_schedule(
        self,
        forecast: list[dict[str, float]],
        duration_hours: float,
        power_draw_kw: float,
        deadline_hours: float,
    ) -> dict[str, Any]:
        """
        JS implementation of optimizeSchedule.

        Args:
            forecast: List of hourly forecast points with 'price' and 'co2_intensity'
            duration_hours: Workload duration in hours
            power_draw_kw: Power draw in kW
            deadline_hours: Deadline in hours

        Returns:
            Dict with optimization results
        """
        energy_kwh = power_draw_kw * duration_hours
        windows_needed = max(1, round(duration_hours))

        # Baseline (immediate start)
        baseline_slice = forecast[:windows_needed]
        baseline_avg_price = sum(w["price"] for w in baseline_slice) / len(baseline_slice)
        baseline_avg_carbon = sum(w["co2_intensity"] for w in baseline_slice) / len(baseline_slice)
        baseline_cost = baseline_avg_price * duration_hours
        baseline_carbon_kg = (baseline_avg_carbon * energy_kwh) / 1000

        def score_window(slice_data):
            avg_p = sum(w["price"] for w in slice_data) / len(slice_data)
            avg_c = sum(w["co2_intensity"] for w in slice_data) / len(slice_data)
            p_norm = min(avg_p / self.price_ceiling, 1.0) * 100
            c_norm = min(avg_c / self.carbon_ceiling, 1.0) * 100
            return {
                "score": p_norm * self.cost_weight + c_norm * self.carbon_weight,
                "avgPrice": avg_p,
                "avgCarbon": avg_c,
                "cost": avg_p * duration_hours,
                "carbonKg": (avg_c * energy_kwh) / 1000,
            }

        # Scan all feasible start times
        best_score = float("inf")
        best_idx = 0
        best_metrics = score_window(baseline_slice)

        max_start_idx = min(
            len(forecast) - windows_needed,
            round(deadline_hours - duration_hours),
        )

        for i in range(max_start_idx + 1):
            slice_data = forecast[i : i + windows_needed]
            if len(slice_data) < windows_needed:
                break
            m = score_window(slice_data)
            if m["score"] < best_score:
                best_score = m["score"]
                best_idx = i
                best_metrics = m

        return {
            "baselineCost": baseline_cost,
            "baselineCarbonKg": baseline_carbon_kg,
            "baselineAvgPrice": baseline_avg_price,
            "baselineAvgCarbon": baseline_avg_carbon,
            "optimizedCost": best_metrics["cost"],
            "optimizedCarbonKg": best_metrics["carbonKg"],
            "optimizedAvgPrice": best_metrics["avgPrice"],
            "optimizedAvgCarbon": best_metrics["avgCarbon"],
            "costSavings": baseline_cost - best_metrics["cost"],
            "carbonSavingsKg": baseline_carbon_kg - best_metrics["carbonKg"],
            "delayHours": best_idx,
            "optimalStartIdx": best_idx,
            "windowsNeeded": windows_needed,
            "energyKwh": energy_kwh,
        }


@pytest.fixture
def parity_forecast():
    """
    Create a forecast suitable for parity testing.

    Matches the structure that would come from MockGrid.getForecast() in the JS.
    """
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    hours = 48
    data = {
        "timestamp": [now + timedelta(hours=i) for i in range(hours)],
        "price": [0.10 + 0.05 * abs((i - 12) % 24) / 12 for i in range(hours)],
        "co2_intensity": [300 + 100 * abs((i - 12) % 24) / 12 for i in range(hours)],
        "renewable_percentage": [50.0] * hours,
        "region": ["US-WEST"] * hours,
        "confidence": [1.0] * hours,
    }
    df = pd.DataFrame(data)
    df = df.set_index("timestamp")
    return df


@pytest.fixture
def parity_forecast_as_list(parity_forecast):
    """Convert pandas forecast to list of dicts (JS format)."""
    return [
        {"price": row["price"], "co2_intensity": row["co2_intensity"]}
        for _, row in parity_forecast.iterrows()
    ]


class TestParityOptimization:
    """Test parity between JS and Python implementations."""

    def test_parity_basic_optimization(self, parity_forecast, parity_forecast_as_list):
        """Test that JS and Python produce identical results on basic workload."""
        # Setup
        duration_hours = 6.0
        power_draw_kw = 120.0
        deadline_hours = 24.0

        # Python implementation
        python_autopilot = Autopilot(
            OptimizationConfig(
                cost_weight=JS_DEFAULT_PRICE_WEIGHT,
                carbon_weight=JS_DEFAULT_CARBON_WEIGHT,
            )
        )
        workload = Workload(
            name="Parity Test",
            duration_hours=duration_hours,
            power_draw_kw=power_draw_kw,
            deadline_hours=deadline_hours,
        )
        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)

        # JavaScript implementation
        js_port = JavaScriptOptimizationPort()
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=duration_hours,
            power_draw_kw=power_draw_kw,
            deadline_hours=deadline_hours,
        )

        # Compare results with epsilon for floating-point tolerance
        assert (
            pytest.approx(python_result.baseline_cost, rel=0.01, abs=0.01)
            == js_result["baselineCost"]
        ), "Baseline cost mismatch"

        assert (
            pytest.approx(python_result.baseline_carbon_kg, rel=0.01, abs=0.01)
            == js_result["baselineCarbonKg"]
        ), "Baseline carbon mismatch"

        assert (
            pytest.approx(python_result.optimized_cost, rel=0.01, abs=0.01)
            == js_result["optimizedCost"]
        ), "Optimized cost mismatch"

        assert (
            pytest.approx(python_result.optimized_carbon_kg, rel=0.01, abs=0.01)
            == js_result["optimizedCarbonKg"]
        ), "Optimized carbon mismatch"

        # Delay should match (in hours) - may need epsilon due to timestamp rounding
        python_delay = (
            python_result.optimal_start - python_result.baseline_start
        ).total_seconds() / 3600
        assert (
            pytest.approx(python_delay, rel=0.1, abs=0.5) == js_result["delayHours"]
        ), f"Delay mismatch: Python={python_delay}h, JS={js_result['delayHours']}h"

    def test_parity_cost_focused(self, parity_forecast, parity_forecast_as_list):
        """Test parity with cost-focused weights (100% cost, 0% carbon)."""
        python_autopilot = Autopilot(OptimizationConfig(cost_weight=1.0, carbon_weight=0.0))
        js_port = JavaScriptOptimizationPort(cost_weight=1.0, carbon_weight=0.0)

        workload = Workload(
            name="Cost Test",
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=20.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=20.0,
        )

        assert (
            pytest.approx(python_result.optimized_cost, rel=0.01, abs=0.01)
            == js_result["optimizedCost"]
        ), "Cost-focused: optimized cost mismatch"

    def test_parity_carbon_focused(self, parity_forecast, parity_forecast_as_list):
        """Test parity with carbon-focused weights (0% cost, 100% carbon)."""
        python_autopilot = Autopilot(OptimizationConfig(cost_weight=0.0, carbon_weight=1.0))
        js_port = JavaScriptOptimizationPort(cost_weight=0.0, carbon_weight=1.0)

        workload = Workload(
            name="Carbon Test",
            duration_hours=3.0,
            power_draw_kw=80.0,
            deadline_hours=18.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=3.0,
            power_draw_kw=80.0,
            deadline_hours=18.0,
        )

        assert (
            pytest.approx(python_result.optimized_carbon_kg, rel=0.01, abs=0.01)
            == js_result["optimizedCarbonKg"]
        ), "Carbon-focused: optimized carbon mismatch"

    def test_parity_short_duration(self, parity_forecast, parity_forecast_as_list):
        """Test parity with very short workload (< 1 hour)."""
        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="Short Task",
            duration_hours=0.5,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=0.5,
            power_draw_kw=50.0,
            deadline_hours=12.0,
        )

        # Short durations may round differently, use larger epsilon
        assert (
            pytest.approx(python_result.optimized_cost, rel=0.05, abs=0.05)
            == js_result["optimizedCost"]
        ), "Short workload cost mismatch"

    def test_parity_long_duration(self, parity_forecast, parity_forecast_as_list):
        """Test parity with long workload (24+ hours)."""
        # Extend forecast for longer workload
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        extended_hours = 96
        extended_data = {
            "timestamp": [now + timedelta(hours=i) for i in range(extended_hours)],
            "price": [0.10 + 0.05 * abs((i - 12) % 24) / 12 for i in range(extended_hours)],
            "co2_intensity": [300 + 100 * abs((i - 12) % 24) / 12 for i in range(extended_hours)],
            "renewable_percentage": [50.0] * extended_hours,
            "region": ["US-WEST"] * extended_hours,
            "confidence": [1.0] * extended_hours,
        }
        extended_df = pd.DataFrame(extended_data).set_index("timestamp")
        extended_list = [
            {"price": row["price"], "co2_intensity": row["co2_intensity"]}
            for _, row in extended_df.iterrows()
        ]

        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="Long Job",
            duration_hours=24.0,
            power_draw_kw=100.0,
            deadline_hours=72.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, extended_df)
        js_result = js_port.optimize_schedule(
            extended_list,
            duration_hours=24.0,
            power_draw_kw=100.0,
            deadline_hours=72.0,
        )

        assert (
            pytest.approx(python_result.optimized_cost, rel=0.02, abs=0.1)
            == js_result["optimizedCost"]
        ), "Long workload cost mismatch"

    def test_parity_no_delay_scenario(self, parity_forecast, parity_forecast_as_list):
        """Test parity when optimal window is immediate start (baseline)."""
        # Create forecast where baseline is already optimal
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        flat_data = {
            "timestamp": [now + timedelta(hours=i) for i in range(48)],
            "price": [0.12] * 48,  # Flat price
            "co2_intensity": [350.0] * 48,  # Flat carbon
            "renewable_percentage": [50.0] * 48,
            "region": ["US-WEST"] * 48,
            "confidence": [1.0] * 48,
        }
        flat_df = pd.DataFrame(flat_data).set_index("timestamp")
        flat_list = [
            {"price": row["price"], "co2_intensity": row["co2_intensity"]}
            for _, row in flat_df.iterrows()
        ]

        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="No Optimization",
            duration_hours=6.0,
            power_draw_kw=100.0,
            deadline_hours=24.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, flat_df)
        js_result = js_port.optimize_schedule(
            flat_list,
            duration_hours=6.0,
            power_draw_kw=100.0,
            deadline_hours=24.0,
        )

        # When no delay, cost savings should be minimal or zero
        assert pytest.approx(python_result.cost_savings, abs=0.01) == js_result["costSavings"]
        assert (
            pytest.approx(python_result.carbon_savings_kg, abs=0.01) == js_result["carbonSavingsKg"]
        )

    def test_parity_different_weight_combinations(self, parity_forecast, parity_forecast_as_list):
        """Test parity with various weight combinations."""
        test_cases = [
            (0.9, 0.1),
            (0.6, 0.4),
            (0.5, 0.5),
            (0.3, 0.7),
        ]

        workload = Workload(
            name="Weight Test",
            duration_hours=5.0,
            power_draw_kw=110.0,
            deadline_hours=22.0,
        )

        for cost_w, carbon_w in test_cases:
            python_autopilot = Autopilot(
                OptimizationConfig(cost_weight=cost_w, carbon_weight=carbon_w)
            )
            js_port = JavaScriptOptimizationPort(cost_weight=cost_w, carbon_weight=carbon_w)

            python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
            js_result = js_port.optimize_schedule(
                parity_forecast_as_list,
                duration_hours=5.0,
                power_draw_kw=110.0,
                deadline_hours=22.0,
            )

            assert (
                pytest.approx(python_result.optimized_cost, rel=0.01, abs=0.01)
                == js_result["optimizedCost"]
            ), f"Weights {cost_w}/{carbon_w}: cost mismatch"

            assert (
                pytest.approx(python_result.optimized_carbon_kg, rel=0.01, abs=0.01)
                == js_result["optimizedCarbonKg"]
            ), f"Weights {cost_w}/{carbon_w}: carbon mismatch"


class TestParityEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_parity_minimal_deadline(self, parity_forecast, parity_forecast_as_list):
        """Test with deadline barely larger than duration."""
        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="Tight Deadline",
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=4.5,
        )

        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=4.5,
        )

        assert (
            pytest.approx(python_result.optimized_cost, rel=0.02, abs=0.02)
            == js_result["optimizedCost"]
        ), "Tight deadline cost mismatch"

    def test_parity_very_high_power(self, parity_forecast, parity_forecast_as_list):
        """Test with very high power draw."""
        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="GPU Intensive",
            duration_hours=8.0,
            power_draw_kw=2000.0,
            deadline_hours=24.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, parity_forecast)
        js_result = js_port.optimize_schedule(
            parity_forecast_as_list,
            duration_hours=8.0,
            power_draw_kw=2000.0,
            deadline_hours=24.0,
        )

        # High power scales carbon calculations, check relative tolerance
        assert (
            pytest.approx(python_result.optimized_carbon_kg, rel=0.01, abs=1.0)
            == js_result["optimizedCarbonKg"]
        ), "High power carbon mismatch"

    def test_parity_low_prices_normalized(self, parity_forecast_as_list):
        """Test with prices well below normalization ceiling."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        cheap_data = {
            "timestamp": [now + timedelta(hours=i) for i in range(48)],
            "price": [0.05] * 48,  # Well below $35 ceiling
            "co2_intensity": [200.0] * 48,
            "renewable_percentage": [50.0] * 48,
            "region": ["US-WEST"] * 48,
            "confidence": [1.0] * 48,
        }
        cheap_df = pd.DataFrame(cheap_data).set_index("timestamp")
        cheap_list = [
            {"price": row["price"], "co2_intensity": row["co2_intensity"]}
            for _, row in cheap_df.iterrows()
        ]

        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="Cheap Test",
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=20.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, cheap_df)
        js_result = js_port.optimize_schedule(
            cheap_list,
            duration_hours=4.0,
            power_draw_kw=100.0,
            deadline_hours=20.0,
        )

        # With very low prices, all windows are normalized to near-zero
        assert python_result.optimized_cost == pytest.approx(js_result["optimizedCost"], rel=0.01)

    def test_parity_high_carbon_normalized(self, parity_forecast_as_list):
        """Test with carbon intensity well above normalization ceiling."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        dirty_data = {
            "timestamp": [now + timedelta(hours=i) for i in range(48)],
            "price": [0.15] * 48,
            "co2_intensity": [1000.0] * 48,  # Well above 600 ceiling
            "renewable_percentage": [50.0] * 48,
            "region": ["US-WEST"] * 48,
            "confidence": [1.0] * 48,
        }
        dirty_df = pd.DataFrame(dirty_data).set_index("timestamp")
        dirty_list = [
            {"price": row["price"], "co2_intensity": row["co2_intensity"]}
            for _, row in dirty_df.iterrows()
        ]

        python_autopilot = Autopilot()
        js_port = JavaScriptOptimizationPort()

        workload = Workload(
            name="High Carbon Test",
            duration_hours=3.0,
            power_draw_kw=90.0,
            deadline_hours=18.0,
        )

        python_result = python_autopilot.optimize_schedule(workload, dirty_df)
        js_result = js_port.optimize_schedule(
            dirty_list,
            duration_hours=3.0,
            power_draw_kw=90.0,
            deadline_hours=18.0,
        )

        # With very high carbon, all windows are normalized to near-100
        assert python_result.optimized_carbon_kg == pytest.approx(
            js_result["optimizedCarbonKg"], rel=0.01
        )
