"""
SightLine AI - Main FastAPI Application
Entrypoint for the SightLine physical threat detection backend service.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import os
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.router import api_router
from .config import Settings, get_settings
from .core.errors import (
    SightLineError,
    sightline_error_handler,
    starlette_http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from .core.logging import setup_logging
from .services.model_checker import ModelChecker
from .services.storage import LocalMediaStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager handling application startup and graceful shutdown."""
    settings = get_settings()
    logger = setup_logging(settings.log_level)
    import logging
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logger.info("Initializing SightLine AI Backend Service [Environment: %s]", settings.environment)
    logger.info("API Prefix configured as: %s", settings.api_prefix)

    # 1. Initialize local media directory
    storage = LocalMediaStorage(settings.media_dir)
    if storage.is_writable():
        logger.info("Local media storage validated and writable at: %s", settings.media_dir)
    else:
        logger.warning("Local media storage at %s is NOT writable!", settings.media_dir)

    # 2. Initialize and verify neural model checkpoint
    from .services.inference_service import InferenceService
    service = None
    try:
        if settings.storage_backend == 'supabase':
            from .services.cloud_storage import hydrate_model
            hydrate_model(settings)
        service = InferenceService.get_instance()
        service.load_and_verify_model()
        readiness = service.get_readiness_info()
        logger.info(
            "Neural Inference Service initialized on %s: %s (%d classes: %s)",
            readiness.get("device"),
            readiness.get("architecture"),
            len(readiness.get("class_map", {})),
            list(readiness.get("class_map", {}).values()),
        )
    except Exception as e:
        logger.warning("Neural model initialization note: %s", e)

    from .db.database import DatabaseManager
    from .services.job_runner import JobRunner
    runner = None
    if service is not None and service.get_readiness_info().get("is_loaded"):
        if settings.storage_backend == 'supabase':
            from .cloud_worker import CloudRunnerProxy
            runner = CloudRunnerProxy(DatabaseManager.get_instance(), settings)
        else:
            runner = JobRunner(DatabaseManager.get_instance(), settings, service)
            runner.start()
    app.state.job_runner = runner
    try:
        yield
    finally:
        worker_stopped = runner.close() if runner is not None else True
        if service is not None and worker_stopped:
            service.cleanup()
    logger.info("SightLine AI Backend Service shutting down gracefully.")



def create_app() -> FastAPI:
    settings = get_settings()
    if os.getenv("VERCEL") == "1" and settings.storage_backend != 'supabase':
        raise RuntimeError("The local SQLite/media backend cannot run safely on Vercel. Configure durable cloud persistence and a durable worker before deploying this API.")

    app = FastAPI(
        title="SightLine AI Backend Service",
        description=(
            "Tactical Physical Threat Detection API. "
            "Phase 1 foundation: API contracts, health, readiness, and model capabilities. "
            "Heavy continuous inference and database persistence are scheduled for Phase 2."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 1. Request Correlation ID & Timing Middleware
    @app.middleware("http")
    async def request_correlation_middleware(request: Request, call_next):
        from .core.identity import owner_id
        identity_token = owner_id.set(None)
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            owner_id.reset(identity_token)

        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store"
        if settings.environment == "production" and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time-Ms"] = str(process_time_ms)
        return response

    # 2. CORS Middleware - Narrowly scoped to authorized frontend origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )

    # 3. Exception Handlers
    app.add_exception_handler(SightLineError, sightline_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 4. Mount API Routes
    app.include_router(api_router, prefix=settings.api_prefix)

    # 5. Optional Same-Origin Production Frontend Serving
    dist_dir = Path(__file__).resolve().parent.parent.parent / "dist"
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app


app = create_app()
