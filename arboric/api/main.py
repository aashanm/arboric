"""
Arboric REST API Server

FastAPI application providing HTTP endpoints for workload optimization.
"""

import logging
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from arboric.api.routes import config, fleet, forecast, history, optimize, receipt, status

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Arboric API",
    description="""
# Arboric API

Intelligent workload scheduling for cost and carbon optimization.

## Features

- **Single Workload Optimization**: Optimize individual workloads for cost and carbon efficiency
- **Fleet Optimization**: Optimize multiple workloads together
- **Grid Forecasting**: Access electricity grid forecasts with price and carbon intensity data
- **System Status**: Monitor API health and configuration

## Authentication

Currently no authentication required. This will be added in future versions for production deployments.

## Rate Limiting

No rate limiting currently enforced.
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Arboric Team", "email": "aashan5050@gmail.com"},
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

# Add CORS middleware (allow all origins initially)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(optimize.router, prefix="/api/v1", tags=["Optimization"])
app.include_router(receipt.router, prefix="/api/v1", tags=["Receipts"])
app.include_router(fleet.router, prefix="/api/v1/fleet", tags=["Fleet"])
app.include_router(forecast.router, prefix="/api/v1", tags=["Forecast"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(config.router, prefix="/api/v1", tags=["Configuration"])
app.include_router(history.router, prefix="/api/v1", tags=["History"])

# Conditionally load cloud routes if arboric-cloud is installed
try:
    from arboric_cloud.api.routes import auth as auth_route
    from arboric_cloud.api.routes import dashboard as dashboard_route
    from arboric_cloud.api.routes import jobs, receipts_ext, signals
    from arboric_cloud.scheduler.receipt_builder import build_and_save_receipt, store_forecast
    from arboric_cloud.scheduler.store import init_db, list_jobs
    from arboric_cloud.signals.carbon import build_48h_forecast_df

    app.include_router(jobs.router, prefix="/api/v1", tags=["Scheduler"])
    app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
    app.include_router(receipts_ext.router, prefix="/api/v1/receipts", tags=["Receipts"])
    app.include_router(auth_route.router, tags=["Auth"])
    app.include_router(dashboard_route.router, tags=["Dashboard"])

    @app.on_event("startup")
    async def _start_recurrence_scheduler() -> None:
        """Start APScheduler recurring job service."""
        try:
            from arboric_cloud.scheduler.recurrence import init_scheduler

            from arboric.api.dependencies import get_arboric_config

            config_obj = get_arboric_config()
            init_scheduler(config_obj)
        except Exception as exc:
            logger.warning("Recurring scheduler startup skipped: %s", exc)

    @app.on_event("shutdown")
    async def _stop_recurrence_scheduler() -> None:
        """Shut down APScheduler gracefully."""
        try:
            from arboric_cloud.scheduler.recurrence import shutdown

            shutdown()
        except Exception:
            pass

    @app.on_event("startup")
    async def _repair_missing_receipts() -> None:
        """Auto-regenerate receipts for COMPLETE jobs that are missing a PDF."""
        try:
            from arboric.api.dependencies import get_arboric_config

            init_db()
            config_obj = get_arboric_config()
            jobs_list = list_jobs(limit=200)
            missing = [
                j for j in jobs_list if j.get("status") == "COMPLETE" and not j.get("receipt_path")
            ]
            if not missing:
                return
            logger.info("Repairing %d job(s) missing receipts on startup", len(missing))
            for job in missing:
                try:
                    region = job.get("optimal_region") or "northeurope"
                    df = build_48h_forecast_df(region, config_obj)
                    store_forecast(job["id"], df)
                    build_and_save_receipt(job["id"], config_obj)
                    logger.info("Repaired receipt for job %s", job["id"])
                except Exception as exc:
                    logger.warning("Could not repair receipt for job %s: %s", job["id"], exc)
        except Exception as exc:
            logger.warning("Startup receipt repair skipped: %s", exc)

except ImportError:
    logger.debug("arboric-cloud not installed — scheduler, signals, and dashboard routes disabled")


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    API root endpoint.

    Returns basic information about the API including links to documentation.
    """
    return {
        "name": "Arboric API",
        "version": "0.1.0",
        "description": "Intelligent workload scheduling for cost and carbon optimization",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/api/v1/health",
    }


# Health check endpoint
@app.get("/api/v1/health", tags=["Health"])
async def health():
    """
    Health check endpoint.

    Simple endpoint for load balancers and monitoring systems to check if the API is responsive.
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# Exception handlers
@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle FastAPI request validation errors.

    Converts FastAPI validation errors into a structured JSON response
    with field-level error details.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in exc.errors()
            ],
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle Pydantic validation errors.

    Converts Pydantic validation errors into a structured JSON response
    with field-level error details.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in exc.errors()
            ],
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """
    Handle business logic errors.

    Converts ValueError exceptions (used for business logic validation)
    into structured error responses.
    """
    return JSONResponse(
        status_code=400,
        content={
            "error": "ValueError",
            "message": str(exc),
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected errors.

    Catches any unexpected exceptions and returns a generic error response
    to avoid leaking internal details.
    """
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path),
        },
    )
