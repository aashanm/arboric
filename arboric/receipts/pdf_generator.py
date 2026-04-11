"""PDF generation for certified carbon receipts using Playwright + Jinja2.

Renders HTML template to PDF using headless Chromium (Playwright).
Guarantees pixel-perfect output matching the web design.
"""

from datetime import datetime
from pathlib import Path

from arboric.receipts.exceptions import EnterpriseFeatureNotAvailableError, PDFGenerationError
from arboric.receipts.models import CarbonReceipt


def _to_local_time(dt: datetime) -> datetime:
    """Convert UTC datetime to local timezone."""
    from datetime import timezone as tz

    import pandas as pd

    # Handle pandas Timestamp
    if isinstance(dt, pd.Timestamp):
        # Convert to Python datetime, ensuring UTC
        if dt.tz is None:
            dt_py = dt.replace(tzinfo=tz.utc)
        else:
            dt_py = dt.to_pydatetime()
        # Convert to local timezone
        return dt_py.astimezone()

    # Handle Python datetime
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=tz.utc)
    return dt.astimezone()


def _get_template_path() -> Path:
    """Get path to receipt HTML template."""
    return Path(__file__).parent / "receipt_template.html"


def render_receipt_html(receipt: CarbonReceipt) -> str:
    """
    Render receipt data into HTML using Jinja2 template.

    Args:
        receipt: CarbonReceipt with all materialized data

    Returns:
        Rendered HTML string

    Raises:
        EnterpriseFeatureNotAvailableError: if jinja2 is not installed
    """
    try:
        from jinja2 import Template
    except ImportError as e:
        raise EnterpriseFeatureNotAvailableError(
            "jinja2 not found. Install: pip install arboric[enterprise]"
        ) from e

    template_path = _get_template_path()
    template_html = template_path.read_text()
    template = Template(template_html)

    # Calculate derived data for template
    avg_renewable = (
        sum(m.renewable_percentage for m in receipt.hourly_moer) / len(receipt.hourly_moer)
        if receipt.hourly_moer
        else 0.0
    )

    # Color thresholds for MOER cells
    def get_moer_color(renewable_pct: float) -> str:
        if renewable_pct >= 65:
            return "emerald"
        elif renewable_pct >= 45:
            return "amber"
        else:
            return "red"

    moer_entries = [
        {
            "hour": _to_local_time(entry.timestamp).strftime("%H"),
            "co2": entry.co2_intensity,
            "renewable": entry.renewable_percentage,
            "color": get_moer_color(entry.renewable_percentage),
        }
        for entry in receipt.hourly_moer
    ]

    delay_hours = int((receipt.optimal_start - receipt.baseline_start).total_seconds() / 3600)

    # Calculate dynamic bar positions for execution shift visualization
    # Positions are percentages of a 24-hour day (0:00 - 24:00)
    # Extract hours from local timezone for display
    baseline_start_local = _to_local_time(receipt.baseline_start)
    optimal_start_local = _to_local_time(receipt.optimal_start)
    baseline_start_hour = baseline_start_local.hour
    optimal_start_hour = optimal_start_local.hour
    duration_hours = receipt.workload.duration_hours

    baseline_margin_left = (baseline_start_hour / 24.0) * 100
    optimal_margin_left = (optimal_start_hour / 24.0) * 100
    bar_width = (duration_hours / 24.0) * 100

    # Debug: log the bar positions for verification
    import sys

    baseline_local = _to_local_time(receipt.baseline_start)
    optimal_local = _to_local_time(receipt.optimal_start)
    print(
        f"[Receipt PDF] Execution Shift bars: "
        f"baseline_start={baseline_local.strftime('%H:%M')} (hour={baseline_start_hour}), "
        f"optimal_start={optimal_local.strftime('%H:%M')} (hour={optimal_start_hour}), "
        f"duration={duration_hours}h | "
        f"baseline_pos={baseline_margin_left:.1f}%, optimal_pos={optimal_margin_left:.1f}%, width={bar_width:.1f}%",
        file=sys.stderr,
    )

    html = template.render(
        receipt_id_short=str(receipt.receipt_id)[:8].upper(),
        generated_at=_to_local_time(receipt.generated_at).strftime("%Y-%m-%d %H:%M"),
        workload_type=receipt.workload.workload_type.value,
        power_draw_kw=receipt.workload.power_draw_kw,
        region=receipt.hourly_moer[0].region if receipt.hourly_moer else "eastus",
        cost_savings_percent=receipt.cost_savings_percent,
        carbon_savings_percent=receipt.carbon_savings_percent,
        baseline_cost=receipt.baseline_cost,
        optimized_cost=receipt.optimized_cost,
        baseline_avg_carbon=receipt.baseline_avg_carbon,
        optimized_avg_carbon=receipt.optimized_avg_carbon,
        avg_renewable=avg_renewable,
        hourly_moer=moer_entries,
        moer_count=len(receipt.hourly_moer),
        delay_hours=delay_hours,
        baseline_margin_left=baseline_margin_left,
        optimal_margin_left=optimal_margin_left,
        bar_width=bar_width,
        signature_algorithm=receipt.signature.algorithm if receipt.signature else "N/A",
        signature_hash=receipt.signature.data_hash if receipt.signature else "N/A",
        signature_id=f"#{str(receipt.receipt_id)[:8].upper()}" if receipt.signature else "N/A",
    )

    return html


def generate_receipt_pdf(receipt: CarbonReceipt) -> bytes:
    """
    Generate a professional certified carbon receipt PDF using Playwright.

    Renders the receipt HTML template to PDF using headless Chromium.
    Guarantees pixel-perfect output matching the web design.
    Single-page letter-size document.

    Args:
        receipt: CarbonReceipt with signature

    Returns:
        PDF bytes

    Raises:
        EnterpriseFeatureNotAvailableError: if playwright is not installed
        PDFGenerationError: if generation fails
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise EnterpriseFeatureNotAvailableError(
            "playwright not found. Install: pip install arboric[enterprise]"
        ) from e

    try:
        html = render_receipt_html(receipt)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            pdf = page.pdf(
                format="Letter",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            browser.close()
        return pdf
    except EnterpriseFeatureNotAvailableError:
        raise
    except Exception as e:
        raise PDFGenerationError(f"PDF generation failed: {e}") from e
