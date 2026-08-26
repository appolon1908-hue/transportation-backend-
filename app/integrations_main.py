from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import SessionLocal
from app.integrations.api import router as integrations_router

app = FastAPI(
    title="Freight Platform Integration API",
    version=os.getenv("APP_VERSION", "0.3.0"),
    description="Signed webhooks, durable delivery, Odoo, n8n and provenance boundary.",
    docs_url=None if os.getenv("ENVIRONMENT", "development").lower() == "production" else "/docs",
    redoc_url=None,
)


@app.middleware("http")
async def correlation_and_security_headers(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or uuid4().hex
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": "HTTP_ERROR",
        "message": str(exc.detail),
    }
    detail.setdefault("correlation_id", getattr(request.state, "correlation_id", None))
    return JSONResponse(status_code=exc.status_code, content=detail, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "correlation_id": getattr(request.state, "correlation_id", None),
            "fields": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected integration error occurred.",
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )


@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "live", "service": "freight-platform-integrations"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            await db.execute(text("SELECT 1 FROM integration_connections LIMIT 1"))
        return {"status": "ready", "dependencies": {"database": "available"}}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependencies": {"database": "unavailable_or_unmigrated"}},
        )


@app.get("/health/version", tags=["health"])
async def health_version():
    return {
        "version": os.getenv("APP_VERSION", "0.3.0"),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "image_digest": os.getenv("IMAGE_DIGEST", "unknown"),
        "migration_head": os.getenv("MIGRATION_HEAD", "0003_integrations_durability"),
    }


app.include_router(integrations_router)
