"""
SightLine AI - Source Data Schemas
Covers media sources (uploaded surveillance videos and webcam sessions).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    UPLOADED_VIDEO = "uploaded_video"
    WEBCAM_SESSION = "webcam_session"
    CAMERA_SNAPSHOT = "camera_snapshot"


class SourceResponse(BaseModel):
    source_id: str = Field(..., description="Unique persistent identifier for the media source")
    owner_id: Optional[str] = Field(None, description="Operator identifier who registered the source")
    source_type: SourceType = Field(..., description="Type of surveillance input")
    original_filename: Optional[str] = Field(None, description="Client filename for uploaded videos")
    video_url: str = Field(..., description="Accessible URL/path to retrieve the source media")
    width: Optional[int] = Field(None, ge=1, description="Native horizontal pixel resolution")
    height: Optional[int] = Field(None, ge=1, description="Native vertical pixel resolution")
    duration_seconds: Optional[float] = Field(None, ge=0.0, description="Total media duration in seconds")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Payload size in bytes")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp",
    )
    processing_availability: str = Field(
        default="available",
        description="Availability status: 'available', 'archived', 'expired'",
    )


class VideoUploadResponse(BaseModel):
    """Payload returned by POST /api/v1/videos/upload matching frontend api.ts."""
    sourceId: str = Field(..., description="Standardized sourceId for subsequent analysis requests")
    videoUrl: str = Field(..., description="URL reference for playback in Detection Studio")
