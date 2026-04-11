"""
Historical optimization tracking and ROI reporting endpoints.

Provides REST API access to historical optimization data for:
- ROI reporting and analytics
- Trend analysis across time and regions
- Audit trails for compliance
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from arboric.api.dependencies import get_arboric_config
from arboric.api.utils import create_api_response
from arboric.core.config import ArboricConfig
from arboric.core.history import HistoryStore

router = APIRouter()


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=500, description="Max results"),
    since_days: int | None = Query(30, description="Days to look back (None = all time)"),
    region: str | None = Query(None, description="Filter by region (eastus, westus2, etc)"),
    config: ArboricConfig = Depends(get_arboric_config),
):
    """
    Get historical optimization runs.

    Returns list of past optimizations with cost/carbon savings, newest first.

    Args:
        limit: Max number of results (1-500, default 20)
        since_days: Include only runs from last N days (None = all time, default 30)
        region: Filter by region (optional)

    Returns:
        List of optimization runs with metrics
    """
    store = HistoryStore(Path(config.history.db_path).expanduser())
    runs = store.query(limit=limit, since_days=since_days, region=region)

    data = {
        "runs": runs,
        "count": len(runs),
        "filters": {
            "limit": limit,
            "since_days": since_days,
            "region": region,
        },
    }

    return create_api_response("history", data)


@router.get("/insights")
async def get_insights(
    since_days: int | None = Query(30, description="Days to look back (None = all time)"),
    region: str | None = Query(None, description="Filter by region (optional)"),
    config: ArboricConfig = Depends(get_arboric_config),
):
    """
    Get ROI summary statistics and insights.

    Returns aggregated metrics: total jobs, cost savings, carbon avoided,
    best performing region, and most optimized workload.

    Args:
        since_days: Include only runs from last N days (None = all time, default 30)
        region: Filter by region (optional)

    Returns:
        Aggregated ROI metrics and insights
    """
    store = HistoryStore(Path(config.history.db_path).expanduser())
    agg = store.aggregate(since_days=since_days, region=region)

    data = {
        "period_days": since_days,
        "region_filter": region,
        **agg,  # Flatten aggregation results
    }

    return create_api_response("insights", data)
