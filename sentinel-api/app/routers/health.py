"""Health check endpoint."""

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


async def database_is_ready() -> bool:
    try:
        timeout = float(os.getenv("HEALTHCHECK_DB_TIMEOUT", "2"))
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _health_response(database_ready: bool, include_database: bool) -> JSONResponse:
    services = {"api": "up"}
    if include_database:
        services["database"] = "up" if database_ready else "down"
    return JSONResponse(
        status_code=200 if database_ready or not include_database else 503,
        content={
            "status": "healthy" if database_ready or not include_database else "unhealthy",
            "version": "1.2.0",
            "services": services,
        },
    )


@router.get("/live")
async def liveness_check() -> JSONResponse:
    return _health_response(True, include_database=False)


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    return _health_response(await database_is_ready(), include_database=True)


@router.get("/health")
async def health_check() -> JSONResponse:
    return await readiness_check()
