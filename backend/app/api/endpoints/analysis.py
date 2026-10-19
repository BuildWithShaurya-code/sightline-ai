"""
SightLine AI - Analysis & Inference Job Endpoints
Handles persistent job initiation (202 Accepted), polling, and cancellation.
Runs inference jobs through a controlled background worker.
"""

from datetime import datetime
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status

from ...core.auth import AuthenticatedUser, get_current_user
from ...core.errors import NotFoundError, ValidationError, ServiceUnavailableError
from ...db.database import DatabaseManager
from ...schemas.analysis import (
    AnalysisJobResponse,
    AnalysisStartRequest,
    AnalysisStartResponse,
    JobCancelResponse,
    JobStatus,
    StructuredJobError,
)

logger = logging.getLogger("sightline.api.analysis")
router = APIRouter(prefix="/analysis", tags=["Analysis Jobs"])

db_manager = DatabaseManager.get_instance()


@router.post(
    "/start",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start neural analysis job on surveillance video",
    description="Registers persistent analysis job for specified video source. Returns 202 Accepted with jobId immediately.",
)
async def start_analysis(
    payload: AnalysisStartRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
) -> AnalysisStartResponse:
    """
    Submits analysis request.
    Validates source ownership, validates targets, registers persistent job,
    and launches background worker processing.
    """
    effective_idempotency = idempotency_key or x_idempotency_key

    # 1. Verify source ownership
    source = db_manager.get_source(payload.sourceId, current_user.id)
    if not source:
        raise NotFoundError("VideoSource", payload.sourceId)

    if source.get("status") != "ready":
        raise ValidationError(
            f"Source '{payload.sourceId}' is not ready for analysis (status: {source.get('status')})."
        )

    runner = getattr(request.app.state, "job_runner", None)
    if runner is None or not runner.ready:
        raise ServiceUnavailableError("Analysis worker is unavailable. Please retry shortly.")

    # 2. Register job with optional idempotency protection
    job_record = db_manager.create_analysis_job(
        user_id=current_user.id,
        source_id=payload.sourceId,
        targets=payload.targets,
        confidence_threshold=payload.confidence_threshold,
        sample_rate_sec=payload.sample_rate_sec,
        idempotency_key=effective_idempotency,
        max_pending=runner.settings.max_pending_jobs,
        max_pending_per_user=runner.settings.max_pending_jobs_per_user,
    )

    job_id = job_record["id"]

    # The persistent queue is scanned at startup and after submissions.
    runner.wake()

    return AnalysisStartResponse(jobId=job_id)


@router.get(
    "/jobs/{id}",
    response_model=AnalysisJobResponse,
    summary="Poll status and progress of an analysis job",
    description="Returns lifecycle status, 0-100 progress percentage, error details, and resulting incident ID when completed.",
)
async def get_job_status(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AnalysisJobResponse:
    """
    Retrieves job state for verified owner.
    Rejects cross-user inspection.
    """
    job = db_manager.get_job(id)
    if not job or job.get("user_id") != current_user.id:
        raise NotFoundError("AnalysisJob", id)

    error_details = None
    if job.get("error_details"):
        try:
            details_dict = json.loads(job["error_details"]) if isinstance(job["error_details"], str) else job["error_details"]
            error_details = StructuredJobError(
                error_code="ANALYSIS_FAILURE",
                message=job.get("error_message") or "Analysis failed",
                details=details_dict,
            )
        except Exception:
            pass

    created_at = None
    if job.get("created_at"):
        try:
            created_at = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    started_at = None
    if job.get("started_at"):
        try:
            started_at = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    finished_at = None
    if job.get("completed_at"):
        try:
            finished_at = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    return AnalysisJobResponse(
        id=job["id"],
        status=JobStatus(job["status"]),
        progress=job.get("progress"),
        incidentId=job.get("incident_id"),
        error=job.get("error_message"),
        error_details=error_details,
        source_id=job.get("source_id"),
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
    )


@router.post(
    "/jobs/{id}/cancel",
    response_model=JobCancelResponse,
    summary="Cancel a queued or running analysis job",
    description="Requests cancellation of analysis job. Cancels queued jobs immediately, or signals running worker to stop.",
)
async def cancel_job(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> JobCancelResponse:
    """
    Handles cancellation requests safely.
    Queued jobs transition immediately; active jobs receive a cancellation signal checked between frames.
    """
    success, reason = db_manager.request_job_cancellation(id, current_user.id)
    if not success and reason == "not_found":
        raise NotFoundError("AnalysisJob", id)

    job = db_manager.get_job(id)
    if not job:
        raise NotFoundError("AnalysisJob", id)

    status_enum = JobStatus(job["status"])
    is_requested = bool(job.get("cancellation_requested"))

    msg = "Job cancellation request accepted."
    if status_enum == JobStatus.CANCELLED:
        msg = "Job has been cancelled."
    elif not success:
        msg = f"Job could not be cancelled: {reason}."

    return JobCancelResponse(
        jobId=id,
        status=status_enum,
        cancellation_requested=is_requested,
        message=msg,
    )
