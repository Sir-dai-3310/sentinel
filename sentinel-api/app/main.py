"""Sentinel API - FastAPI backend."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import analysis, rules, health, stats, settings, tenants
from app.security import SecurityHeadersMiddleware, RateLimitMiddleware
from app.websocket import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("🚀 Sentinel API starting...")
    yield
    # Shutdown
    print("🛑 Sentinel API shutting down...")


app = FastAPI(
    title="Sentinel API",
    description="AI-powered security log analysis platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Prometheus metrics instrumentation
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
    inprogress_name="sentinel_requests_inprogress",
    inprogress_labels=True,
)
instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting middleware (100 requests per 60 seconds per IP)
rate_limit = int(os.getenv("RATE_LIMIT", "100"))
rate_window = int(os.getenv("RATE_WINDOW", "60"))
app.add_middleware(RateLimitMiddleware, rate=rate_limit, per=rate_window)

# CORS - Restrict in production
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
if os.getenv("ENVIRONMENT") == "production" and "*" in allowed_origins:
    raise ValueError("CORS_ORIGINS cannot be '*' in production")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(rules.router, prefix="/api/v1", tags=["rules"])
app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])
app.include_router(tenants.router, prefix="/api/v1", tags=["tenants"])

# WebSocket endpoint
app.add_api_websocket_route("/ws/analysis", manager.manager.websocket_endpoint)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )
