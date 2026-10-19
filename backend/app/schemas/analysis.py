"""
SightLine AI - Analysis Request & Job Schemas
Covers neural inference requests, lifecycle status, progress metrics, and failure metadata.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

SUPPORTED_CLASSES = {"person", "mask", "knife"}


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisStartRequest(BaseModel):
    sourceId: str = Field(..., min_length=1, description="Identifier of the uploaded video source")
    targets: List[str] = Field(
        ...,
        min_length=1,
        description="List of target classes to monitor. Exclusively supports: 'person', 'mask', 'knife'",
    )
    confidence_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum detection confidence score threshold",
    )
    sample_rate_sec: float = Field(
        default=0.5,
        ge=0.1,
        le=5.0,
        description="Sampling frequency in seconds across video timeline",
    )

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, targets: List[str]) -> List[str]:
        if not targets:
            raise ValueError("At least one target class must be selected")
        invalid = [t for t in targets if t not in SUPPORTED_CLASSES]
        if invalid:
            raise ValueError(
                f"Unsupported detection target(s): {invalid}. "
                f"Model strictly supports: {sorted(list(SUPPORTED_CLASSES))}. "
                "Forbidden classes: gun, motion."
            )
        # Deduplicate while preserving order
        return list(dict.fromkeys(targets))


class AnalysisStartResponse(BaseModel):
    jobId: str = Field(..., description="Unique identifier for the initiated background inference job")


class StructuredJobError(BaseModel):
    error_code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AnalysisJobResponse(BaseModel):
    id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Current lifecycle state")
    progress: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Explicit progress percentage (integer 0 to 100)",
    )
    incidentId: Optional[str] = Field(
        None,
        description="Populated with created Incident ID upon successful completion",
    )
    error: Optional[str] = Field(
        None,
        description="Human-readable error description if status is failed",
    )
    error_details: Optional[StructuredJobError] = Field(
        None,
        description="Structured failure metadata for debugging",
    )
    source_id: Optional[str] = Field(None, description="Reference to source media being processed")
    created_at: Optional[datetime] = Field(None, description="UTC timestamp of job creation")
    started_at: Optional[datetime] = Field(None, description="UTC timestamp when processing began")
    finished_at: Optional[datetime] = Field(None, description="UTC timestamp when job reached terminal state")


class JobCancelResponse(BaseModel):
    jobId: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Lifecycle status following cancellation request")
    cancellation_requested: bool = Field(..., description="Indicates whether worker has received/flagged cancellation request")
    message: str = Field(..., description="Explanation of cancellation transition")

