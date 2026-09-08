"""Main FastAPI Application Entrypoint

FastAPI gateway configuring routes, deterministic health probes,
safe global error handlers, and router mount points.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for Windows subprocess reloader
_root_dir = str(Path(__file__).resolve().parent.parent.parent)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config import get_settings
from backend.app.api.voice import router as voice_router
from backend.app.api.websocket import router as ws_router
from backend.app.models.schemas import HealthResponse, RootStatusResponse

app = FastAPI(
    title="Rime Voice AI Assistant with Interruption & Recovery",
    description="DataForge 2026 Rime Hackathon - Phase 14 Real-Time Full-Duplex WebSocket Layer",
    version="0.14.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware to allow browser frontend communication and exposed custom headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Session-ID",
        "X-Turn-ID",
        "X-User-Transcript",
        "X-Assistant-Response",
        "X-Final-Response",
        "X-LLM-Provider",
        "X-LLM-Model",
        "X-Provider",
        "X-Model-ID",
        "X-Speaker",
        "X-Audio-Format",
        "X-Audio-Bytes-Length",
        "X-Pipeline-Latency-Ms",
        "X-Search-Used",
        "X-Search-Sources",
    ],
)

# Mount API Routers
app.include_router(voice_router, prefix="/api")
app.include_router(ws_router, prefix="/api")


# Global Safe Error Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Clean JSON response for HTTP exceptions without exposing server stack traces."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Sanitized validation error response."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Request validation failed",
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Generic fallback error handler guaranteeing zero credential or internal trace leakage."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error occurred",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


# Core System Endpoints
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health Check",
    description="Deterministic health probe endpoint.",
)
def health_check():
    """Health check endpoint returning deterministic status."""
    return {"status": "ok"}


@app.get(
    "/",
    response_model=RootStatusResponse,
    tags=["System"],
    summary="Root Status",
    description="Returns high-level service status and configuration readiness without secrets.",
)
def root():
    """Root endpoint for status information."""
    settings = get_settings()
    return {
        "service": "Rime Voice AI Assistant",
        "status": "online",
        "phase": 14,
        "rime_configured": settings.is_rime_configured,
    }
