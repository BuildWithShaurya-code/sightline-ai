"""
SightLine AI - Incident & Evidence Schemas
Distinguishes raw neural model detections from human operator review & incident status.
Excludes UI presentation styling (colors, CSS classes) from database persistence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from .detection import DetectionSchema


class IncidentStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FrameSchema(BaseModel):
    id: str = Field(..., description="Unique frame identifier (matches Frame.id)")
    timeSeconds: float = Field(..., ge=0.0, description="Media timestamp in seconds")
    imageDataUrl: str = Field(..., description="JPEG keyframe base64 or storage URL reference")


class IncidentSchema(BaseModel):
    id: str = Field(..., min_length=1, description="Incident identifier (e.g. 'INC-2026-001')")
    sourceId: str = Field(..., min_length=1, description="Media source identifier")
    createdAt: str = Field(
        ...,
        description="ISO 8601 UTC timestamp string conforming to frontend isValidIncident()",
    )
    status: IncidentStatus = Field(
        default=IncidentStatus.UNREVIEWED,
        description="Review lifecycle state ('unreviewed' | 'confirmed' | 'dismissed')",
    )
    frames: List[FrameSchema] = Field(
        default_factory=list,
        description="Keyframe snapshots associated with this threat event",
    )
    detections: List[DetectionSchema] = Field(
        default_factory=list,
        description="Model detections linked to this incident",
    )
    responseStatus: str = "Not contacted"
    reason: Optional[str] = None
    dispatchId: Optional[str] = Field(None, description="Linked dispatch transmission ID if sent")
    title: Optional[str] = Field(None, description="Descriptive headline for incident card")
    channel: Optional[str] = Field(None, description="Camera or channel tag (e.g. 'CAM-04 // NORTH GATE')")
    zone: Optional[str] = Field(None, description="Security zone designation (e.g. 'Zone B // Loading Dock')")
    durationSeconds: Optional[float] = Field(None, ge=0.0, description="Video duration in seconds")
    thumbnail: Optional[str] = Field(None, description="Thumbnail data URL or image reference")
    severity: Optional[IncidentSeverity] = Field(
        None,
        description="Evaluated security threat severity (low/medium/high/critical)",
    )
    review_reason: Optional[str] = Field(
        None,
        description="Operator justification for confirmation or dismissal",
    )
    reviewer_id: Optional[str] = Field(
        None,
        description="Operator badge ID who conducted threat review",
    )
    reviewed_at: Optional[str] = Field(
        None,
        description="ISO 8601 UTC timestamp of review decision",
    )

    @field_validator("createdAt")
    @classmethod
    def validate_created_at_iso(cls, v: str) -> str:
        try:
            # Must parse as valid ISO date
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"createdAt must be a valid ISO 8601 date string, got: '{v}'")
        return v


class IncidentReviewRequest(BaseModel):
    status: IncidentStatus = Field(
        ...,
        description="New decision status: 'confirmed' or 'dismissed'",
    )
    reason: Optional[str] = Field(
        None,
        description="Operator note detailing verification rationale",
    )
