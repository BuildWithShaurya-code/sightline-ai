"""
SightLine AI - Shared Common Data Schemas
Standardized error responses, pagination metadata, and correlation models.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Machine-readable uppercase error code")
    message: str = Field(..., description="Human-readable explanation of the error")
    details: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual error details")
    request_id: Optional[str] = Field(None, description="Correlation request ID for tracking across services")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the error occurrence",
    )


class ValidationErrorDetail(BaseModel):
    location: str
    message: str


class ValidationErrorResponse(BaseModel):
    error: str = "VALIDATION_ERROR"
    message: str = "Request payload failed schema validation"
    details: Dict[str, str] = Field(default_factory=dict)
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaginationMeta(BaseModel):
    page: int = Field(1, ge=1, description="1-indexed current page number")
    page_size: int = Field(20, ge=1, le=100, description="Items returned per page")
    total_items: int = Field(..., ge=0, description="Total matching items across all pages")
    total_pages: int = Field(..., ge=0, description="Total number of available pages")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    pagination: PaginationMeta
