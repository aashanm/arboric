"""
Arboric CLI

The command-line interface for Arboric - intelligent workload scheduling
for cost and carbon optimization. Built with Typer and Rich.
"""

import time
from datetime import datetime

import typer
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from arboric.core.autopilot import Autopilot, OptimizationConfig
from arboric.core.config import ArboricConfig, get_config
from arboric.core.grid_oracle import MockGrid, get_grid
from arboric.core.history import HistoryStore
from arboric.core.models import FleetOptimizationResult, Workload, WorkloadType

# Initialize Rich console
console = Console()

# Frequency presets and savings calculation
FREQUENCY_PRESETS = {
    "daily": 365,
    "weekdays": 260,  # 5 × 52
    "weekly": 52,
    "monthly": 12,
}

SAVINGS_REALIZATION_RATE = 0.80  # user keeps 80% after performance fee


def parse_frequency(value: str) -> float:
    """Parse frequency string to runs/year.

    Accepts:
    - Named presets: 'daily', 'weekdays', 'weekly', 'monthly'
    - Numeric: runs per week (e.g. '3' = 3 times/week)

    Raises ValueError on invalid input.
    """
    lower = value.strip().lower()
    if lower in FREQUENCY_PRESETS:
        return float(FREQUENCY_PRESETS[lower])
    try:
        runs_per_week = float(lower)  # input unit: runs/week (e.g. --frequency 3 = 3×/wk)
        if runs_per_week <= 0:
            raise ValueError("Frequency must be greater than 0.")
        return runs_per_week * 52
    except ValueError:
        raise ValueError(
            f"Unknown frequency '{value}'. Use: daily, weekdays, weekly, monthly, or a number (runs/week)."
        )


def to_local_time(dt):
    """Convert datetime to local timezone (if needed). Naive timestamps are assumed to already be in local time."""

    import pandas as pd

    # Handle pandas Timestamp
    if isinstance(dt, pd.Timestamp):
        dt_py = dt.to_pydatetime()
        # If naive (from our forecast), it's already in local time - return as-is
        if dt_py.tzinfo is None:
            return dt_py
        # If UTC-aware, convert to local
        if str(dt_py.tzinfo) == "UTC":
            return dt_py.astimezone()
        # If already in a local timezone, return as-is
        return dt_py

    # Handle Python datetime
    if dt.tzinfo is None:
        # Naive timestamps from forecast are already in local time
        return dt
    if str(dt.tzinfo) == "UTC":
        # UTC-aware, convert to local
        return dt.astimezone()
    # Already in some timezone, return as-is
    return dt


def format_local_time(dt, fmt: str = "%H:%M") -> str:
    """Format datetime in local timezone."""
    return to_local_time(dt).strftime(fmt)


# Initialize Typer app
app = typer.Typer(
    name="arboric",
    help="Intelligent autopilot for cloud infrastructure. Harvest optimal energy windows.",
    add_completion=False,
    rich_markup_mode="rich",
)

# Brand colors
ARBORIC_GREEN = "#22c55e"
ARBORIC_BLUE = "#3b82f6"
ARBORIC_AMBER = "#f59e0b"
ARBORIC_RED = "#ef4444"
ARBORIC_PURPLE = "#8b5cf6"


def print_banner():
    """Display the Arboric ASCII banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║     █████╗ ██████╗ ██████╗  ██████╗ ██████╗ ██╗ ██████╗       ║
    ║    ██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██║██╔════╝       ║
    ║    ███████║██████╔╝██████╔╝██║   ██║██████╔╝██║██║            ║
    ║    ██╔══██║██╔══██╗██╔══██╗██║   ██║██╔══██╗██║██║            ║
    ║    ██║  ██║██║  ██║██████╔╝╚██████╔╝██║  ██║██║╚██████╗       ║
    ║    ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝       ║
    ║                                                               ║
    ║           Intelligent Autopilot for Cloud Infrastructure      ║
    ║                  Harvest Optimal Energy Windows               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style=f"bold {ARBORIC_GREEN}")


def create_comparison_table(result) -> Table:
    """Create a visual comparison table for optimization results."""
    table = Table(
        title="",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {ARBORIC_BLUE}",
        border_style=ARBORIC_BLUE,
        padding=(0, 1),
    )

    table.add_column("Metric", style="bold white", width=20)
    table.add_column("Immediate Run", style=f"bold {ARBORIC_RED}", justify="right", width=18)
    table.add_column("Arboric Schedule", style=f"bold {ARBORIC_GREEN}", justify="right", width=18)
    table.add_column("Yield", style=f"bold {ARBORIC_AMBER}", justify="right", width=14)

    # Start time
    if result.delay_hours > 0:
        optimal_col = f"{result.optimal_start_clock} (+{result.delay_hours:.1f}h)"
        yield_col = f"within {result.workload.deadline_hours:.0f}h deadline ✓"
    else:
        optimal_col = result.optimal_start_clock
        yield_col = "Immediate — already optimal"

    table.add_row(
        "Start Time",
        format_local_time(result.baseline_start),
        optimal_col,
        yield_col,
    )

    # Avg Price
    table.add_row(
        "Avg Price",
        f"${result.baseline_avg_price:.2f}/hr",
        f"${result.optimized_avg_price:.2f}/hr",
        f"{((result.baseline_avg_price - result.optimized_avg_price) / result.baseline_avg_price * 100):+.1f}%",
    )

    # Avg Carbon
    table.add_row(
        "Avg Carbon",
        f"{result.baseline_avg_carbon:.0f} gCO2/kWh",
        f"{result.optimized_avg_carbon:.0f} gCO2/kWh",
        f"{((result.baseline_avg_carbon - result.optimized_avg_carbon) / result.baseline_avg_carbon * 100):+.1f}%",
    )

    table.add_section()

    # Total Cost
    table.add_row(
        "Total Cost",
        f"${result.baseline_cost:.2f}",
        f"${result.optimized_cost:.2f}",
        f"-${result.cost_savings:.2f}",
    )

    # Total Carbon
    table.add_row(
        "Total Carbon",
        f"{result.baseline_carbon_kg:.2f} kg",
        f"{result.optimized_carbon_kg:.2f} kg",
        f"-{result.carbon_savings_kg:.2f} kg",
    )

    # On-demand rate (if instance was specified)
    if result.on_demand_rate_per_hr is not None:
        table.add_row(
            "On-demand Rate",
            f"${result.on_demand_rate_per_hr:.2f}/hr",
            f"${result.on_demand_rate_per_hr:.2f}/hr",
            "(reference)",
        )

    return table


def create_forecast_chart(forecast_df, optimal_start, workload_duration) -> str:
    """Create an ASCII visualization of the forecast with scheduled window."""
    hours = min(24, len(forecast_df))

    # Normalize values for display
    prices = forecast_df["price"].head(hours).values
    carbons = forecast_df["co2_intensity"].head(hours).values

    price_min, price_max = prices.min(), prices.max()
    _carbon_min, _carbon_max = carbons.min(), carbons.max()

    def normalize(val, vmin, vmax, height=8):
        if vmax == vmin:
            return height // 2
        return int((val - vmin) / (vmax - vmin) * (height - 1))

    # Build chart
    lines = []
    height = 8

    # Price chart
    lines.append(f"  {'Price ($/hr)':<20} │ ${price_max:.2f}")
    for row in range(height - 1, -1, -1):
        line = "  " + " " * 20 + " │ "
        for i, price in enumerate(prices):
            h = normalize(price, price_min, price_max, height)
            if h >= row:
                # Check if this hour is in the optimal window
                hour_ts = forecast_df.index[i]
                if (
                    hour_ts >= optimal_start
                    and (hour_ts - optimal_start).total_seconds() / 3600 < workload_duration
                ):
                    line += "█"  # Scheduled window
                else:
                    line += "▒"
            else:
                line += " "
        lines.append(line)
    lines.append(f"  {'':20} │ ${price_min:.2f}")
    lines.append(f"  {'':20} └{'─' * hours}")

    # Hour labels
    hour_labels = "  " + " " * 21
    for i in range(0, hours, 4):
        ts = forecast_df.index[i]
        local_hour = to_local_time(ts).hour
        hour_labels += f"{local_hour:02d}  "
    lines.append(hour_labels + " (hour)")

    return "\n".join(lines)


def simulate_optimization_animation(workload_name: str, duration: float = 1.5):
    """Display animated optimization process."""
    steps = [
        ("Connecting to Grid Oracle...", 0.2),
        ("Fetching 24h forecast data...", 0.3),
        ("Analyzing carbon intensity patterns...", 0.2),
        ("Scanning for price anomalies...", 0.2),
        ("Detecting spot price contention patterns...", 0.15),
        ("Evaluating feasible windows...", 0.2),
        ("Computing optimal trajectory...", 0.25),
    ]

    with Progress(
        SpinnerColumn(spinner_name="dots", style=ARBORIC_GREEN),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=30, complete_style=ARBORIC_GREEN),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[{ARBORIC_BLUE}]Optimizing {workload_name}...", total=len(steps))

        for step_text, step_time in steps:
            progress.update(task, description=f"[white]{step_text}")
            time.sleep(step_time * (duration / 1.5))
            progress.advance(task)


def _display_region_comparison(comparison, frequency: str | None = None, quiet: bool = False):
    """Display cross-region temporal comparison results."""
    if quiet:
        return

    # Create comparison table
    table = Table(
        title="",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {ARBORIC_BLUE}",
        border_style=ARBORIC_BLUE,
        padding=(0, 1),
    )

    table.add_column("Region", style="bold white", width=15)
    table.add_column("Best Window", style="white", width=12)
    table.add_column("Spot Rate", style="white", justify="right", width=12)
    table.add_column("Carbon", style="white", justify="right", width=14)
    table.add_column("Cost", style="white", justify="right", width=10)
    table.add_column("You Save", style=f"bold {ARBORIC_GREEN}", justify="right", width=12)

    # Add entries (already sorted cheapest-first)
    for entry in comparison.entries:
        region_label = entry.region
        # Mark cheapest with ⚡ and cleanest with 🌱
        if entry.region == comparison.cheapest_region:
            region_label = f"⚡ {region_label}"
        if entry.region == comparison.cleanest_region:
            region_label = f"🌱 {region_label}"

        table.add_row(
            region_label,
            entry.optimal_start_clock,
            f"${entry.avg_spot_price:.2f}/hr",
            f"{entry.avg_carbon:.0f} gCO2/kWh",
            f"${entry.optimized_cost:.2f}",
            f"-${entry.cost_savings:.2f}",
        )

    console.print(Panel(table, title="[bold]Cross-Region Comparison", border_style=ARBORIC_BLUE))
    console.print()

    # Show comparison summary
    cheapest_entry = comparison.entries[0]  # Already sorted
    cleanest_entry = min(comparison.entries, key=lambda e: e.avg_carbon)

    summary_text = (
        f"[bold {ARBORIC_GREEN}]⚡ Cheapest:[/bold {ARBORIC_GREEN}] {comparison.cheapest_region} "
        f"at {cheapest_entry.optimal_start_clock}  "
        f"[bold {ARBORIC_GREEN}]🌱 Cleanest:[/bold {ARBORIC_GREEN}] {comparison.cleanest_region} "
        f"({cleanest_entry.avg_carbon:.0f} gCO2/kWh)"
    )

    # Add annual projection if frequency provided
    if frequency is not None:
        try:
            runs_per_year = parse_frequency(frequency)
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="'--frequency'")
        annual_savings = cheapest_entry.cost_savings * runs_per_year * SAVINGS_REALIZATION_RATE
        summary_text += f"\n\n[dim]At {frequency} ({runs_per_year:.0f} runs/year) in {comparison.cheapest_region}, that's ${annual_savings:,.2f}/year[/dim]"

    summary_text += (
        "\n\n[dim]Cross-region temporal comparison · data egress costs not included[/dim]"
    )

    summary_panel = Panel(
        summary_text,
        border_style=ARBORIC_GREEN,
        padding=(1, 2),
    )
    console.print(summary_panel)


@app.command()
def optimize(
    workload_name: str = typer.Argument(..., help="Name of the workload to optimize"),
    duration: float | None = typer.Option(
        None, "--duration", "-d", help="Workload duration in hours"
    ),
    deadline: float | None = typer.Option(
        None, "--deadline", "-D", help="Must complete within hours"
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Grid region"),
    instance_type: str | None = typer.Option(
        None,
        "--instance-type",
        "-i",
        help="Cloud instance type (e.g., p3.8xlarge). Use with --provider.",
    ),
    cloud_provider: str | None = typer.Option(
        None, "--provider", help="Cloud provider: aws, gcp, or azure. Use with --instance-type."
    ),
    frequency: str | None = typer.Option(
        None,
        "--frequency",
        "-f",
        help="Job frequency for annual projection: daily, weekdays, weekly, monthly, or runs/week (e.g. 3).",
    ),
    runs_per_week_deprecated: float | None = typer.Option(
        None,
        "--runs-per-week",
        help="[Deprecated] Use --frequency instead.",
        hidden=True,
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (or '-' for stdout)"
    ),
    format: str | None = typer.Option(None, "--format", help="Export format: json, csv"),
    receipt: str | None = typer.Option(
        None, "--receipt", help="Generate certified receipt PDF at path"
    ),
):
    """
    Optimize a single workload for cost and carbon efficiency.

    Example: arboric optimize "LLM Training" --duration 6 --deadline 24 --instance p3.8xlarge --provider aws

    Export results: arboric optimize "Job" --output results.json

    Power draw is auto-derived from the instance type if provided, or defaults to 100 kW.
    If options are not specified, values from ~/.arboric/config.yaml will be used.
    """
    # Load configuration for defaults
    cfg = get_config()

    # Handle deprecated --runs-per-week flag
    if runs_per_week_deprecated is not None:
        console.print("[yellow]⚠  --runs-per-week is deprecated, use --frequency instead.[/yellow]")
        if frequency is None:
            frequency = str(runs_per_week_deprecated)  # treat as numeric runs/week

    # Use config defaults if not specified
    duration = duration if duration is not None else cfg.defaults.duration_hours
    deadline = deadline if deadline is not None else cfg.defaults.deadline_hours
    region = region if region is not None else cfg.defaults.region
    instance_type = instance_type if instance_type is not None else cfg.defaults.instance_type
    cloud_provider = cloud_provider if cloud_provider is not None else cfg.defaults.cloud_provider
    quiet = quiet or cfg.cli.quiet_mode

    # Normalize legacy region aliases to Azure ARM IDs
    _region_aliases = {
        "us-west": "westus2",
        "us-east": "eastus",
        "eu-west": "uksouth",
        "nordic": "northeurope",
    }
    if region and region.lower() in _region_aliases:
        region = _region_aliases[region.lower()]

    if not quiet and cfg.cli.show_banner:
        print_banner()
        console.print()

    # Handle cross-region optimization (--region all → find best across all regions)
    if region and region.lower() == "all":
        workload = Workload(
            name=workload_name,
            duration_hours=duration,
            deadline_hours=deadline,
            workload_type=WorkloadType.ML_TRAINING,
            instance_type=instance_type,
            cloud_provider=cloud_provider,
        )
        opt_config = OptimizationConfig(
            cost_weight=cfg.optimization.cost_weight,
            carbon_weight=cfg.optimization.carbon_weight,
            min_delay_hours=cfg.optimization.min_delay_hours,
            prefer_continuous=cfg.optimization.prefer_continuous,
        )
        autopilot = Autopilot(config=opt_config)
        comparison = autopilot.compare_regions(workload)

        # Get the best (cheapest) region
        best_region = comparison.cheapest_region
        region = best_region  # Set region for normal flow

        # Display which region was chosen
        console.print(
            f"[bold {ARBORIC_GREEN}]✓ Optimal region across all: {best_region}[/bold {ARBORIC_GREEN}]"
        )
        console.print()

    # Create workload
    workload = Workload(
        name=workload_name,
        duration_hours=duration,
        deadline_hours=deadline,
        workload_type=WorkloadType.ML_TRAINING,
        instance_type=instance_type,
        cloud_provider=cloud_provider,
    )

    # Display workload info
    instance_info = ""
    power_note = ""
    if workload.instance_type:
        from arboric.core.grid_oracle import INSTANCE_PROFILES

        provider_profiles = INSTANCE_PROFILES.get(workload.cloud_provider, {})
        instance_profile = provider_profiles.get(workload.instance_type)
        if instance_profile:
            instance_info = f"""[bold]Instance:[/bold] {workload.instance_type} ({workload.cloud_provider.upper()}) · {instance_profile["gpu"]} · {instance_profile["use_case"]}
[bold]On-demand:[/bold] ${instance_profile["on_demand"]:.2f}/hr
"""
            # Power is auto-derived from instance profile
            power_note = f"[dim](auto-estimated from {workload.instance_type}: {workload.power_draw_kw} kW)[/dim]"
        else:
            instance_info = f"[bold]Instance:[/bold] {workload.instance_type} ({workload.cloud_provider.upper()})\n"
    else:
        instance_info = "[bold]Instance:[/bold] Not specified (using default GPU profile)\n"

    workload_panel = Panel(
        f"""[bold]Workload:[/bold] {workload.name}
[bold]Duration:[/bold] {workload.duration_hours}h
[bold]Power Draw:[/bold] {workload.power_draw_kw} kW {power_note}
[bold]Energy:[/bold] {workload.energy_kwh} kWh
[bold]Deadline:[/bold] {workload.deadline_hours}h from now
[bold]Region:[/bold] {region}
{instance_info}""",
        title="[bold white]Payload Configuration",
        border_style=ARBORIC_PURPLE,
        padding=(1, 2),
    )
    console.print(workload_panel)
    console.print()

    # Simulate optimization
    if not quiet:
        simulate_optimization_animation(workload_name)
        console.print()

    # Get forecast and optimize
    grid = get_grid(
        region=region,
        config=cfg,
        instance_type=instance_type,
        cloud_provider=cloud_provider,
    )
    # Pass appropriate time based on grid type:
    # - MockGrid expects naive local time for correct hour_of_day calculations
    # - LiveGrid expects UTC time (interprets naive datetime as UTC)
    from datetime import timezone as tz

    now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
    if getattr(grid, "is_live", False):
        # Live grid interprets naive datetime as UTC
        now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
    else:
        # MockGrid expects naive local time
        now_for_forecast = now_local
    forecast = grid.get_forecast(
        hours=int(deadline) + int(duration) + 2, start_time=now_for_forecast
    )

    # Create autopilot with config-based optimization settings
    opt_config = OptimizationConfig(
        cost_weight=cfg.optimization.cost_weight,
        carbon_weight=cfg.optimization.carbon_weight,
        min_delay_hours=cfg.optimization.min_delay_hours,
        prefer_continuous=cfg.optimization.prefer_continuous,
    )
    autopilot = Autopilot(config=opt_config)
    result = autopilot.optimize_schedule(workload, forecast)

    # DEBUG: Print autopilot logs
    if not quiet:
        for log_entry in autopilot.get_log():
            console.print(f"[dim]{log_entry}[/dim]")

    # Auto-record to history database
    if cfg.history.enabled:
        from pathlib import Path

        try:
            store = HistoryStore(Path(cfg.history.db_path).expanduser())
            data_source = "live" if getattr(grid, "is_live", False) else "mockgrid"
            store.record(result, region=region, data_source=data_source)
        except Exception as e:
            # Gracefully handle history db failures (e.g., in CI/GitHub Actions)
            if not quiet:
                console.print(f"[dim]Note: Could not record to history database: {e}[/dim]")

    # Handle export if requested
    if output:
        from arboric.cli.export import (
            ExportError,
            ExportFormat,
            detect_format,
            export_schedule_result,
        )

        # Determine format
        if format:
            try:
                export_format = ExportFormat(format.lower())
            except ValueError:
                console.print(
                    f"[{ARBORIC_RED}]Invalid format '{format}'. Use 'json' or 'csv'.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)
        else:
            export_format = detect_format(output)
            if not export_format:
                console.print(
                    f"[{ARBORIC_RED}]Cannot detect format from '{output}'. Use --format flag.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)

        # Export
        try:
            export_schedule_result(result, output, export_format, command="optimize")
            if output != "-":
                console.print(f"[{ARBORIC_GREEN}]✓ Exported to {output}[/{ARBORIC_GREEN}]")
                console.print()
        except ExportError as e:
            console.print(f"[{ARBORIC_RED}]Export failed: {e}[/{ARBORIC_RED}]")
            raise typer.Exit(1)

    # Handle receipt generation if requested
    if receipt:
        try:
            from pathlib import Path

            from arboric.receipts import generate_receipt

            carbon_receipt, pdf_bytes = generate_receipt(result, forecast, cfg)
            Path(receipt).write_bytes(pdf_bytes)
            console.print(
                f"[{ARBORIC_GREEN}]✓ Receipt saved:[/] {receipt}  (ID: {carbon_receipt.receipt_id})"
            )
            console.print()
        except ImportError:
            console.print(
                f"[{ARBORIC_RED}]⚠ Enterprise deps not installed. Run: pip install arboric[enterprise][/{ARBORIC_RED}]"
            )
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[{ARBORIC_RED}]Receipt generation failed: {e}[/{ARBORIC_RED}]")
            raise typer.Exit(1)

    # Display events
    events = grid.detect_events(forecast)
    if events and not quiet:
        console.print(f"[bold {ARBORIC_AMBER}]Grid Events Detected:[/bold {ARBORIC_AMBER}]")
        for event in events:
            icon = "⚠️ " if event["severity"] == "warning" else "✨ "
            color = ARBORIC_AMBER if event["severity"] == "warning" else ARBORIC_GREEN
            console.print(f"  {icon}[{color}]{event['description']}[/{color}]")
        console.print()

    # Show optimization decision
    if result.delay_hours > 0:
        console.print(
            f"[bold {ARBORIC_GREEN}]Rerouting payload to "
            f"{format_local_time(result.optimal_start)} "
            f"({result.delay_hours:.1f}h delay)[/bold {ARBORIC_GREEN}]"
        )
    else:
        console.print(
            f"[bold {ARBORIC_GREEN}]Optimal window is NOW - executing immediately[/bold {ARBORIC_GREEN}]"
        )
    console.print()

    # Show comparison table
    table = create_comparison_table(result)
    console.print(Panel(table, title="[bold]Optimization Analysis", border_style=ARBORIC_BLUE))
    console.print()

    # Show yield summary
    # Build schedule confirmation line
    if result.delay_hours > 0:
        schedule_line = f"⏰ Scheduled for {result.optimal_start_clock} · within your {result.workload.deadline_hours:.0f}h deadline ✓  ({result.deadline_slack_hours:.1f}h slack)"
    else:
        schedule_line = "⏰ Starting immediately — already optimal"

    # Build annual savings line if frequency provided
    annual_line = ""
    if frequency is not None:
        try:
            runs_per_year = parse_frequency(frequency)
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="'--frequency'")
        annual_savings = result.cost_savings * runs_per_year * SAVINGS_REALIZATION_RATE
        annual_line = f"\n[dim]Annual savings estimate: ${annual_savings:,.2f}/year  ({frequency} · {runs_per_year:.0f} runs/year)[/dim]"

    yield_panel = Panel(
        Align.center(
            Text.from_markup(
                f"[bold {ARBORIC_GREEN}]TOTAL YIELD[/bold {ARBORIC_GREEN}]  ·  Region: {region}\n\n"
                f"[bold white]💰 ${result.cost_savings:.2f} saved[/bold white]  ·  "
                f"[bold white]🌱 {result.carbon_savings_kg:.2f} kg CO₂ avoided[/bold white]\n\n"
                f"[dim]Cost reduction: {result.cost_savings_percent:.1f}% | "
                f"Carbon reduction: {result.carbon_savings_percent:.1f}%[/dim]\n\n"
                f"{schedule_line}{annual_line}"
            )
        ),
        border_style=ARBORIC_GREEN,
        padding=(1, 2),
    )
    console.print(yield_panel)


@app.command()
def tradeoff(
    workload_name: str = typer.Argument(..., help="Name of the workload to analyze"),
    duration: float | None = typer.Option(
        None, "--duration", "-d", help="Workload duration in hours"
    ),
    deadline: float | None = typer.Option(
        None, "--deadline", "-D", help="Must complete within hours"
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Grid region"),
    instance_type: str | None = typer.Option(
        None,
        "--instance-type",
        "-i",
        help="Cloud instance type (e.g., p3.8xlarge). Use with --provider.",
    ),
    cloud_provider: str | None = typer.Option(
        None, "--provider", help="Cloud provider: aws, gcp, or azure. Use with --instance-type."
    ),
    points: int = typer.Option(10, "--points", "-n", help="Number of tradeoff points to show"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
):
    """
    Analyze cost/carbon tradeoff frontier for a workload.

    Shows multiple equally-feasible schedules with different cost/carbon tradeoffs,
    helping you understand the Pareto frontier of scheduling options.

    Example: arboric tradeoff "LLM Training" --duration 6 --deadline 24 --points 10

    If options are not specified, values from ~/.arboric/config.yaml will be used.
    """
    cfg = get_config()

    duration = duration if duration is not None else cfg.defaults.duration_hours
    deadline = deadline if deadline is not None else cfg.defaults.deadline_hours
    region = region if region is not None else cfg.defaults.region
    instance_type = instance_type if instance_type is not None else cfg.defaults.instance_type
    cloud_provider = cloud_provider if cloud_provider is not None else cfg.defaults.cloud_provider
    quiet = quiet or cfg.cli.quiet_mode

    # Normalize legacy region aliases to Azure ARM IDs
    _region_aliases = {
        "us-west": "westus2",
        "us-east": "eastus",
        "eu-west": "uksouth",
        "nordic": "northeurope",
    }
    if region and region.lower() in _region_aliases:
        region = _region_aliases[region.lower()]

    if not quiet and cfg.cli.show_banner:
        print_banner()
        console.print()

    workload = Workload(
        name=workload_name,
        duration_hours=duration,
        deadline_hours=deadline,
        workload_type=WorkloadType.ML_TRAINING,
        instance_type=instance_type,
        cloud_provider=cloud_provider,
    )

    workload_panel = Panel(
        f"""[bold]Workload:[/bold] {workload.name}
[bold]Duration:[/bold] {workload.duration_hours}h
[bold]Power Draw:[/bold] {workload.power_draw_kw} kW
[bold]Energy:[/bold] {workload.energy_kwh} kWh
[bold]Deadline:[/bold] {workload.deadline_hours}h from now
[bold]Region:[/bold] {region}""",
        title="[bold white]Workload Configuration",
        border_style=ARBORIC_PURPLE,
        padding=(1, 2),
    )
    console.print(workload_panel)
    console.print()

    if not quiet:
        simulate_optimization_animation(workload_name, duration=1.0)
        console.print()

    grid = get_grid(
        region=region,
        config=cfg,
        instance_type=instance_type,
        cloud_provider=cloud_provider,
    )
    # Pass appropriate time based on grid type:
    # - MockGrid expects naive local time for correct hour_of_day calculations
    # - LiveGrid expects UTC time (interprets naive datetime as UTC)
    from datetime import timezone as tz

    now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
    if getattr(grid, "is_live", False):
        now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
    else:
        now_for_forecast = now_local
    forecast = grid.get_forecast(
        hours=int(deadline) + int(duration) + 2, start_time=now_for_forecast
    )

    opt_config = OptimizationConfig(
        cost_weight=cfg.optimization.cost_weight,
        carbon_weight=cfg.optimization.carbon_weight,
        min_delay_hours=cfg.optimization.min_delay_hours,
        prefer_continuous=cfg.optimization.prefer_continuous,
    )
    autopilot = Autopilot(config=opt_config)

    console.print(f"[bold {ARBORIC_GREEN}]Analyzing tradeoff frontier...")
    console.print()

    tradeoff_points = autopilot.generate_tradeoff_frontier(workload, forecast, num_points=points)

    tradeoff_table = Table(
        title="[bold]Cost/Carbon Tradeoff Frontier",
        box=box.ROUNDED,
        border_style=ARBORIC_BLUE,
        header_style=f"bold {ARBORIC_BLUE}",
    )
    tradeoff_table.add_column("#", style="dim", width=3)
    tradeoff_table.add_column("Schedule Time", justify="center", width=16)
    tradeoff_table.add_column("Cost", justify="right", width=12, style=ARBORIC_AMBER)
    tradeoff_table.add_column("Carbon (kg)", justify="right", width=14, style=ARBORIC_GREEN)
    tradeoff_table.add_column("Cost Saved", justify="right", width=12)
    tradeoff_table.add_column("Carbon Saved", justify="right", width=14)

    for i, point in enumerate(tradeoff_points, 1):
        cost_color = ARBORIC_GREEN if point["cost_savings"] >= 0 else ARBORIC_AMBER
        cost_display = f"[{cost_color}]${point['cost']:.2f}[/{cost_color}]"
        savings_display = (
            f"[{ARBORIC_GREEN}]${point['cost_savings']:.2f}[/{ARBORIC_GREEN}]"
            if point["cost_savings"] >= 0
            else f"[{ARBORIC_AMBER}]-${abs(point['cost_savings']):.2f}[/{ARBORIC_AMBER}]"
        )

        tradeoff_table.add_row(
            str(i),
            format_local_time(point["start_time"]),
            cost_display,
            f"{point['carbon']:.2f}",
            savings_display,
            f"{point['carbon_savings']:.2f}",
        )

    console.print(tradeoff_table)
    console.print()

    explanation = Panel(
        "[bold white]Understanding the Tradeoff Frontier[/bold white]\n\n"
        "[dim]Each row shows a feasible schedule option. Moving down the list:\n"
        "• Left side: Lower cost options (less delay)\n"
        "• Right side: Lower carbon options (more delay possible)\n"
        "• No option dominates another - they're all Pareto-optimal\n"
        "• Choose based on your priorities (cost vs. sustainability)[/dim]",
        border_style=ARBORIC_PURPLE,
        padding=(1, 2),
    )
    console.print(explanation)


@app.command()
def demo(
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (or '-' for stdout)"
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Export format: json, csv"),
):
    """
    Run the Arboric Autopilot demo with multiple AI workloads.

    Simulates scheduling 5 heavy AI training jobs and shows
    the aggregated impact of intelligent scheduling.

    Export results: arboric demo --output fleet.json
    """
    print_banner()
    console.print()

    # Demo workloads (realistic AI/data pipeline jobs)
    demo_workloads = [
        Workload(
            name="LLM Fine-tuning (GPT-4 class)",
            duration_hours=8,
            power_draw_kw=120,
            deadline_hours=24,
            workload_type=WorkloadType.ML_TRAINING,
        ),
        Workload(
            name="Daily ETL Pipeline",
            duration_hours=2,
            power_draw_kw=40,
            deadline_hours=12,
            workload_type=WorkloadType.ETL_PIPELINE,
        ),
        Workload(
            name="Vision Model Training",
            duration_hours=6,
            power_draw_kw=80,
            deadline_hours=18,
            workload_type=WorkloadType.ML_TRAINING,
        ),
        Workload(
            name="Embedding Generation",
            duration_hours=4,
            power_draw_kw=60,
            deadline_hours=16,
            workload_type=WorkloadType.BATCH_PROCESSING,
        ),
        Workload(
            name="Data Warehouse Sync",
            duration_hours=3,
            power_draw_kw=35,
            deadline_hours=8,
            workload_type=WorkloadType.DATA_ANALYTICS,
        ),
    ]

    # Display intro
    intro_panel = Panel(
        f"""[bold]Arboric Autopilot Demo[/bold]

Simulating intelligent scheduling for [bold]{len(demo_workloads)}[/bold] heavy compute workloads.
The autopilot will analyze grid conditions and optimize each job for
minimum cost and carbon emissions.

[dim]Region: eastus  |  Forecast Horizon: 24h  |  Optimization: 70% cost / 30% carbon[/dim]""",
        border_style=ARBORIC_PURPLE,
        padding=(1, 2),
    )
    console.print(intro_panel)
    console.print()

    # Show workload queue
    queue_table = Table(
        title="[bold]Workload Queue",
        box=box.ROUNDED,
        border_style=ARBORIC_BLUE,
        header_style=f"bold {ARBORIC_BLUE}",
    )
    queue_table.add_column("#", style="dim", width=3)
    queue_table.add_column("Workload", style="white", width=30)
    queue_table.add_column("Duration", justify="right", width=10)
    queue_table.add_column("Power", justify="right", width=10)
    queue_table.add_column("Energy", justify="right", width=12)
    queue_table.add_column("Deadline", justify="right", width=10)

    for i, w in enumerate(demo_workloads, 1):
        queue_table.add_row(
            str(i),
            w.name,
            f"{w.duration_hours}h",
            f"{w.power_draw_kw} kW",
            f"{w.energy_kwh} kWh",
            f"{w.deadline_hours}h",
        )

    console.print(queue_table)
    console.print()

    # Initialize grid and autopilot
    # Start forecast at evening peak (18:00) to show optimizer finding cheaper morning windows

    demo_start = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)

    grid = MockGrid(region="eastus", seed=42)  # Fixed seed for consistent demo results
    forecast = grid.get_forecast(hours=48, start_time=demo_start)  # Extended forecast
    autopilot = Autopilot()

    # Process each workload with live updates
    results = []

    console.print(f"[bold {ARBORIC_GREEN}]Engaging Autopilot...[/bold {ARBORIC_GREEN}]")
    console.print()

    with Progress(
        SpinnerColumn(spinner_name="dots", style=ARBORIC_GREEN),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, complete_style=ARBORIC_GREEN, finished_style=ARBORIC_GREEN),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        main_task = progress.add_task(
            "[white]Processing workload queue...",
            total=len(demo_workloads),
        )

        for workload in demo_workloads:
            progress.update(main_task, description=f"[white]Optimizing: {workload.name}")

            # Simulate processing time
            time.sleep(0.8)

            # Get optimization result
            result = autopilot.optimize_schedule(workload, forecast)
            results.append(result)

            progress.advance(main_task)

    console.print()

    # Calculate totals for fleet result
    total_cost_saved_calc = sum(r.cost_savings for r in results)
    total_carbon_saved_calc = sum(r.carbon_savings_kg for r in results)

    # Create FleetOptimizationResult for export
    fleet_result = FleetOptimizationResult(
        schedules=results,
        total_cost_savings=total_cost_saved_calc,
        total_carbon_savings_kg=total_carbon_saved_calc,
        total_workloads=len(results),
    )

    # Handle export if requested
    if output:
        from arboric.cli.export import ExportError, ExportFormat, detect_format, export_fleet_result

        # Determine format
        if format:
            try:
                export_format = ExportFormat(format.lower())
            except ValueError:
                console.print(
                    f"[{ARBORIC_RED}]Invalid format '{format}'. Use 'json' or 'csv'.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)
        else:
            export_format = detect_format(output)
            if not export_format:
                console.print(
                    f"[{ARBORIC_RED}]Cannot detect format from '{output}'. Use --format flag.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)

        # Export
        try:
            export_fleet_result(fleet_result, output, export_format, command="demo")
            if output != "-":
                console.print(f"[{ARBORIC_GREEN}]✓ Exported to {output}[/{ARBORIC_GREEN}]")
                console.print()
        except ExportError as e:
            console.print(f"[{ARBORIC_RED}]Export failed: {e}[/{ARBORIC_RED}]")
            raise typer.Exit(1)

    # Show results table
    results_table = Table(
        title="[bold]Optimization Results",
        box=box.ROUNDED,
        border_style=ARBORIC_GREEN,
        header_style=f"bold {ARBORIC_GREEN}",
    )
    results_table.add_column("Workload", style="white", width=36, no_wrap=True)
    results_table.add_column("Scheduled", justify="center", width=10)
    results_table.add_column("Delay", justify="right", width=10)
    results_table.add_column("Cost Saved", justify="right", width=12)
    results_table.add_column("CO₂ Saved", justify="right", width=12, style=ARBORIC_GREEN)

    total_cost_saved = 0
    total_carbon_saved = 0

    for r in results:
        delay_str = f"+{r.delay_hours:.1f}h" if r.delay_hours > 0 else "Now"
        # Conditional coloring: green if positive savings, amber/yellow if negative
        cost_color = ARBORIC_GREEN if r.cost_savings >= 0 else ARBORIC_AMBER
        cost_display = f"[{cost_color}]${r.cost_savings:.2f}[/{cost_color}]"

        results_table.add_row(
            r.workload.name[:35],
            format_local_time(r.optimal_start),
            delay_str,
            cost_display,
            f"{r.carbon_savings_kg:.2f} kg",
        )
        total_cost_saved += r.cost_savings
        total_carbon_saved += r.carbon_savings_kg

    # Add totals row with conditional coloring
    total_cost_color = ARBORIC_GREEN if total_cost_saved >= 0 else ARBORIC_AMBER
    results_table.add_section()
    results_table.add_row(
        "[bold]TOTAL",
        "",
        "",
        f"[bold {total_cost_color}]${total_cost_saved:.2f}[/bold {total_cost_color}]",
        f"[bold]{total_carbon_saved:.2f} kg",
    )

    console.print(results_table)
    console.print()

    # Calculate fleet statistics
    total_baseline_cost = sum(r.baseline_cost for r in results)
    total_optimized_cost = sum(r.optimized_cost for r in results)
    total_baseline_carbon = sum(r.baseline_carbon_kg for r in results)
    total_optimized_carbon = sum(r.optimized_carbon_kg for r in results)

    cost_reduction_pct = (
        (total_cost_saved / total_baseline_cost * 100) if total_baseline_cost > 0 else 0
    )
    carbon_reduction_pct = (
        (total_carbon_saved / total_baseline_carbon * 100) if total_baseline_carbon > 0 else 0
    )

    # Annualized projections (assuming daily runs)
    annual_cost_savings = total_cost_saved * 365
    annual_carbon_savings = total_carbon_saved * 365

    # Conditional coloring for cost savings
    cost_savings_color = ARBORIC_GREEN if total_cost_saved >= 0 else ARBORIC_AMBER
    cost_savings_label = "SAVINGS" if total_cost_saved >= 0 else "COST"

    # Final impact panel with clean formatting
    saved_label = "saved" if total_cost_saved >= 0 else "increase"
    impact_lines = [
        f"[bold {ARBORIC_GREEN}]ARBORIC IMPACT REPORT[/bold {ARBORIC_GREEN}]",
        "",
        "[bold]Fleet Optimization Summary[/bold]",
        f"Workloads Processed:  [bold]{len(demo_workloads)}[/bold]",
        f"Total Energy:         [bold]{sum(w.energy_kwh for w in demo_workloads):,.0f} kWh[/bold]",
        "",
        f"[bold {ARBORIC_RED}]Without Arboric[/bold {ARBORIC_RED}]        [bold {ARBORIC_GREEN}]With Arboric[/bold {ARBORIC_GREEN}]",
        f"Cost:    ${total_baseline_cost:>8,.2f}         Cost:    ${total_optimized_cost:>8,.2f}",
        f"Carbon:  {total_baseline_carbon:>8,.2f} kg       Carbon:  {total_optimized_carbon:>8,.2f} kg",
        "",
        f"[bold {cost_savings_color}]💰 COST {cost_savings_label}:  ${abs(total_cost_saved):>8,.2f}  ({abs(cost_reduction_pct):.1f}% {saved_label})[/bold {cost_savings_color}]",
        f"[bold {ARBORIC_GREEN}]🌱 CARBON AVOIDED:  {total_carbon_saved:>8,.2f} kg ({carbon_reduction_pct:.1f}% reduction)[/bold {ARBORIC_GREEN}]",
        "",
        f"[bold {cost_savings_color}]💵 ANNUALIZED SAVINGS: ${abs(annual_cost_savings):>,.0f}/year[/bold {cost_savings_color}]",
        f"[dim]🌲 {annual_carbon_savings / 1000:,.1f} metric tons CO₂ avoided per year[/dim]",
    ]
    impact_text = "\n".join(impact_lines)

    console.print(
        Panel(
            impact_text,
            border_style=ARBORIC_GREEN,
            padding=(1, 2),
        )
    )

    # Closing message
    console.print()
    console.print(
        "[dim]Arboric: Where algorithms meet sustainability.[/dim]",
        justify="center",
    )


@app.command()
def forecast(
    region: str = typer.Option("eastus", "--region", "-r", help="Grid region"),
    hours: int = typer.Option(24, "--hours", "-h", help="Forecast hours"),
    instance_type: str | None = typer.Option(
        None, "--instance-type", help="Cloud instance type (optional, affects spot pricing)"
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Cloud provider: aws, gcp, azure (optional)"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (or '-' for stdout)"
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Export format: json, csv"),
):
    """
    Display the current grid forecast for a region.

    Shows carbon intensity and pricing over the forecast horizon.

    Export forecast: arboric forecast --output forecast.csv --region eastus --hours 24
    """
    print_banner()
    console.print()

    console.print(f"[bold]Fetching {hours}h forecast for {region}...[/bold]")
    console.print()

    cfg = get_config()
    grid = get_grid(region=region, config=cfg, instance_type=instance_type, cloud_provider=provider)
    # Pass appropriate time based on grid type:
    # - MockGrid expects naive local time for correct hour_of_day calculations
    # - LiveGrid expects UTC time (interprets naive datetime as UTC)
    from datetime import timezone as tz

    now_local = datetime.now().replace(minute=0, second=0, microsecond=0)
    if getattr(grid, "is_live", False):
        now_for_forecast = now_local.astimezone(tz.utc).replace(tzinfo=None)
    else:
        now_for_forecast = now_local
    forecast_df = grid.get_forecast(hours=hours, start_time=now_for_forecast)

    # Display parameters being used
    resolved_instance = instance_type or "default"
    resolved_provider = provider or "default"
    console.print(
        f"[dim]Parameters: region={region}, hours={hours}, instance={resolved_instance}, provider={resolved_provider}[/dim]"
    )
    console.print()

    # Handle export if requested
    if output:
        from arboric.cli.export import ExportError, ExportFormat, detect_format, export_forecast

        # Determine format
        if format:
            try:
                export_format = ExportFormat(format.lower())
            except ValueError:
                console.print(
                    f"[{ARBORIC_RED}]Invalid format '{format}'. Use 'json' or 'csv'.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)
        else:
            export_format = detect_format(output)
            if not export_format:
                console.print(
                    f"[{ARBORIC_RED}]Cannot detect format from '{output}'. Use --format flag.[/{ARBORIC_RED}]"
                )
                raise typer.Exit(1)

        # Export
        try:
            export_forecast(forecast_df, region, hours, output, export_format, command="forecast")
            if output != "-":
                console.print(f"[{ARBORIC_GREEN}]✓ Exported to {output}[/{ARBORIC_GREEN}]")
                console.print()
        except ExportError as e:
            console.print(f"[{ARBORIC_RED}]Export failed: {e}[/{ARBORIC_RED}]")
            raise typer.Exit(1)

    # Create forecast table
    table = Table(
        title=f"[bold]Grid Forecast: {region}",
        box=box.ROUNDED,
        border_style=ARBORIC_BLUE,
        header_style=f"bold {ARBORIC_BLUE}",
    )
    table.add_column("Time", style="white", width=8)
    table.add_column("Price", justify="right", width=12)
    table.add_column("Carbon", justify="right", width=14)
    table.add_column("Renewable", justify="right", width=12)
    table.add_column("Status", justify="center", width=20)

    for timestamp, row in forecast_df.iterrows():
        # Price color thresholds (spot instance $/hour)
        price_color = (
            ARBORIC_GREEN
            if row["price"] < 6.0
            else (ARBORIC_AMBER if row["price"] < 12.0 else ARBORIC_RED)
        )
        carbon_color = (
            ARBORIC_GREEN
            if row["co2_intensity"] < 250
            else (ARBORIC_AMBER if row["co2_intensity"] < 400 else ARBORIC_RED)
        )

        # Status indicator
        status_parts = []
        if row["price"] < 6.0:
            status_parts.append("💰 CHEAP")
        if row["co2_intensity"] < 200:
            status_parts.append("🌱 GREEN")
        if row["price"] > 12.0:
            status_parts.append("⚠️  PEAK")
        if row["co2_intensity"] > 500:
            status_parts.append("🏭 DIRTY")

        status = " ".join(status_parts) if status_parts else "─"

        table.add_row(
            format_local_time(timestamp),
            f"[{price_color}]${row['price']:.4f}[/{price_color}]",
            f"[{carbon_color}]{row['co2_intensity']:.0f} gCO₂[/{carbon_color}]",
            f"{row['renewable_percentage']:.0f}%",
            status,
        )

    console.print(table)

    # Summary stats
    console.print()
    console.print("[bold]Summary:[/bold]")
    console.print(
        f"  Price range:  ${forecast_df['price'].min():.2f} - ${forecast_df['price'].max():.2f}/hr"
    )
    console.print(
        f"  Carbon range: {forecast_df['co2_intensity'].min():.0f} - {forecast_df['co2_intensity'].max():.0f} gCO₂/kWh"
    )

    # Best windows
    best_price_idx = forecast_df["price"].idxmin()
    best_carbon_idx = forecast_df["co2_intensity"].idxmin()

    console.print()
    console.print(
        f"[bold {ARBORIC_GREEN}]Best price window:[/bold {ARBORIC_GREEN}] {format_local_time(best_price_idx)} (${forecast_df.loc[best_price_idx, 'price']:.2f}/hr)"
    )
    console.print(
        f"[bold {ARBORIC_GREEN}]Greenest window:[/bold {ARBORIC_GREEN}] {format_local_time(best_carbon_idx)} ({forecast_df.loc[best_carbon_idx, 'co2_intensity']:.0f} gCO₂/kWh)"
    )


@app.command()
def status():
    """Display Arboric system status and configuration."""
    print_banner()
    console.print()

    # Determine actual grid type being used
    from arboric.core.grid_oracle import get_grid

    config = get_config()
    grid = get_grid(region="eastus", config=config)
    mode = "live" if getattr(grid, "is_live", False) else "simulation"
    grid_details = f"Grid ({mode} mode)"

    status_table = Table(
        title="[bold]System Status",
        box=box.ROUNDED,
        border_style=ARBORIC_BLUE,
    )
    status_table.add_column("Component", style="white", width=25)
    status_table.add_column("Status", justify="center", width=15)
    status_table.add_column("Details", width=35)

    status_table.add_row(
        "Grid Oracle",
        f"[{ARBORIC_GREEN}]● ONLINE[/{ARBORIC_GREEN}]",
        grid_details,
    )
    # Format optimization weights as percentages
    cost_pct = int(config.optimization.cost_weight * 100)
    carbon_pct = int(config.optimization.carbon_weight * 100)

    status_table.add_row(
        "Autopilot Engine",
        f"[{ARBORIC_GREEN}]● READY[/{ARBORIC_GREEN}]",
        f"v1.0.0 | {cost_pct}/{carbon_pct} cost/carbon weights",
    )

    # Get supported regions from grid oracle
    from arboric.core.grid_oracle import REGION_PROFILES

    regions = ", ".join(sorted(REGION_PROFILES.keys()))
    region_count = len(REGION_PROFILES)

    status_table.add_row(
        "Supported Regions",
        f"[{ARBORIC_GREEN}]● {region_count} ACTIVE[/{ARBORIC_GREEN}]",
        regions,
    )
    # Determine data sources
    data_sources = []
    live_data_config = config.live_data
    if live_data_config.enabled and live_data_config.api_key:
        data_sources.append("Live Data")
    if not data_sources:
        data_sources.append("MockGrid")

    data_source_text = " + ".join(data_sources)
    api_status = (
        f"[{ARBORIC_GREEN}]● {data_source_text}[/{ARBORIC_GREEN}]"
        if "Live Data" in data_source_text
        else f"[{ARBORIC_AMBER}]○ {data_source_text}[/{ARBORIC_AMBER}]"
    )

    # Determine data source details
    if "Live Data" in data_source_text:
        data_details = "Live carbon + pricing"
    else:
        data_details = "Simulated grid data"

    status_table.add_row(
        "API Integration",
        api_status,
        data_details,
    )

    console.print(status_table)
    console.print()

    console.print("[dim]Run 'arboric --help' for available commands.[/dim]")


@app.command()
def config(
    action: str = typer.Argument(..., help="Action: show, init, edit, path"),
):
    """
    Manage Arboric configuration.

    Actions:
        show  - Display current configuration
        init  - Create default config file
        edit  - Open config file in editor
        path  - Show config file path
    """
    config_path = ArboricConfig.get_config_path()

    if action == "show":
        # Display current configuration
        try:
            cfg = get_config()
            console.print(f"\n[bold {ARBORIC_BLUE}]Arboric Configuration[/bold {ARBORIC_BLUE}]")
            console.print(f"[dim]Loaded from: {config_path}[/dim]\n")

            # Optimization settings
            opt_table = Table(
                title="Optimization Settings",
                box=box.ROUNDED,
                border_style=ARBORIC_GREEN,
            )
            opt_table.add_column("Setting", style="white")
            opt_table.add_column("Value", style=f"bold {ARBORIC_GREEN}", justify="right")

            opt_table.add_row("Cost Weight", f"{cfg.optimization.cost_weight:.1%}")
            opt_table.add_row("Carbon Weight", f"{cfg.optimization.carbon_weight:.1%}")
            opt_table.add_row("Min Delay (hours)", f"{cfg.optimization.min_delay_hours}")
            opt_table.add_row("Prefer Continuous", str(cfg.optimization.prefer_continuous))
            console.print(opt_table)
            console.print()

            # Default workload settings
            default_table = Table(
                title="Default Workload Settings",
                box=box.ROUNDED,
                border_style=ARBORIC_BLUE,
            )
            default_table.add_column("Setting", style="white")
            default_table.add_column("Value", style=f"bold {ARBORIC_BLUE}", justify="right")

            default_table.add_row("Duration", f"{cfg.defaults.duration_hours}h")
            default_table.add_row("Power Draw", f"{cfg.defaults.power_draw_kw} kW")
            default_table.add_row("Deadline", f"{cfg.defaults.deadline_hours}h")
            default_table.add_row("Region", cfg.defaults.region)
            console.print(default_table)
            console.print()

            # CLI settings
            cli_table = Table(
                title="CLI Settings",
                box=box.ROUNDED,
                border_style=ARBORIC_PURPLE,
            )
            cli_table.add_column("Setting", style="white")
            cli_table.add_column("Value", style=f"bold {ARBORIC_PURPLE}", justify="right")

            cli_table.add_row("Show Banner", str(cfg.cli.show_banner))
            cli_table.add_row("Color Theme", cfg.cli.color_theme)
            cli_table.add_row("Quiet Mode", str(cfg.cli.quiet_mode))
            cli_table.add_row("Auto Approve", str(cfg.cli.auto_approve))
            console.print(cli_table)
            console.print()

            # Live data settings
            if cfg.live_data.enabled:
                console.print(f"[{ARBORIC_GREEN}]✓[/{ARBORIC_GREEN}] Live data integration enabled")
            else:
                console.print(
                    f"[{ARBORIC_AMBER}]○[/{ARBORIC_AMBER}] Live data integration disabled"
                )
            console.print()

        except Exception as e:
            console.print(f"[{ARBORIC_RED}]Error loading configuration: {e}[/{ARBORIC_RED}]")

    elif action == "init":
        # Create default config file
        if config_path.exists():
            console.print(f"[{ARBORIC_AMBER}]Config file already exists at:[/{ARBORIC_AMBER}]")
            console.print(f"  {config_path}")
            console.print("\n[dim]Use 'arboric config edit' to modify it.[/dim]")
        else:
            try:
                cfg = ArboricConfig.create_default_config()
                console.print(
                    f"[{ARBORIC_GREEN}]✓[/{ARBORIC_GREEN}] Created default configuration at:"
                )
                console.print(f"  {config_path}")
                console.print("\n[dim]Edit this file to customize your settings.[/dim]")
            except Exception as e:
                console.print(f"[{ARBORIC_RED}]Error creating config: {e}[/{ARBORIC_RED}]")

    elif action == "edit":
        # Open config file in editor
        import os
        import subprocess

        if not config_path.exists():
            console.print(
                f"[{ARBORIC_AMBER}]Config file doesn't exist. Creating default...[/{ARBORIC_AMBER}]"
            )
            ArboricConfig.create_default_config()

        # Try to open in user's preferred editor
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
        try:
            subprocess.run([editor, str(config_path)], check=True)
            console.print(f"[{ARBORIC_GREEN}]✓[/{ARBORIC_GREEN}] Configuration saved")
        except FileNotFoundError:
            console.print(
                f"[{ARBORIC_AMBER}]Editor '{editor}' not found. Config file location:[/{ARBORIC_AMBER}]"
            )
            console.print(f"  {config_path}")
        except Exception as e:
            console.print(f"[{ARBORIC_RED}]Error opening editor: {e}[/{ARBORIC_RED}]")

    elif action == "path":
        # Show config file path
        if config_path.exists():
            console.print(f"[{ARBORIC_GREEN}]Configuration file:[/{ARBORIC_GREEN}]")
            console.print(f"  {config_path}")
            console.print("\n[dim]Use 'arboric config edit' to modify it.[/dim]")
        else:
            console.print(f"[{ARBORIC_AMBER}]No configuration file found.[/{ARBORIC_AMBER}]")
            console.print(f"Expected location: {config_path}")
            console.print("\n[dim]Use 'arboric config init' to create one.[/dim]")

    else:
        console.print(f"[{ARBORIC_RED}]Unknown action: {action}[/{ARBORIC_RED}]")
        console.print("\nAvailable actions: show, init, edit, path")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of runs to display"),
    since: str = typer.Option("30d", "--since", "-s", help="Time period: 7d, 30d, 90d, all"),
    region: str | None = typer.Option(None, "--region", "-r", help="Filter by region"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
):
    """
    View historical optimization runs and ROI metrics.

    Example: arboric history
    Example: arboric history --limit 10 --since 7d --region eastus
    Example: arboric history --format json
    """
    from pathlib import Path

    cfg = get_config()

    # Parse since parameter
    since_days_map = {"7d": 7, "30d": 30, "90d": 90, "all": None}
    since_days = since_days_map.get(since, 30)

    # Load history
    store = HistoryStore(Path(cfg.history.db_path).expanduser())
    rows = store.query(limit=limit, since_days=since_days, region=region)

    if not rows:
        console.print("[yellow]No optimization history found.[/yellow]")
        console.print("Run 'arboric optimize' to start tracking your workloads.")
        return

    if format == "json":
        console.print_json(data=rows)
    elif format == "csv":
        import csv
        import sys

        writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    else:  # table
        table = Table(title="Optimization History", box=box.ROUNDED, show_header=True)
        table.add_column("Job", style=ARBORIC_BLUE)
        table.add_column("When", style=ARBORIC_AMBER)
        table.add_column("Cost Saved", style=ARBORIC_GREEN)
        table.add_column("CO₂ Avoided", style=ARBORIC_GREEN)
        table.add_column("Region", style=ARBORIC_PURPLE)

        for row in rows:
            from datetime import datetime

            recorded = datetime.fromisoformat(row["recorded_at"])
            time_ago = (datetime.now(recorded.tzinfo) - recorded).total_seconds()

            if time_ago < 3600:
                when = f"{int(time_ago / 60)}m ago"
            elif time_ago < 86400:
                when = f"{int(time_ago / 3600)}h ago"
            else:
                when = f"{int(time_ago / 86400)}d ago"

            table.add_row(
                row["workload_name"],
                when,
                f"${row['cost_savings']:.2f}" if row["cost_savings"] else "—",
                f"{row['carbon_savings_kg']:.1f} kg" if row["carbon_savings_kg"] else "—",
                row["region"] or "—",
            )

        console.print(table)
        console.print(f"\n[dim]Showing {len(rows)} of {limit} results from last {since}[/dim]")


@app.command()
def insights(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: 7d, 30d, 90d, all"),
    region: str | None = typer.Option(None, "--region", "-r", help="Filter by region"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
):
    """
    View ROI insights and savings summary.

    Example: arboric insights
    Example: arboric insights --period 90d --region eastus
    Example: arboric insights --format json
    """
    from pathlib import Path

    cfg = get_config()

    # Parse period parameter
    period_days_map = {"7d": 7, "30d": 30, "90d": 90, "all": None}
    period_days = period_days_map.get(period, 30)

    # Get aggregated insights
    store = HistoryStore(Path(cfg.history.db_path).expanduser())
    agg = store.aggregate(since_days=period_days, region=region)

    if agg["total_jobs"] == 0:
        console.print("[yellow]No history for the selected period.[/yellow]")
        console.print("Run 'arboric optimize' to start tracking your workloads.")
        return

    if format == "json":
        console.print_json(data=agg)
    else:  # table
        insights_text = f"""[bold white]Jobs Optimized[/bold white]
{agg["total_jobs"]}

[bold white]Total Cost Saved[/bold white]
${agg["total_cost_savings"]:.2f}  (avg ${agg["total_cost_savings"] / agg["total_jobs"]:.2f}/job)

[bold white]Total CO₂ Avoided[/bold white]
{agg["total_carbon_savings_kg"]:.1f} kg  (avg {agg["total_carbon_savings_kg"] / agg["total_jobs"]:.1f} kg/job)

[bold white]Avg Cost Savings[/bold white]
{agg["avg_cost_savings_percent"]:.1f}%

[bold white]Avg Carbon Savings[/bold white]
{agg["avg_carbon_savings_percent"]:.1f}%"""

        if agg["best_region"]:
            insights_text += (
                f"\n\n[bold white]Most Active Region[/bold white]\n{agg['best_region']}"
            )

        if agg["top_workload"]:
            insights_text += (
                f"\n\n[bold white]Top Optimized Job[/bold white]\n{agg['top_workload']}"
            )

        panel = Panel(
            insights_text,
            title=f"[bold]ROI Insights — {period}",
            border_style=ARBORIC_GREEN,
            padding=(1, 2),
        )
        console.print(panel)


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
):
    """
    Start the Arboric REST API server.

    The API provides HTTP endpoints for workload optimization, enabling
    integration with orchestration tools like Airflow, Prefect, and Dagster.

    Example: arboric api --host 0.0.0.0 --port 8000 --reload

    Once started, visit http://localhost:8000/docs for interactive API documentation.
    """
    import uvicorn

    console.print(f"[{ARBORIC_GREEN}]🚀 Starting Arboric API server...[/{ARBORIC_GREEN}]")
    console.print()
    console.print(f"  Host:     {host}")
    console.print(f"  Port:     {port}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Docs:     http://{host}:{port}/docs")
    console.print(f"  Health:   http://{host}:{port}/api/v1/health")
    console.print()

    if reload:
        console.print(
            f"[{ARBORIC_AMBER}]⚠️  Auto-reload enabled (development mode)[/{ARBORIC_AMBER}]"
        )
        console.print()

    uvicorn.run(
        "arboric.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,  # reload requires single worker
        log_level="info",
    )


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
