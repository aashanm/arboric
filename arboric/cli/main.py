"""
Arboric CLI

The command-line interface for Arboric - intelligent workload scheduling
for cost and carbon optimization. Built with Typer and Rich.
"""

import time

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
from arboric.core.grid_oracle import MockGrid
from arboric.core.models import FleetOptimizationResult, Workload, WorkloadType

# Initialize Rich console
console = Console()

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
    table.add_row(
        "Start Time",
        result.baseline_start.strftime("%H:%M"),
        result.optimal_start.strftime("%H:%M"),
        f"+{result.delay_hours:.1f}h delay" if result.delay_hours > 0 else "Immediate",
    )

    # Avg Price
    table.add_row(
        "Avg Price",
        f"${result.baseline_avg_price:.4f}/kWh",
        f"${result.optimized_avg_price:.4f}/kWh",
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
    lines.append(f"  {'Price ($/kWh)':<20} │ ${price_max:.3f}")
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
    lines.append(f"  {'':20} │ ${price_min:.3f}")
    lines.append(f"  {'':20} └{'─' * hours}")

    # Hour labels
    hour_labels = "  " + " " * 21
    for i in range(0, hours, 4):
        ts = forecast_df.index[i]
        hour_labels += f"{ts.hour:02d}  "
    lines.append(hour_labels + " (hour)")

    return "\n".join(lines)


def simulate_optimization_animation(workload_name: str, duration: float = 1.5):
    """Display animated optimization process."""
    steps = [
        ("Connecting to Grid Oracle...", 0.2),
        ("Fetching 24h forecast data...", 0.3),
        ("Analyzing carbon intensity patterns...", 0.2),
        ("Scanning for price anomalies...", 0.2),
        ("Detecting solar duck curve...", 0.15),
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


@app.command()
def optimize(
    workload_name: str = typer.Argument(..., help="Name of the workload to optimize"),
    duration: float | None = typer.Option(
        None, "--duration", "-d", help="Workload duration in hours"
    ),
    deadline: float | None = typer.Option(
        None, "--deadline", "-D", help="Must complete within hours"
    ),
    power: float | None = typer.Option(None, "--power", "-p", help="Power draw in kW"),
    region: str | None = typer.Option(None, "--region", "-r", help="Grid region"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (or '-' for stdout)"
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Export format: json, csv"),
):
    """
    Optimize a single workload for cost and carbon efficiency.

    Example: arboric optimize "LLM Training" --duration 6 --deadline 24

    Export results: arboric optimize "Job" --output results.json

    If options are not specified, values from ~/.arboric/config.yaml will be used.
    """
    # Load configuration for defaults
    cfg = get_config()

    # Use config defaults if not specified
    duration = duration if duration is not None else cfg.defaults.duration_hours
    deadline = deadline if deadline is not None else cfg.defaults.deadline_hours
    power = power if power is not None else cfg.defaults.power_draw_kw
    region = region if region is not None else cfg.defaults.region
    quiet = quiet or cfg.cli.quiet_mode

    if not quiet and cfg.cli.show_banner:
        print_banner()
        console.print()

    # Create workload
    workload = Workload(
        name=workload_name,
        duration_hours=duration,
        power_draw_kw=power,
        deadline_hours=deadline,
        workload_type=WorkloadType.ML_TRAINING,
    )

    # Display workload info
    workload_panel = Panel(
        f"""[bold]Workload:[/bold] {workload.name}
[bold]Duration:[/bold] {workload.duration_hours}h
[bold]Power Draw:[/bold] {workload.power_draw_kw} kW
[bold]Energy:[/bold] {workload.energy_kwh} kWh
[bold]Deadline:[/bold] {workload.deadline_hours}h from now
[bold]Region:[/bold] {region}""",
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
    grid = MockGrid(region=region)
    forecast = grid.get_forecast(hours=int(deadline) + int(duration) + 2)

    # Create autopilot with config-based optimization settings
    opt_config = OptimizationConfig(
        cost_weight=cfg.optimization.cost_weight,
        carbon_weight=cfg.optimization.carbon_weight,
        min_delay_hours=cfg.optimization.min_delay_hours,
        prefer_continuous=cfg.optimization.prefer_continuous,
    )
    autopilot = Autopilot(config=opt_config)
    result = autopilot.optimize_schedule(workload, forecast)

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
            f"{result.optimal_start.strftime('%H:%M')} "
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
    yield_panel = Panel(
        Align.center(
            Text.from_markup(
                f"[bold {ARBORIC_GREEN}]TOTAL YIELD[/bold {ARBORIC_GREEN}]\n\n"
                f"[bold white]💰 ${result.cost_savings:.2f} saved[/bold white]  ·  "
                f"[bold white]🌱 {result.carbon_savings_kg:.2f} kg CO₂ avoided[/bold white]\n\n"
                f"[dim]Cost reduction: {result.cost_savings_percent:.1f}% | "
                f"Carbon reduction: {result.carbon_savings_percent:.1f}%[/dim]"
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
    power: float | None = typer.Option(None, "--power", "-p", help="Power draw in kW"),
    region: str | None = typer.Option(None, "--region", "-r", help="Grid region"),
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
    power = power if power is not None else cfg.defaults.power_draw_kw
    region = region if region is not None else cfg.defaults.region
    quiet = quiet or cfg.cli.quiet_mode

    if not quiet and cfg.cli.show_banner:
        print_banner()
        console.print()

    workload = Workload(
        name=workload_name,
        duration_hours=duration,
        power_draw_kw=power,
        deadline_hours=deadline,
        workload_type=WorkloadType.ML_TRAINING,
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

    grid = MockGrid(region=region)
    forecast = grid.get_forecast(hours=int(deadline) + int(duration) + 2)

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
            point["start_time"].strftime("%H:%M"),
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

[dim]Region: US-WEST  |  Forecast Horizon: 24h  |  Optimization: 70% cost / 30% carbon[/dim]""",
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
    from datetime import datetime

    demo_start = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)

    grid = MockGrid(region="US-WEST", seed=42)  # Fixed seed for consistent demo results
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
    results_table.add_column("Workload", style="white", width=28)
    results_table.add_column("Scheduled", justify="center", width=12)
    results_table.add_column("Delay", justify="right", width=8)
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
            r.workload.name[:27],
            r.optimal_start.strftime("%H:%M"),
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

    # Final impact panel
    impact_text = f"""
[bold {ARBORIC_GREEN}]                    ARBORIC IMPACT REPORT                    [/bold {ARBORIC_GREEN}]

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   [bold]Fleet Optimization Summary[/bold]                             │
│                                                             │
│   Workloads Processed:  [bold]{len(demo_workloads)}[/bold]                                │
│   Total Energy:         [bold]{sum(w.energy_kwh for w in demo_workloads):,.0f} kWh[/bold]                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [bold {ARBORIC_RED}]Without Arboric[/bold {ARBORIC_RED}]          [bold {ARBORIC_GREEN}]With Arboric[/bold {ARBORIC_GREEN}]               │
│   ─────────────────      ─────────────────               │
│   Cost:    ${total_baseline_cost:>8,.2f}        Cost:    ${total_optimized_cost:>8,.2f}             │
│   Carbon:  {total_baseline_carbon:>8,.2f} kg      Carbon:  {total_optimized_carbon:>8,.2f} kg           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [bold {cost_savings_color}]💰 COST {cost_savings_label}:      ${abs(total_cost_saved):>8,.2f}  ({abs(cost_reduction_pct):.1f}% {"saved" if total_cost_saved >= 0 else "increase"})[/bold {cost_savings_color}]   │
│   [bold {ARBORIC_GREEN}]🌱 CARBON AVOIDED:    {total_carbon_saved:>8,.2f} kg ({carbon_reduction_pct:.1f}% reduction)[/bold {ARBORIC_GREEN}]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘

[bold {cost_savings_color}]═══════════════════════════════════════════════════════════════[/bold {cost_savings_color}]
[bold {cost_savings_color}]  💵 ANNUALIZED SAVINGS: ${abs(annual_cost_savings):>,.0f}/year {"" if total_cost_saved >= 0 else "(projected cost increase)"}[/bold {cost_savings_color}]
[bold {cost_savings_color}]═══════════════════════════════════════════════════════════════[/bold {cost_savings_color}]

[dim]Plus: 🌲 {annual_carbon_savings / 1000:,.1f} metric tons CO₂ avoided per year[/dim]
"""

    console.print(
        Panel(
            impact_text,
            border_style=ARBORIC_GREEN,
            padding=(0, 1),
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
    region: str = typer.Option("US-WEST", "--region", "-r", help="Grid region"),
    hours: int = typer.Option(24, "--hours", "-h", help="Forecast hours"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (or '-' for stdout)"
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Export format: json, csv"),
):
    """
    Display the current grid forecast for a region.

    Shows carbon intensity and pricing over the forecast horizon.

    Export forecast: arboric forecast --output forecast.csv --region US-WEST --hours 24
    """
    print_banner()
    console.print()

    console.print(f"[bold]Fetching {hours}h forecast for {region}...[/bold]")
    console.print()

    grid = MockGrid(region=region)
    forecast_df = grid.get_forecast(hours=hours)

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
        price_color = (
            ARBORIC_GREEN
            if row["price"] < 0.10
            else (ARBORIC_AMBER if row["price"] < 0.15 else ARBORIC_RED)
        )
        carbon_color = (
            ARBORIC_GREEN
            if row["co2_intensity"] < 250
            else (ARBORIC_AMBER if row["co2_intensity"] < 400 else ARBORIC_RED)
        )

        # Status indicator
        status_parts = []
        if row["price"] < 0.08:
            status_parts.append("💰 CHEAP")
        if row["co2_intensity"] < 200:
            status_parts.append("🌱 GREEN")
        if row["price"] > 0.18:
            status_parts.append("⚠️  PEAK")
        if row["co2_intensity"] > 500:
            status_parts.append("🏭 DIRTY")

        status = " ".join(status_parts) if status_parts else "─"

        table.add_row(
            timestamp.strftime("%H:%M"),
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
        f"  Price range:  ${forecast_df['price'].min():.4f} - ${forecast_df['price'].max():.4f}/kWh"
    )
    console.print(
        f"  Carbon range: {forecast_df['co2_intensity'].min():.0f} - {forecast_df['co2_intensity'].max():.0f} gCO₂/kWh"
    )

    # Best windows
    best_price_idx = forecast_df["price"].idxmin()
    best_carbon_idx = forecast_df["co2_intensity"].idxmin()

    console.print()
    console.print(
        f"[bold {ARBORIC_GREEN}]Best price window:[/bold {ARBORIC_GREEN}] {best_price_idx.strftime('%H:%M')} (${forecast_df.loc[best_price_idx, 'price']:.4f}/kWh)"
    )
    console.print(
        f"[bold {ARBORIC_GREEN}]Greenest window:[/bold {ARBORIC_GREEN}] {best_carbon_idx.strftime('%H:%M')} ({forecast_df.loc[best_carbon_idx, 'co2_intensity']:.0f} gCO₂/kWh)"
    )


@app.command()
def status():
    """Display Arboric system status and configuration."""
    print_banner()
    console.print()

    # Determine actual grid type being used
    from arboric.core.grid_oracle import get_grid

    config = get_config()
    grid = get_grid(region="US-WEST", config=config)
    grid_type = type(grid).__name__
    mode = "live" if isinstance(grid, type(grid)) and grid_type == "LiveGrid" else "simulation"
    grid_details = f"{grid_type} ({mode} mode)"

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
    status_table.add_row(
        "Autopilot Engine",
        f"[{ARBORIC_GREEN}]● READY[/{ARBORIC_GREEN}]",
        "v1.0.0 | 60/40 cost/carbon weights",
    )
    status_table.add_row(
        "Supported Regions",
        f"[{ARBORIC_GREEN}]● 4 ACTIVE[/{ARBORIC_GREEN}]",
        "US-WEST, US-EAST, EU-WEST, NORDIC",
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

    status_table.add_row(
        "API Integration",
        api_status,
        "Live carbon data + simulated pricing"
        if "Live Data" in data_source_text
        else "Simulated grid data",
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

            # API settings
            if cfg.api.live_api_enabled:
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
