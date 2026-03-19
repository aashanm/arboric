"""
Historical optimization tracking and ROI reporting.

Stores all optimization results to a local SQLite database for:
- ROI reporting (show CFOs actual savings over time)
- Trend analysis (which jobs benefit most from scheduling?)
- Audit trail (compliance + proof of carbon-aware decisions)

Database location: ~/.arboric/history.db
File permissions protect access (per-user, per-machine).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlite3 import Row, connect

from arboric.core.models import ScheduleResult

logger = logging.getLogger(__name__)


class HistoryStore:
    """SQLite-backed storage for optimization runs."""

    def __init__(self, db_path: Path):
        """
        Initialize history store.

        Args:
            db_path: Path to SQLite database file (~/.arboric/history.db)
        """
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create table if it doesn't exist. Silent on failure."""
        try:
            with connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS optimization_runs (
                        id              TEXT PRIMARY KEY,
                        recorded_at     TEXT NOT NULL,
                        workload_name   TEXT NOT NULL,
                        workload_type   TEXT,
                        duration_hours  REAL,
                        power_draw_kw   REAL,
                        energy_kwh      REAL,
                        deadline_hours  REAL,
                        region          TEXT,
                        data_source     TEXT DEFAULT 'mockgrid',
                        optimal_start   TEXT,
                        baseline_start  TEXT,
                        delay_hours     REAL,
                        optimized_cost  REAL,
                        baseline_cost   REAL,
                        cost_savings    REAL,
                        cost_savings_percent REAL,
                        optimized_carbon_kg  REAL,
                        baseline_carbon_kg   REAL,
                        carbon_savings_kg    REAL,
                        carbon_savings_percent REAL,
                        raw_json        TEXT
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to initialize history database: {e}")

    def record(
        self,
        result: ScheduleResult,
        region: str,
        data_source: str = "mockgrid",
    ) -> None:
        """
        Record an optimization run to history.

        Silent on failure — never interrupts the optimize workflow.

        Args:
            result: ScheduleResult from autopilot
            region: Grid region (US-WEST, US-EAST, etc)
            data_source: 'mockgrid' or 'live'
        """
        try:
            recorded_at = datetime.now(timezone.utc).isoformat()
            workload = result.workload

            with connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO optimization_runs (
                        id, recorded_at, workload_name, workload_type,
                        duration_hours, power_draw_kw, energy_kwh, deadline_hours,
                        region, data_source,
                        optimal_start, baseline_start, delay_hours,
                        optimized_cost, baseline_cost, cost_savings, cost_savings_percent,
                        optimized_carbon_kg, baseline_carbon_kg, carbon_savings_kg, carbon_savings_percent,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(workload.id),
                        recorded_at,
                        workload.name,
                        workload.workload_type.value if workload.workload_type else None,
                        result.workload.duration_hours,
                        result.workload.power_draw_kw,
                        result.workload.duration_hours * result.workload.power_draw_kw,
                        result.workload.deadline_hours,
                        region,
                        data_source,
                        result.optimal_start.isoformat(),
                        result.baseline_start.isoformat(),
                        (result.optimal_start - result.baseline_start).total_seconds() / 3600,
                        result.optimized_cost,
                        result.baseline_cost,
                        result.baseline_cost - result.optimized_cost,
                        (
                            (result.baseline_cost - result.optimized_cost)
                            / result.baseline_cost
                            * 100
                        )
                        if result.baseline_cost > 0
                        else 0,
                        result.optimized_carbon_kg,
                        result.baseline_carbon_kg,
                        result.baseline_carbon_kg - result.optimized_carbon_kg,
                        (
                            (result.baseline_carbon_kg - result.optimized_carbon_kg)
                            / result.baseline_carbon_kg
                            * 100
                        )
                        if result.baseline_carbon_kg > 0
                        else 0,
                        json.dumps(self._serialize_result(result)),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record optimization run: {e}")

    def query(
        self,
        limit: int = 20,
        since_days: int | None = 30,
        region: str | None = None,
    ) -> list[dict]:
        """
        Query historical runs.

        Args:
            limit: Max number of rows (default 20, max 500)
            since_days: Include only runs from last N days (None = all time)
            region: Filter by region (None = all regions)

        Returns:
            List of dicts, newest first
        """
        limit = min(limit, 500)

        try:
            with connect(self.db_path) as conn:
                conn.row_factory = Row

                # Build WHERE clause
                where_parts = []
                params = []

                if since_days is not None:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
                    where_parts.append("recorded_at >= ?")
                    params.append(cutoff.isoformat())

                if region:
                    where_parts.append("region = ?")
                    params.append(region)

                where_clause = " AND ".join(where_parts) if where_parts else "1=1"

                params.extend([limit])

                rows = conn.execute(
                    f"""
                    SELECT * FROM optimization_runs
                    WHERE {where_clause}
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()

                return [dict(row) for row in rows]

        except Exception as e:
            logger.warning(f"Failed to query history: {e}")
            return []

    def aggregate(
        self,
        since_days: int | None = 30,
        region: str | None = None,
    ) -> dict:
        """
        Get ROI summary statistics.

        Args:
            since_days: Include only runs from last N days (None = all time)
            region: Filter by region (None = all regions)

        Returns:
            Dict with total_jobs, total_cost_savings, total_carbon_savings_kg,
            avg_cost_savings_percent, avg_carbon_savings_percent, best_region, top_workload
        """
        try:
            with connect(self.db_path) as conn:
                # Build WHERE clause
                where_parts = []
                params = []

                if since_days is not None:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
                    where_parts.append("recorded_at >= ?")
                    params.append(cutoff.isoformat())

                if region:
                    where_parts.append("region = ?")
                    params.append(region)

                where_clause = " AND ".join(where_parts) if where_parts else "1=1"

                # Aggregate stats
                agg = conn.execute(
                    f"""
                    SELECT
                        COUNT(*) as total_jobs,
                        COALESCE(SUM(cost_savings), 0) as total_cost_savings,
                        COALESCE(SUM(carbon_savings_kg), 0) as total_carbon_savings_kg,
                        COALESCE(AVG(cost_savings_percent), 0) as avg_cost_savings_percent,
                        COALESCE(AVG(carbon_savings_percent), 0) as avg_carbon_savings_percent
                    FROM optimization_runs
                    WHERE {where_clause}
                    """,
                    params,
                ).fetchone()

                # Best region (most jobs)
                best_region_row = conn.execute(
                    f"""
                    SELECT region, COUNT(*) as count
                    FROM optimization_runs
                    WHERE {where_clause} AND region IS NOT NULL
                    GROUP BY region
                    ORDER BY count DESC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()

                # Top workload (most runs)
                top_workload_row = conn.execute(
                    f"""
                    SELECT workload_name, COUNT(*) as count
                    FROM optimization_runs
                    WHERE {where_clause}
                    GROUP BY workload_name
                    ORDER BY count DESC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()

                return {
                    "total_jobs": agg[0] if agg else 0,
                    "total_cost_savings": agg[1] if agg else 0.0,
                    "total_carbon_savings_kg": agg[2] if agg else 0.0,
                    "avg_cost_savings_percent": agg[3] if agg else 0.0,
                    "avg_carbon_savings_percent": agg[4] if agg else 0.0,
                    "best_region": best_region_row[0] if best_region_row else None,
                    "top_workload": top_workload_row[0] if top_workload_row else None,
                }

        except Exception as e:
            logger.warning(f"Failed to aggregate history: {e}")
            return {
                "total_jobs": 0,
                "total_cost_savings": 0.0,
                "total_carbon_savings_kg": 0.0,
                "avg_cost_savings_percent": 0.0,
                "avg_carbon_savings_percent": 0.0,
                "best_region": None,
                "top_workload": None,
            }

    def clear(self) -> None:
        """Delete all history. Used in tests and config reset."""
        try:
            with connect(self.db_path) as conn:
                conn.execute("DELETE FROM optimization_runs")
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to clear history: {e}")

    @staticmethod
    def _serialize_result(result: ScheduleResult) -> dict:
        """Serialize ScheduleResult to JSON-safe dict."""
        workload = result.workload
        return {
            "workload": {
                "id": str(workload.id),
                "name": workload.name,
                "type": workload.workload_type.value if workload.workload_type else None,
                "duration_hours": workload.duration_hours,
                "power_draw_kw": workload.power_draw_kw,
                "deadline_hours": workload.deadline_hours,
                "energy_kwh": workload.duration_hours * workload.power_draw_kw,
            },
            "optimization": {
                "optimal_start": result.optimal_start.isoformat(),
                "optimal_end": result.optimal_end.isoformat(),
                "baseline_start": result.baseline_start.isoformat(),
                "baseline_end": result.baseline_end.isoformat(),
                "delay_hours": (result.optimal_start - result.baseline_start).total_seconds()
                / 3600,
            },
            "metrics": {
                "optimized": {
                    "cost": result.optimized_cost,
                    "carbon_kg": result.optimized_carbon_kg,
                    "avg_price": result.optimized_avg_price,
                    "avg_carbon": result.optimized_avg_carbon,
                },
                "baseline": {
                    "cost": result.baseline_cost,
                    "carbon_kg": result.baseline_carbon_kg,
                    "avg_price": result.baseline_avg_price,
                    "avg_carbon": result.baseline_avg_carbon,
                },
                "savings": {
                    "cost": result.baseline_cost - result.optimized_cost,
                    "cost_percent": (
                        (result.baseline_cost - result.optimized_cost) / result.baseline_cost * 100
                        if result.baseline_cost > 0
                        else 0
                    ),
                    "carbon_kg": result.baseline_carbon_kg - result.optimized_carbon_kg,
                    "carbon_percent": (
                        (result.baseline_carbon_kg - result.optimized_carbon_kg)
                        / result.baseline_carbon_kg
                        * 100
                        if result.baseline_carbon_kg > 0
                        else 0
                    ),
                },
            },
        }
