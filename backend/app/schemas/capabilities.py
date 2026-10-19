"""
SightLine AI - Model Capabilities Schemas
Defines supported classes, thresholds, and inspection metadata for the neural detection pipeline.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class ModelCapabilitiesResponse(BaseModel):
    model_id: str = Field(
        default="sightline-yolo11n-v1",
        description="Unique identifier and revision of the deployed fine-tuned model",
    )
    architecture: str = Field(
        default="YOLO11n DetectionModel",
        description="Neural network architecture type",
    )
    framework: str = Field(
        default="PyTorch 2.14.1 / Ultralytics 8.4.135",
        description="Machine learning framework environment",
    )
    supported_classes: List[str] = Field(
        default=["person", "mask", "knife"],
        description="Exclusively supported detection target classes. Does not include gun or motion.",
    )
    class_map: Dict[int, str] = Field(
        default={0: "person", 1: "mask", 2: "knife"},
        description="Exact numeric index to class name mapping in checkpoint",
    )
    default_confidence_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Recommended default inference confidence threshold",
    )
    recommended_sample_rate_sec: float = Field(
        default=0.5,
        ge=0.1,
        le=5.0,
        description="Default frame sampling rate for video inspection in seconds",
    )
    readiness: Dict[str, Any] = Field(
        default_factory=dict,
        description="Model environment verification and compatibility state",
    )
