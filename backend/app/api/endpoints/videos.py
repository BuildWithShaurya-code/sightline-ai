"""
SightLine AI - Videos & Media Endpoints
Implements authenticated video upload (multipart stream/spooling),
container validation, metadata persistence, and authorized playback.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from ...core.auth import AuthenticatedUser, get_current_user
from ...core.errors import NotFoundError, ValidationError
from ...schemas.source import VideoUploadResponse
from ...services.video_service import VideoService

logger = logging.getLogger("sightline.api.videos")
router = APIRouter(prefix="/videos", tags=["Videos"])

video_service = VideoService()


class DirectUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


@router.post('/uploads', status_code=201)
def begin_direct_upload(payload: DirectUploadRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    from ...services.cloud_video import CloudVideoService
    return CloudVideoService().begin(current_user.id, payload.filename, payload.size)


@router.post('/uploads/{source_id}/complete', response_model=VideoUploadResponse)
def complete_direct_upload(source_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    from ...services.cloud_video import CloudVideoService
    return CloudVideoService().complete(current_user.id, source_id)


@router.post(
    "/upload",
    response_model=VideoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload surveillance video for neural analysis",
    description="Accepts multipart video bytes, spools to temporary storage, verifies decodability via OpenCV, and creates persistent source record.",
)
async def upload_video(
    video: UploadFile = File(..., description="SURVEILLANCE video file (mp4, avi, mov, mkv, webm)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> VideoUploadResponse:
    """
    Authenticated video upload handler.
    Strictly derives ownership from verified Supabase token.
    Enforces maximum file size, non-empty content, and decodability.
    """
    if video_service.settings.storage_backend == 'supabase':
        raise ValidationError('Use a direct private-storage upload on the cloud deployment.')
    logger.info("Video upload received for operator [%s], filename: %s", current_user.id, video.filename)
    result = await video_service.process_and_store_upload(video, current_user.id)
    return VideoUploadResponse(
        sourceId=result["sourceId"],
        videoUrl=result["videoUrl"],
    )


@router.get(
    "/{source_id}/playback",
    summary="Stream authorized source video playback",
    description="Returns video stream for an owned surveillance source. Rejects cross-owner access.",
)
async def get_video_playback(
    source_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Verifies user ownership before serving the video stream.
    """
    if video_service.settings.storage_backend == 'supabase':
        from ...services.cloud_video import CloudVideoService
        return RedirectResponse(CloudVideoService().playback(current_user.id, source_id), status_code=302)
    full_path, mime_type = video_service.get_authorized_playback_file(source_id, current_user.id)
    return FileResponse(
        path=full_path,
        media_type=mime_type,
        filename=full_path.name,
    )
