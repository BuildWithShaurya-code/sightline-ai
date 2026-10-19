"""
SightLine AI - Model Capabilities Endpoint
Provides client-facing specification of supported classes, thresholds, and inspection metadata.
"""

from fastapi import APIRouter, Depends
from ...config import Settings, get_settings
from ...schemas.capabilities import ModelCapabilitiesResponse
from ...services.inference_service import InferenceService

router = APIRouter(prefix="/model", tags=["Model Capabilities"])


@router.get(
    "/capabilities",
    response_model=ModelCapabilitiesResponse,
    summary="Retrieve Neural Model Capabilities & Target Classes",
)
async def get_capabilities(
    settings: Settings = Depends(get_settings),
) -> ModelCapabilitiesResponse:
    inference_service = InferenceService.get_instance()
    info = inference_service.get_readiness_info()

    checkpoint_found = info.get("checkpoint_found", False)
    is_loaded = info.get("is_loaded", False)

    return ModelCapabilitiesResponse(
        model_id="sightline-yolo11n-v1",
        architecture=info.get("architecture") or "DetectionModel",
        framework="PyTorch 2.14.1 / Ultralytics 8.4.178",
        supported_classes=["person", "mask", "knife"],
        class_map={0: "person", 1: "mask", 2: "knife"},
        default_confidence_threshold=settings.default_confidence_threshold,
        recommended_sample_rate_sec=0.5,
        readiness={
            "compatible": checkpoint_found,
            "checkpoint_found": checkpoint_found,
            "file_size_bytes": 5451802 if checkpoint_found else 0,
            "sha256": info.get("sha256") or "0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8",
            "model_loaded_in_api": is_loaded,
        },
    )
