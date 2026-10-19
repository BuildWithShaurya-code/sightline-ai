"""
SightLine AI - Authenticated Single-Image Inference Route
Endpoint: POST /api/v1/inference/image
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from ...config import get_settings
from ...core.auth import AuthenticatedUser, get_current_user
from ...core.errors import ValidationError
from ...schemas.inference import InferenceResponse
from ...services.inference_service import InferenceService


router = APIRouter(prefix="/inference", tags=["Inference"])

_inference_semaphore: Optional[asyncio.Semaphore] = None


def get_inference_semaphore() -> asyncio.Semaphore:
    global _inference_semaphore
    if _inference_semaphore is None:
        settings = get_settings()
        _inference_semaphore = asyncio.Semaphore(settings.max_concurrent_inferences)
    return _inference_semaphore


@router.post(
    "/image",
    response_model=InferenceResponse,
    summary="Execute neural detection on a single uploaded image",
    description="Protected endpoint performing YOLOv11n detection on an uploaded surveillance frame.",
)
async def infer_image(
    request: Request,
    image: UploadFile = File(..., description="Image file to analyze (JPEG, PNG, WebP)"),
    targets: Optional[str] = Form(
        None,
        description="Comma-separated target classes to filter by (subset of 'person', 'mask', 'knife')",
    ),
    confidence_threshold: Optional[float] = Form(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score threshold (default: 0.25)",
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
) -> InferenceResponse:
    """
    Executes neural model detection on a single frame.
    Requires authenticated operator bearer token.
    """
    request_id = getattr(request.state, "request_id", None)

    # Read image bytes
    try:
        image_bytes = await image.read()
    except Exception as e:
        raise ValidationError(f"Failed to read image stream: {str(e)}")

    service = InferenceService.get_instance()

    # Bound concurrency via Semaphore
    async with semaphore:
        response = await service.infer_image_async(
            image_bytes=image_bytes,
            targets=targets,
            confidence_threshold=confidence_threshold,
            request_id=request_id,
        )

    return response
