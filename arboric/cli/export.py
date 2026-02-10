"""
Arboric Export Module

Handles exporting optimization results, forecasts, and fleet data
to various formats (JSON, CSV) for integration and analysis.
"""

import csv
import json
import sys
from datetime import datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Optional, TextIO, Union

import pandas as pd

from arboric.core.models import FleetOptimizationResult, ScheduleResult


class ExportFormat(str, Enum):
    """Supported export formats."""

    JSON = "json"
    CSV = "csv"


class ExportError(Exception):
    """Raised when export operation fails."""

    pass


def detect_format(output_path: str) -> Optional[ExportFormat]:
    """
    Auto-detect export format from file extension.

    Args:
        output_path: Path to output file

    Returns:
        ExportFormat if detected, None if unknown extension
    """
    if output_path == "-":
        return None  # Stdout requires explicit format

    path = Path(output_path)
    ext = path.suffix.lower()

    format_map = {
        ".json": ExportFormat.JSON,
        ".csv": ExportFormat.CSV,
    }

    return format_map.get(ext)


def _serialize_schedule_result(result: ScheduleResult) -> dict:
    """
    Serialize ScheduleResult including computed properties.

    Pydantic's model_dump() doesn't include @property decorated fields,
    so we must add them explicitly.

    Args:
        result: ScheduleResult to serialize

    Returns:
        Dictionary with all fields including computed properties
    """
    base_dict = result.model_dump()

    # Add computed properties from ScheduleResult
    base_dict["cost_savings"] = result.cost_savings
    base_dict["carbon_savings_kg"] = result.carbon_savings_kg
    base_dict["cost_savings_percent"] = result.cost_savings_percent
    base_dict["carbon_savings_percent"] = result.carbon_savings_percent
    base_dict["delay_hours"] = result.delay_hours

    # Add computed property from nested Workload
    base_dict["workload"]["energy_kwh"] = result.workload.energy_kwh

    return base_dict


def _serialize_fleet_result(result: FleetOptimizationResult) -> dict:
    """
    Serialize FleetOptimizationResult including computed properties.

    Args:
        result: FleetOptimizationResult to serialize

    Returns:
        Dictionary with all fields including computed properties
    """
    base_dict = result.model_dump()

    # Add computed properties
    base_dict["average_cost_savings_percent"] = result.average_cost_savings_percent
    base_dict["average_carbon_savings_percent"] = result.average_carbon_savings_percent

    # Serialize nested schedules with their computed properties
    base_dict["schedules"] = [
        _serialize_schedule_result(schedule) for schedule in result.schedules
    ]

    return base_dict


def _schedule_to_json(result: ScheduleResult, command: str = "optimize") -> dict:
    """
    Convert ScheduleResult to structured JSON format.

    Args:
        result: ScheduleResult to convert
        command: Command that generated this result

    Returns:
        Structured JSON dictionary
    """
    data = _serialize_schedule_result(result)

    return {
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
        "data": {
            "workload": data["workload"],
            "optimization": {
                "optimal_start": data["optimal_start"],
                "optimal_end": data["optimal_end"],
                "baseline_start": data["baseline_start"],
                "baseline_end": data["baseline_end"],
                "delay_hours": data["delay_hours"],
            },
            "metrics": {
                "optimized": {
                    "cost": data["optimized_cost"],
                    "carbon_kg": data["optimized_carbon_kg"],
                    "avg_price": data["optimized_avg_price"],
                    "avg_carbon": data["optimized_avg_carbon"],
                },
                "baseline": {
                    "cost": data["baseline_cost"],
                    "carbon_kg": data["baseline_carbon_kg"],
                    "avg_price": data["baseline_avg_price"],
                    "avg_carbon": data["baseline_avg_carbon"],
                },
                "savings": {
                    "cost": data["cost_savings"],
                    "cost_percent": data["cost_savings_percent"],
                    "carbon_kg": data["carbon_savings_kg"],
                    "carbon_percent": data["carbon_savings_percent"],
                },
            },
        },
    }


def _fleet_to_json(result: FleetOptimizationResult, command: str = "demo") -> dict:
    """
    Convert FleetOptimizationResult to structured JSON format.

    Args:
        result: FleetOptimizationResult to convert
        command: Command that generated this result

    Returns:
        Structured JSON dictionary
    """
    data = _serialize_fleet_result(result)

    return {
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
        "data": {
            "summary": {
                "total_workloads": data["total_workloads"],
                "total_cost_savings": data["total_cost_savings"],
                "total_carbon_savings_kg": data["total_carbon_savings_kg"],
                "average_cost_savings_percent": data["average_cost_savings_percent"],
                "average_carbon_savings_percent": data[
                    "average_carbon_savings_percent"
                ],
                "optimization_timestamp": data["optimization_timestamp"],
            },
            "schedules": [
                _schedule_to_json(result.schedules[i], command="optimize")["data"]
                for i in range(len(result.schedules))
            ],
        },
    }


def _schedule_to_csv_row(result: ScheduleResult, command: str = "optimize") -> dict:
    """
    Flatten ScheduleResult to a single CSV row.

    Args:
        result: ScheduleResult to flatten
        command: Command that generated this result

    Returns:
        Dictionary with flattened column names and values
    """
    data = _serialize_schedule_result(result)
    workload = data["workload"]

    return {
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
        # Workload fields
        "workload_id": str(workload["id"]),
        "workload_name": workload["name"],
        "workload_duration_hours": workload["duration_hours"],
        "workload_power_draw_kw": workload["power_draw_kw"],
        "workload_energy_kwh": workload["energy_kwh"],
        "workload_deadline_hours": workload["deadline_hours"],
        "workload_type": workload["workload_type"],
        "workload_priority": workload["priority"],
        "workload_description": workload.get("description", ""),
        # Optimization fields
        "optimal_start": data["optimal_start"],
        "optimal_end": data["optimal_end"],
        "baseline_start": data["baseline_start"],
        "baseline_end": data["baseline_end"],
        "delay_hours": data["delay_hours"],
        # Optimized metrics
        "optimized_cost": data["optimized_cost"],
        "optimized_carbon_kg": data["optimized_carbon_kg"],
        "optimized_avg_price": data["optimized_avg_price"],
        "optimized_avg_carbon": data["optimized_avg_carbon"],
        # Baseline metrics
        "baseline_cost": data["baseline_cost"],
        "baseline_carbon_kg": data["baseline_carbon_kg"],
        "baseline_avg_price": data["baseline_avg_price"],
        "baseline_avg_carbon": data["baseline_avg_carbon"],
        # Savings (computed properties)
        "cost_savings": data["cost_savings"],
        "cost_savings_percent": data["cost_savings_percent"],
        "carbon_savings_kg": data["carbon_savings_kg"],
        "carbon_savings_percent": data["carbon_savings_percent"],
    }


def _fleet_to_csv_rows(result: FleetOptimizationResult, command: str = "demo") -> list[dict]:
    """
    Convert FleetOptimizationResult to CSV rows (summary + details).

    First row contains fleet summary, remaining rows contain individual schedules.

    Args:
        result: FleetOptimizationResult to convert
        command: Command that generated this result

    Returns:
        List of row dictionaries (first is summary, rest are details)
    """
    data = _serialize_fleet_result(result)
    rows = []

    # Summary row
    summary_row = {
        "record_type": "summary",
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
        "fleet_total_workloads": data["total_workloads"],
        "fleet_total_cost_savings": data["total_cost_savings"],
        "fleet_total_carbon_savings_kg": data["total_carbon_savings_kg"],
        "fleet_avg_cost_savings_percent": data["average_cost_savings_percent"],
        "fleet_avg_carbon_savings_percent": data["average_carbon_savings_percent"],
        "fleet_optimization_timestamp": data["optimization_timestamp"],
    }
    rows.append(summary_row)

    # Detail rows (individual schedules)
    for schedule in result.schedules:
        detail_row = {"record_type": "detail"}
        detail_row.update(_schedule_to_csv_row(schedule, command="optimize"))
        rows.append(detail_row)

    return rows


def export_schedule_result(
    result: ScheduleResult,
    output: Union[str, Path],
    format: ExportFormat,
    command: str = "optimize",
) -> None:
    """
    Export a single optimization result.

    Args:
        result: ScheduleResult to export
        output: Output file path or '-' for stdout
        format: Export format (JSON or CSV)
        command: Command that generated this result

    Raises:
        ExportError: If export fails
    """
    try:
        if str(output) == "-":
            # Export to stdout
            if format == ExportFormat.JSON:
                json_data = _schedule_to_json(result, command)
                json.dump(json_data, sys.stdout, indent=2, default=str)
                sys.stdout.write("\n")
            elif format == ExportFormat.CSV:
                csv_row = _schedule_to_csv_row(result, command)
                writer = csv.DictWriter(sys.stdout, fieldnames=csv_row.keys())
                writer.writeheader()
                writer.writerow(csv_row)
        else:
            # Export to file
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if format == ExportFormat.JSON:
                json_data = _schedule_to_json(result, command)
                with open(output_path, "w") as f:
                    json.dump(json_data, f, indent=2, default=str)
            elif format == ExportFormat.CSV:
                csv_row = _schedule_to_csv_row(result, command)
                with open(output_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=csv_row.keys())
                    writer.writeheader()
                    writer.writerow(csv_row)

    except PermissionError as e:
        raise ExportError(f"Permission denied writing to {output}: {e}")
    except OSError as e:
        raise ExportError(f"Failed to write to {output}: {e}")
    except Exception as e:
        raise ExportError(f"Export failed: {e}")


def export_fleet_result(
    result: FleetOptimizationResult,
    output: Union[str, Path],
    format: ExportFormat,
    command: str = "demo",
) -> None:
    """
    Export fleet optimization results.

    Args:
        result: FleetOptimizationResult to export
        output: Output file path or '-' for stdout
        format: Export format (JSON or CSV)
        command: Command that generated this result

    Raises:
        ExportError: If export fails
    """
    try:
        if str(output) == "-":
            # Export to stdout
            if format == ExportFormat.JSON:
                json_data = _fleet_to_json(result, command)
                json.dump(json_data, sys.stdout, indent=2, default=str)
                sys.stdout.write("\n")
            elif format == ExportFormat.CSV:
                rows = _fleet_to_csv_rows(result, command)
                # Get all unique fieldnames from all rows
                fieldnames = []
                for row in rows:
                    for key in row.keys():
                        if key not in fieldnames:
                            fieldnames.append(key)

                writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        else:
            # Export to file
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if format == ExportFormat.JSON:
                json_data = _fleet_to_json(result, command)
                with open(output_path, "w") as f:
                    json.dump(json_data, f, indent=2, default=str)
            elif format == ExportFormat.CSV:
                rows = _fleet_to_csv_rows(result, command)
                # Get all unique fieldnames from all rows
                fieldnames = []
                for row in rows:
                    for key in row.keys():
                        if key not in fieldnames:
                            fieldnames.append(key)

                with open(output_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(row)

    except PermissionError as e:
        raise ExportError(f"Permission denied writing to {output}: {e}")
    except OSError as e:
        raise ExportError(f"Failed to write to {output}: {e}")
    except Exception as e:
        raise ExportError(f"Export failed: {e}")


def export_forecast(
    forecast_df: pd.DataFrame,
    region: str,
    hours: int,
    output: Union[str, Path],
    format: ExportFormat,
    command: str = "forecast",
) -> None:
    """
    Export grid forecast data.

    Args:
        forecast_df: Forecast DataFrame to export
        region: Grid region
        hours: Number of forecast hours
        output: Output file path or '-' for stdout
        format: Export format (JSON or CSV)
        command: Command that generated this result

    Raises:
        ExportError: If export fails
    """
    try:
        if format == ExportFormat.JSON:
            # Convert DataFrame to structured JSON with metadata
            json_data = {
                "command": command,
                "timestamp": datetime.now().isoformat(),
                "version": "0.1.0",
                "metadata": {
                    "region": region,
                    "hours": hours,
                    "data_points": len(forecast_df),
                },
                "data": json.loads(
                    forecast_df.reset_index().to_json(orient="records", date_format="iso")
                ),
            }

            if str(output) == "-":
                json.dump(json_data, sys.stdout, indent=2, default=str)
                sys.stdout.write("\n")
            else:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(json_data, f, indent=2, default=str)

        elif format == ExportFormat.CSV:
            # Export DataFrame directly to CSV
            if str(output) == "-":
                forecast_df.to_csv(sys.stdout)
            else:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                forecast_df.to_csv(output_path)

    except PermissionError as e:
        raise ExportError(f"Permission denied writing to {output}: {e}")
    except OSError as e:
        raise ExportError(f"Failed to write to {output}: {e}")
    except Exception as e:
        raise ExportError(f"Export failed: {e}")
