"""
SightLine AI - Local Media Storage Service
Implements MediaStorageInterface for local development and private storage.
Provides path-traversal protection and disk write readiness verification.
"""

import os
from pathlib import Path
import uuid
from typing import Optional


class LocalMediaStorage:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary media subfolders if they do not exist."""
        subfolders = ["videos", "keyframes", "temp"]
        for sub in subfolders:
            folder = self.base_dir / sub
            folder.mkdir(parents=True, exist_ok=True)

    def is_writable(self) -> bool:
        """Verify that the media directory can be written to."""
        try:
            self._ensure_directories()
            test_file = self.base_dir / "temp" / f".health_check_{uuid.uuid4().hex}"
            test_file.write_bytes(b"health")
            if test_file.exists():
                test_file.unlink()
                return True
            return False
        except Exception:
            return False

    def save_media(self, content: bytes, filename: str, subfolder: str = "videos") -> str:
        """
        Saves content to disk in a collision-resistant path within base_dir.
        Returns relative storage path.
        """
        clean_ext = Path(filename).suffix.lower() or ".bin"
        unique_name = f"{uuid.uuid4().hex}{clean_ext}"
        target_file = (self.base_dir / subfolder / unique_name).resolve()
        # Check containment before creating directories, including sibling-prefix paths.
        if not target_file.is_relative_to(self.base_dir):
            raise ValueError("Target path escapes storage directory")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(content)
        return f"{subfolder}/{unique_name}"

    def get_media_path(self, relative_path: str) -> Path:
        """
        Resolves relative storage path and ensures it stays strictly within base_dir.
        """
        # Strip leading slashes to prevent root escapes
        clean_rel = relative_path.lstrip("/\\")
        resolved = (self.base_dir / clean_rel).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ValueError("Requested media path escapes storage directory")
        return resolved

    def delete_media(self, relative_path: str) -> bool:
        """Deletes media file if it exists."""
        try:
            target = self.get_media_path(relative_path)
            if target.exists() and target.is_file():
                target.unlink()
                return True
            return False
        except Exception:
            return False
