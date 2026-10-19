"""
SightLine AI - Unified Schema Exports
"""

from .common import (
    ErrorResponse,
    ValidationErrorResponse,
    ValidationErrorDetail,
    PaginationMeta,
    PaginatedResponse,
)
from .capabilities import ModelCapabilitiesResponse
from .source import SourceType, SourceResponse, VideoUploadResponse
from .analysis import (
    JobStatus,
    AnalysisStartRequest,
    AnalysisStartResponse,
    AnalysisJobResponse,
    StructuredJobError,
)
from .detection import DetectionSchema, BoundingBoxDict, VALID_MODEL_CLASSES
from .incident import (
    IncidentStatus,
    IncidentSeverity,
    FrameSchema,
    IncidentSchema,
    IncidentReviewRequest,
)
from .dispatch import (
    DispatchStatus,
    DispatchNotificationChannel,
    DispatchSendRequest,
    DispatchCancelRequest,
    DispatchResponse,
    DispatchCancelResponse,
)

__all__ = [
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "PaginationMeta",
    "PaginatedResponse",
    "ModelCapabilitiesResponse",
    "SourceType",
    "SourceResponse",
    "VideoUploadResponse",
    "JobStatus",
    "AnalysisStartRequest",
    "AnalysisStartResponse",
    "AnalysisJobResponse",
    "StructuredJobError",
    "DetectionSchema",
    "BoundingBoxDict",
    "VALID_MODEL_CLASSES",
    "IncidentStatus",
    "IncidentSeverity",
    "FrameSchema",
    "IncidentSchema",
    "IncidentReviewRequest",
    "DispatchStatus",
    "DispatchNotificationChannel",
    "DispatchSendRequest",
    "DispatchCancelRequest",
    "DispatchResponse",
    "DispatchCancelResponse",
]
