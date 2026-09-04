from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import router as core_router
from app.api_extended import router as extended_router
from app.config import get_settings
from app.db import SessionLocal

settings = get_settings()

app = FastAPI(
    title="Freight Platform API",
    version=os.getenv("APP_VERSION", "0.1.0"),
    description="Multi-tenant freight brokerage / 3PL API",
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or uuid4().hex
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
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
            "message": "An unexpected error occurred.",
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )


@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "live"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "dependencies": {"database": "unavailable"}})


@app.get("/health/version", tags=["health"])
async def health_version():
    return {
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "image_digest": os.getenv("IMAGE_DIGEST", "unknown"),
        "migration_head": os.getenv("MIGRATION_HEAD", "0001_foundation"),
    }


app.include_router(core_router)
app.include_router(extended_router)
