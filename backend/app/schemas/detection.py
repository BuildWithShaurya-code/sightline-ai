"""
SightLine AI - Detection Schema
Standardized representation of an object prediction emitted by the neural model.

Bounding Box Coordinate Convention:
- `box`: Tuple of four numeric pixel coordinates [x1, y1, x2, y2] referencing the original source frame.
  x1 = left, y1 = top, x2 = right, y2 = bottom (x1 <= x2 and y1 <= y2).
- Display scaling on frontend:
  When displaying bounding boxes over an HTML5 <video> or <canvas> rendered at dimensions (renderedW, renderedH):
    scaleX = renderedW / frame_width
    scaleY = renderedH / frame_height
    displayedX = x1 * scaleX
    displayedY = y1 * scaleY
    displayedWidth = (x2 - x1) * scaleX
    displayedHeight = (y2 - y1) * scaleY
"""

from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator

CLASS_NAME_TO_ID = {
    "person": 0,
    "mask": 1,
    "knife": 2,
}
VALID_MODEL_CLASSES = Literal["person", "mask", "knife"]


class BoundingBoxDict(BaseModel):
    x: float = Field(..., description="Top-left X pixel coordinate in original frame")
    y: float = Field(..., description="Top-left Y pixel coordinate in original frame")
    w: float = Field(..., ge=0.0, description="Bounding box pixel width")
    h: float = Field(..., ge=0.0, description="Bounding box pixel height")


class DetectionSchema(BaseModel):
    detection_id: Optional[str] = Field(
        None,
        description="Unique identifier for the detection record",
    )
    classId: VALID_MODEL_CLASSES = Field(
        ...,
        description="Standardized target class ('person' | 'mask' | 'knife')",
    )
    class_id_numeric: Optional[int] = Field(
        None,
        ge=0,
        le=2,
        description="Numeric index (0: person, 1: mask, 2: knife)",
    )
    className: Optional[str] = Field(
        None,
        description="Capitalized display label (e.g. 'Person', 'Mask', 'Knife')",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Numeric model confidence strictly between 0.0 and 1.0. Display strings (e.g. '89%') forbidden.",
    )
    box: Tuple[float, float, float, float] = Field(
        ...,
        description="Raw pixel bounding box tuple [x1, y1, x2, y2] in original frame coordinates",
    )
    box_dict: Optional[BoundingBoxDict] = Field(
        None,
        description="Optional object representation {x, y, w, h} matching model_contract.json",
    )
    frame_width: Optional[int] = Field(
        None,
        ge=1,
        description="Source frame horizontal pixel resolution",
    )
    frame_height: Optional[int] = Field(
        None,
        ge=1,
        description="Source frame vertical pixel resolution",
    )
    frame_index: Optional[int] = Field(
        None,
        ge=0,
        description="Zero-indexed sequence index of the sampled video frame",
    )
    evidence_id: Optional[str] = Field(
        None,
        description="Evidence frame ID this prediction belongs to",
    )
    video_offset_seconds: Optional[float] = Field(
        None,
        ge=0.0,
        description="Timestamp of the source frame in seconds",
    )
    video_offset_ms: Optional[int] = Field(
        None,
        ge=0,
        description="Offset in milliseconds from start of video",
    )
    model_version: Optional[str] = Field(
        default="sightline-yolo11n-v1",
        description="Model checkpoint identifier generating this prediction",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence_type(cls, v: Any) -> float:
        if isinstance(v, str):
            # Prohibit display strings like "88%" or "MASK: 92%"
            raise ValueError(
                f"Confidence must be a numeric float between 0.0 and 1.0, not a display string ('{v}')."
            )
        try:
            val = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"Confidence value {v} cannot be converted to float.")
        if val < 0.0 or val > 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, received: {val}")
        return val

    @field_validator("box", mode="before")
    @classmethod
    def validate_box_coordinates(
        cls, v: Any
    ) -> Tuple[float, float, float, float]:
        if isinstance(v, (list, tuple)):
            if len(v) != 4:
                raise ValueError(f"Bounding box must contain exactly 4 coordinates [x1, y1, x2, y2], got {len(v)}")
            try:
                coords = tuple(float(c) for c in v)
            except (TypeError, ValueError):
                raise ValueError(f"Bounding box coordinates must be numeric, got {v}")
            x1, y1, x2, y2 = coords
            if x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
                raise ValueError(f"Bounding box coordinates must be non-negative: {coords}")
            if x2 < x1:
                raise ValueError(f"Malformed bounding box: x2 ({x2}) cannot be less than x1 ({x1})")
            if y2 < y1:
                raise ValueError(f"Malformed bounding box: y2 ({y2}) cannot be less than y1 ({y1})")
            return coords
        raise ValueError(f"Bounding box must be a list or tuple of 4 numbers, got {type(v)}")

    @model_validator(mode="after")
    def populate_derived_fields(self) -> "DetectionSchema":
        if self.class_id_numeric is None:
            self.class_id_numeric = CLASS_NAME_TO_ID.get(self.classId, 0)
        if not self.className:
            self.className = self.classId.capitalize()
        return self
