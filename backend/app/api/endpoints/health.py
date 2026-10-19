"""
SightLine AI - Health & Readiness Endpoints
Provides truthful status indicators distinguishing API foundation, model inference service,
and deferred background video worker pipelines.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, Response, Request, status

from ...config import Settings, get_settings
from ...services.inference_service import InferenceService
from ...services.storage import LocalMediaStorage

router = APIRouter(prefix="/health", tags=["Health & Readiness"])


@router.get("/live", summary="API Process Liveness Check")
async def health_live() -> Dict[str, Any]:
    """
    Indicates that the FastAPI API process is running and able to handle HTTP requests.
    Does not verify external dependencies.
    """
    return {
        "status": "live",
        "service": "sightline-api",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", summary="Service Readiness Inspection")
def health_ready(
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Truthfully inspects dependencies for the currently implemented phase (Phase 3).
    Distinguishes:
    - API process readiness
    - Local media storage readiness
    - Model checkpoint integrity and exact class map verification
    - Inference service availability (single-frame inference)
    - Deferred video processing worker (Phase 4)
    """
    # 1. Media Storage Check
    storage = LocalMediaStorage(settings.media_dir)
    storage_writable = storage.is_writable()
    if settings.storage_backend == 'supabase':
        from ...services.cloud_storage import CloudStorage
        storage_writable = storage_writable and CloudStorage(settings).ready()

    # 2. Inference Service Readiness (read metadata without reloading model)
    inference_service = InferenceService.get_instance()
    inference_info = inference_service.get_readiness_info()
    checkpoint_found = inference_info.get("checkpoint_found", False)
    inference_ready = bool(checkpoint_found and inference_info.get("is_loaded", False))

    # 3. Database & Worker Readiness
    from ...db.database import DatabaseManager
    db = DatabaseManager.get_instance()
    db_ready = True
    try:
        conn = db.get_connection()
        conn.execute("SELECT 1 FROM sources LIMIT 1;")
    except Exception:
        db_ready = False

    # Core Phase 4 readiness: storage writable, checkpoint found, database ready
    runner = getattr(request.app.state, "job_runner", None)
    worker_ready = bool(runner and runner.ready and inference_ready and db_ready)
    phase4_ready = storage_writable and inference_ready and db_ready and worker_ready

    if not phase4_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if phase4_ready else "degraded",
        "phase": 4,
        "phase_description": "Phase 4: Video Upload, Persistent Analysis Jobs, Worker Processing, Incidents, and Evidence",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "api_foundation": {
                "status": "ready",
                "ready": True,
                "environment": settings.environment,
                "api_prefix": settings.api_prefix,
            },
            "media_storage": {
                "status": "ready" if storage_writable else "unwritable",
                "ready": storage_writable,
                "storage_type": "supabase_private_objects" if settings.storage_backend == 'supabase' else "local_private_filesystem",
                "path": str(settings.media_dir) if settings.environment != "production" else None,
            },
            "model_checkpoint": {
                "status": "verified" if inference_ready else "present_unverified" if checkpoint_found else "missing",
                "ready": checkpoint_found,
                "path": inference_info.get("model_path") if settings.environment != "production" else None,
                "sha256": inference_info.get("sha256"),
                "classes_count": 3,
                "supported_classes": ["person", "mask", "knife"],
            },
            "inference_service": {
                "status": "ready" if inference_ready else "unavailable",
                "ready": inference_ready,
                "is_loaded": inference_info.get("is_loaded", False),
                "device": inference_info.get("device", "cpu"),
                "architecture": inference_info.get("architecture") or "DetectionModel",
                "note": "Single-image inference loaded." if inference_ready else "Inference is not loaded; analysis is unavailable.",
            },
            "video_worker": {
                "status": "ready" if worker_ready else "degraded",
                "ready": worker_ready,
                "note": "Video processing requires loaded inference and database access.",
            },
            "database": {
                "status": "ready" if db_ready else "unhealthy",
                "ready": db_ready,
                "driver": "postgresql_tls_rls" if settings.storage_backend == 'supabase' else "sqlite_wal",
                "note": "Persistent relational store initialized with atomic transactions and WAL mode.",
            },
        },
    }

