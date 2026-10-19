"""
SightLine AI - Video Processing & Storage Service
Handles streaming spooling, video container inspection, dimension and duration validation,
collision-resistant storage keys, and authorized playback access.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, Optional, Tuple
import uuid

import cv2
from fastapi import UploadFile

from ..config import get_settings
from ..core.errors import (
    NotFoundError,
    PayloadTooLargeError,
    ValidationError,
)
from ..db.database import DatabaseManager
from .storage import LocalMediaStorage

logger = logging.getLogger("sightline.video")

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


class VideoService:
    def __init__(self, db: Optional[DatabaseManager] = None, storage: Optional[LocalMediaStorage] = None):
        self.settings = get_settings()
        self.db = db or DatabaseManager.get_instance()
        self.storage = storage or LocalMediaStorage(self.settings.media_dir)

    async def process_and_store_upload(
        self,
        upload_file: UploadFile,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Streams uploaded video, validates decodability and constraints,
        stores in collision-safe storage, and creates database source record.
        """
        original_filename = upload_file.filename or "uploaded_video.mp4"
        clean_ext = Path(original_filename).suffix.lower()
        if clean_ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported video file extension '{clean_ext}'. Supported: {sorted(list(ALLOWED_EXTENSIONS))}."
            )

        # 1. Spool to a temporary file while enforcing max byte limit
        temp_dir = self.storage.base_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        spool_path = temp_dir / f"spool_{uuid.uuid4().hex}{clean_ext}"

        bytes_read = 0
        max_bytes = self.settings.max_upload_size_bytes

        try:
            with open(spool_path, "wb") as f_out:
                while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
                    bytes_read += len(chunk)
                    if bytes_read > max_bytes:
                        raise PayloadTooLargeError(
                            f"Uploaded file exceeds maximum size of {max_bytes} bytes ({max_bytes // (1024*1024)} MB).",
                            max_bytes=max_bytes,
                        )
                    f_out.write(chunk)

            if bytes_read == 0:
                raise ValidationError("Uploaded video file is empty (0 bytes).")

            # 2. Inspect video decodability and metadata using OpenCV
            cap = cv2.VideoCapture(str(spool_path))
            if not cap.isOpened():
                raise ValidationError("Failed to decode video container. File is corrupted or uses an unsupported codec.")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            if width <= 0 or height <= 0 or total_frames <= 0 or fps <= 0:
                raise ValidationError("Video file has invalid metadata or contains zero playable frames.")

            duration_seconds = round(total_frames / fps, 2)

            if duration_seconds > self.settings.max_media_duration_seconds:
                raise ValidationError(
                    f"Video duration ({duration_seconds}s) exceeds maximum allowed ({self.settings.max_media_duration_seconds}s)."
                )

            # 3. Move to permanent storage
            source_id = f"src_{uuid.uuid4().hex[:12]}"
            storage_key = f"{user_id}/{source_id}/{source_id}{clean_ext}"

            # Save in local storage videos directory
            target_storage_rel = f"videos/{source_id}{clean_ext}"
            target_full_path = self.storage.get_media_path(target_storage_rel)
            target_full_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(spool_path), str(target_full_path))

            # 4. Attempt database insertion (with compensation if failure occurs)
            source_record = {
                "id": source_id,
                "user_id": user_id,
                "source_type": "video_upload",
                "original_filename": original_filename,
                "storage_bucket": "source-videos",
                "storage_key": storage_key,
                "media_dimensions": {"width": width, "height": height},
                "duration_seconds": duration_seconds,
                "file_size_bytes": bytes_read,
                "status": "ready",
            }

            try:
                created = self.db.create_source(source_record)
            except Exception as db_exc:
                # Compensation: remove stored file if DB insertion failed
                if target_full_path.exists():
                    target_full_path.unlink()
                raise db_exc

            video_url = f"/api/v1/videos/{source_id}/playback"

            return {
                "sourceId": source_id,
                "videoUrl": video_url,
                "width": width,
                "height": height,
                "duration_seconds": duration_seconds,
                "file_size_bytes": bytes_read,
            }

        finally:
            # Clean up temporary spool file if it still exists
            if spool_path.exists():
                try:
                    spool_path.unlink()
                except Exception:
                    pass

    def get_authorized_playback_file(self, source_id: str, user_id: str) -> Tuple[Path, str]:
        """
        Verifies user ownership of source and returns local file path and mime-type.
        """
        source = self.db.get_source(source_id, user_id)
        if not source:
            raise NotFoundError("VideoSource", source_id)

        clean_ext = Path(source["original_filename"]).suffix.lower() or ".mp4"
        rel_path = f"videos/{source_id}{clean_ext}"
        full_path = self.storage.get_media_path(rel_path)

        if not full_path.exists() or not full_path.is_file():
            raise NotFoundError("VideoMediaFile", source_id)

        mime_type = "video/mp4"
        if clean_ext == ".webm":
            mime_type = "video/webm"
        elif clean_ext == ".mkv":
            mime_type = "video/x-matroska"

        return full_path, mime_type
