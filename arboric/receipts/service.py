"""Receipt service: orchestration of receipt generation."""

import pandas as pd

from arboric.core.config import ArboricConfig
from arboric.core.models import ScheduleResult
from arboric.receipts.exceptions import PDFGenerationError
from arboric.receipts.models import CarbonReceipt, HourlyMOEREntry
from arboric.receipts.pdf_generator import generate_receipt_pdf
from arboric.receipts.signing import sign_receipt


def _detect_moer_source(config: ArboricConfig) -> str:
    """Detect whether we're using live external emissions data or mock simulation."""
    if config.live_data.enabled and config.live_data.provider:
        return "live_emissions_provider"
    return "mock_simulation"


def _slice_forecast_to_window(
    forecast_df: pd.DataFrame,
    optimal_start,
    optimal_end,
    power_draw_kw: float,
) -> list[HourlyMOEREntry]:
    """
    Slice forecast DataFrame to the optimal execution window and build HourlyMOEREntry list.

    Args:
        forecast_df: DataFrame with columns: co2_intensity, price, renewable_percentage, region, confidence
        optimal_start: Start datetime of optimal window
        optimal_end: End datetime of optimal window
        power_draw_kw: Workload power draw in kW (for computing carbon/cost per hour)

    Returns:
        List of HourlyMOEREntry objects, one per hour in the window.
    """
    # Slice to the optimal window
    window = forecast_df[(forecast_df.index >= optimal_start) & (forecast_df.index < optimal_end)]

    entries = []
    for timestamp, row in window.iterrows():
        carbon_kg_for_hour = row["co2_intensity"] * power_draw_kw / 1000.0
        cost_for_hour = row["price"] * power_draw_kw / 1000.0

        entry = HourlyMOEREntry(
            timestamp=pd.Timestamp(timestamp).to_pydatetime(),
            co2_intensity=float(row["co2_intensity"]),
            marginal_price=float(row["price"]),
            renewable_percentage=float(row.get("renewable_percentage", 0.0)),
            region=str(row.get("region", "US-WEST")),
            confidence=float(row.get("confidence", 1.0)),
            carbon_kg_for_hour=carbon_kg_for_hour,
            cost_for_hour=cost_for_hour,
        )
        entries.append(entry)

    return entries


def generate_receipt(
    schedule: ScheduleResult,
    forecast_df: pd.DataFrame,
    config: ArboricConfig,
) -> tuple[CarbonReceipt, bytes]:
    """
    Generate a certified carbon receipt (CarbonReceipt + PDF bytes).

    Args:
        schedule: ScheduleResult from optimization
        forecast_df: Forecast DataFrame used during optimization
        config: ArboricConfig

    Returns:
        Tuple of (CarbonReceipt, pdf_bytes)

    Raises:
        PDFGenerationError: If PDF generation fails
    """
    # Detect data source
    moer_source = _detect_moer_source(config)

    # Slice forecast to optimal window
    hourly_moer = _slice_forecast_to_window(
        forecast_df,
        schedule.optimal_start,
        schedule.optimal_end,
        schedule.workload.power_draw_kw,
    )

    # Build receipt with all materialized values
    receipt = CarbonReceipt(
        moer_data_source=moer_source,
        workload=schedule.workload,
        optimal_start=schedule.optimal_start,
        optimal_end=schedule.optimal_end,
        baseline_start=schedule.baseline_start,
        baseline_end=schedule.baseline_end,
        optimized_cost=schedule.optimized_cost,
        baseline_cost=schedule.baseline_cost,
        cost_savings=schedule.baseline_cost - schedule.optimized_cost,
        cost_savings_percent=(
            (schedule.baseline_cost - schedule.optimized_cost) / schedule.baseline_cost * 100
            if schedule.baseline_cost > 0
            else 0.0
        ),
        optimized_carbon_kg=schedule.optimized_carbon_kg,
        baseline_carbon_kg=schedule.baseline_carbon_kg,
        carbon_savings_kg=schedule.baseline_carbon_kg - schedule.optimized_carbon_kg,
        carbon_savings_percent=(
            (schedule.baseline_carbon_kg - schedule.optimized_carbon_kg)
            / schedule.baseline_carbon_kg
            * 100
            if schedule.baseline_carbon_kg > 0
            else 0.0
        ),
        optimized_avg_price=schedule.optimized_avg_price,
        baseline_avg_price=schedule.baseline_avg_price,
        optimized_avg_carbon=schedule.optimized_avg_carbon,
        baseline_avg_carbon=schedule.baseline_avg_carbon,
        cost_weight=config.optimization.cost_weight,
        carbon_weight=config.optimization.carbon_weight,
        hourly_moer=hourly_moer,
    )

    # Sign receipt
    receipt.signature = sign_receipt(receipt)

    # Generate PDF
    try:
        pdf_bytes = generate_receipt_pdf(receipt)
    except Exception as e:
        raise PDFGenerationError(f"Failed to generate PDF: {e}") from e

    return receipt, pdf_bytes
