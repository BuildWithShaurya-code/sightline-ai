"""
SightLine AI - Inference Request & Response Schemas
Type-validated Pydantic schemas for single-frame neural detection and model evaluation.
"""

from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


SupportedClassId = Literal["person", "mask", "knife"]


class BoundingBoxObject(BaseModel):
    """Optional {x, y, w, h} box representation for contract compatibility."""
    x: float = Field(..., description="Top-left X coordinate in original frame pixels")
    y: float = Field(..., description="Top-left Y coordinate in original frame pixels")
    w: float = Field(..., description="Bounding box width in original frame pixels")
    h: float = Field(..., description="Bounding box height in original frame pixels")


class DetectionItem(BaseModel):
    """
    Standardized detection format aligned with SightLine AI frontend.
    box is strictly [x1, y1, x2, y2] in original image pixel coordinate space.
    """
    classId: SupportedClassId = Field(
        ...,
        description="Canonical class identifier string ('person' | 'mask' | 'knife')",
    )
    className: str = Field(
        ...,
        description="Display class name matching the canonical class",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Detection confidence score between 0.0 and 1.0",
    )
    box: Tuple[float, float, float, float] = Field(
        ...,
        description="Original pixel coordinates tuple: [x1, y1, x2, y2]",
    )
    box_object: Optional[BoundingBoxObject] = Field(
        default=None,
        description="Optional object representation {x, y, w, h}",
    )

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(float(v), 4)

    @field_validator("box")
    @classmethod
    def validate_box_order(cls, v: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        x1, y1, x2, y2 = v
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Invalid bounding box coordinates: x2 ({x2}) must be > x1 ({x1}) and y2 ({y2}) > y1 ({y1})")
        return (round(float(x1), 2), round(float(y1), 2), round(float(x2), 2), round(float(y2), 2))


class InferenceTimings(BaseModel):
    """Precise latency breakdown in milliseconds."""
    decode_ms: float = Field(..., ge=0.0, description="Image decoding time in ms")
    inference_ms: float = Field(..., ge=0.0, description="Raw model execution time in ms")
    serialization_ms: float = Field(..., ge=0.0, description="Postprocessing & tensor serialization in ms")
    total_ms: float = Field(..., ge=0.0, description="Total end-to-end request latency in ms")


class InferenceResponse(BaseModel):
    """
    Validated response payload for authenticated single-image inference.
    """
    request_id: Optional[str] = Field(default=None, description="Unique correlation request ID")
    model_version: str = Field(..., description="Checkpoint architecture and identifier")
    model_sha256: str = Field(..., description="Verified SHA256 checksum of loaded checkpoint")
    device: str = Field(..., description="Compute execution device (e.g. 'cpu', 'cuda')")
    original_width: int = Field(..., gt=0, description="Original image width in pixels")
    original_height: int = Field(..., gt=0, description="Original image height in pixels")
    targets: List[SupportedClassId] = Field(..., description="Monitored target classes evaluated")
    confidence_threshold: float = Field(..., ge=0.0, le=1.0, description="Effective detection confidence threshold")
    detections_count: int = Field(..., ge=0, description="Number of detected objects meeting threshold")
    detections: List[DetectionItem] = Field(default_factory=list, description="Validated detections list")
    timings: InferenceTimings = Field(..., description="Latency breakdown")
    timestamp: str = Field(..., description="UTC ISO-8601 execution timestamp")
