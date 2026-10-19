"""
SightLine AI - Reusable Neural Model Inference Service
Handles model lifecycle, checkpoint integrity, class mapping validation, warm-up,
thread-safe execution, coordinate-space preservation, and validated detection serialization.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import cv2
import numpy as np

from ..config import get_settings
from ..core.errors import (
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    ValidationError,
)
from ..schemas.inference import (
    BoundingBoxObject,
    DetectionItem,
    InferenceResponse,
    InferenceTimings,
    SupportedClassId,
)


logger = logging.getLogger("sightline.inference")

EXPECTED_SHA256 = "0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8"
EXPECTED_CLASS_MAP = {0: "person", 1: "mask", 2: "knife"}
SUPPORTED_TARGETS: Set[SupportedClassId] = {"person", "mask", "knife"}
FORBIDDEN_CLASSES: Set[str] = {"gun", "motion", "weapon", "fire"}


class InferenceService:
    """
    Production-grade inference service managing the YOLO detection model.
    Thread-safe and concurrency-bounded.
    """
    _instance: Optional["InferenceService"] = None
    _instance_lock = threading.Lock()

    def __init__(self, model_path: Optional[Path] = None, device: Optional[str] = None):
        self.settings = get_settings()
        self.model_path = Path(model_path or self.settings.model_path)
        self.device = device or self.settings.inference_device
        self._model = None
        self._model_lock = threading.Lock()
        self._is_initialized = False
        self._sha256: Optional[str] = None
        self._architecture: Optional[str] = None
        self._class_map: Dict[int, str] = {}
        self._warmup_time_ms: float = 0.0
        self._load_time_ms: float = 0.0

    @classmethod
    def get_instance(cls) -> "InferenceService":
        """Singleton accessor ensuring one persistent model in memory."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Testing utility to reset singleton state."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.cleanup()
                cls._instance = None

    def calculate_sha256(self, file_path: Path) -> str:
        """Calculates SHA-256 hash of checkpoint file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def load_and_verify_model(self) -> None:
        """
        Loads the fine-tuned checkpoint, enforces strict checksum,
        and validates exact numeric class mapping.
        """
        with self._model_lock:
            if self._is_initialized and self._model is not None:
                return

            start_load = time.perf_counter()

            # 1. Path existence verification
            if not self.model_path.exists() or not self.model_path.is_file():
                raise NotFoundError("ModelCheckpoint", str(self.model_path))

            # 2. Checksum verification
            computed_sha = self.calculate_sha256(self.model_path)
            self._sha256 = computed_sha
            if computed_sha != EXPECTED_SHA256:
                raise ServiceUnavailableError(
                    f"Model checkpoint integrity check failed. Expected SHA-256 '{EXPECTED_SHA256}', got '{computed_sha}'."
                )

            # 3. Model instantiation via Ultralytics
            try:
                from ultralytics import YOLO
                model = YOLO(str(self.model_path))
            except Exception as e:
                raise ServiceUnavailableError(f"Failed to load YOLO model runtime: {str(e)}")

            # 4. Class map verification
            raw_names = getattr(model, "names", {})
            class_map = {int(k): str(v).lower() for k, v in raw_names.items()}
            self._class_map = class_map

            # Check exact classes count and order
            if class_map != EXPECTED_CLASS_MAP:
                raise ServiceUnavailableError(
                    f"Model class mapping mismatch. Expected exact mapping {EXPECTED_CLASS_MAP}, got {class_map}."
                )

            # Check for forbidden classes
            found_classes = set(class_map.values())
            forbidden_intersection = found_classes.intersection(FORBIDDEN_CLASSES)
            if forbidden_intersection:
                raise ServiceUnavailableError(
                    f"Model contains forbidden classes: {forbidden_intersection}. Only {EXPECTED_CLASS_MAP} permitted."
                )

            self._model = model
            self._architecture = model.model.__class__.__name__
            self._load_time_ms = round((time.perf_counter() - start_load) * 1000.0, 2)

            # 5. Model Warm-up
            self._warm_up()
            self._is_initialized = True
            logger.info(
                "Model '%s' initialized on %s (Load: %.1fms, Warmup: %.1fms, SHA256: %s)",
                self.model_path.name,
                self.device,
                self._load_time_ms,
                self._warmup_time_ms,
                self._sha256[:12],
            )

    def _warm_up(self) -> None:
        """Executes a single blank dummy frame inference to prime JIT and memory caches."""
        if self._model is None:
            return
        start_warmup = time.perf_counter()
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        try:
            self._model.predict(
                dummy_frame,
                device=self.device,
                conf=0.25,
                verbose=False,
            )
            self._warmup_time_ms = round((time.perf_counter() - start_warmup) * 1000.0, 2)
        except Exception as e:
            logger.warning("Model warm-up threw non-fatal warning: %s", e)

    def get_readiness_info(self) -> Dict[str, Any]:
        """Provides status and metadata for health checks without reloading model."""
        return {
            "model_path": str(self.model_path),
            "checkpoint_found": self.model_path.exists(),
            "sha256": self._sha256,
            "is_loaded": self._is_initialized and self._model is not None,
            "architecture": self._architecture,
            "class_map": self._class_map,
            "supported_classes": list(SUPPORTED_TARGETS),
            "device": self.device,
            "load_time_ms": self._load_time_ms,
            "warmup_time_ms": self._warmup_time_ms,
        }

    def decode_image_bytes(self, image_bytes: bytes) -> Tuple[np.ndarray, int, int, float]:
        """
        Validates and decodes image bytes into a 3-channel BGR numpy array.
        Returns: (decoded_bgr, width, height, decode_ms)
        """
        start_decode = time.perf_counter()

        if not image_bytes or len(image_bytes) == 0:
            raise ValidationError("Empty image payload: 0 bytes received.")

        if len(image_bytes) > self.settings.max_inference_image_bytes:
            raise PayloadTooLargeError(
                f"Image size exceeds maximum allowed ({self.settings.max_inference_image_bytes} bytes).",
                max_bytes=self.settings.max_inference_image_bytes,
            )

        # Decode via OpenCV
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)

        if img is None:
            raise ValidationError("Failed to decode image. File is corrupted, truncated, or in an unsupported format.")

        # Handle different channel configurations
        if len(img.shape) == 2:
            # Grayscale to 3-channel BGR
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif len(img.shape) == 3 and img.shape[2] == 4:
            # Alpha channel PNG / TIFF: convert to BGR
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        elif len(img.shape) == 3 and img.shape[2] == 3:
            pass  # Already BGR
        else:
            raise ValidationError(f"Unsupported image shape with {len(img.shape)} dimensions.")

        height, width = img.shape[:2]
        if width < 16 or height < 16:
            raise ValidationError(f"Image dimensions too small ({width}x{height}). Minimum is 16x16.")
        if width > 8192 or height > 8192:
            raise ValidationError(f"Image dimensions too large ({width}x{height}). Maximum is 8192x8192.")

        decode_ms = round((time.perf_counter() - start_decode) * 1000.0, 3)
        return img, width, height, decode_ms

    def validate_targets(self, targets: Optional[Union[str, List[str]]]) -> List[SupportedClassId]:
        """Validates target classes against the supported schema (person, mask, knife)."""
        if targets is None:
            return ["person", "mask", "knife"]

        raw_list: List[str] = []
        if isinstance(targets, str):
            raw_list = [t.strip().lower() for t in targets.split(",") if t.strip()]
        elif isinstance(targets, list):
            for item in targets:
                if isinstance(item, str):
                    for sub in item.split(","):
                        if sub.strip():
                            raw_list.append(sub.strip().lower())

        if not raw_list:
            raise ValidationError("Targets list cannot be empty.")

        # Deduplicate while preserving order
        deduped: List[SupportedClassId] = []
        for t in raw_list:
            if t not in SUPPORTED_TARGETS:
                raise ValidationError(
                    f"Unsupported target class '{t}'. Supported classes: {sorted(list(SUPPORTED_TARGETS))}."
                )
            if t not in deduped:
                deduped.append(t)  # type: ignore

        return deduped

    def validate_confidence_threshold(self, threshold: Optional[float]) -> float:
        """Validates that confidence is finite and between 0.0 and 1.0."""
        if threshold is None:
            return self.settings.default_confidence_threshold

        try:
            val = float(threshold)
        except (ValueError, TypeError):
            raise ValidationError("Confidence threshold must be a valid numeric float.")

        if not np.isfinite(val):
            raise ValidationError("Confidence threshold must be a finite number.")

        if val < 0.0 or val > 1.0:
            raise ValidationError("Confidence threshold must be between 0.0 and 1.0 inclusive.")

        return round(val, 4)

    def infer_frame_sync(
        self,
        frame: np.ndarray,
        orig_width: int,
        orig_height: int,
        targets: List[SupportedClassId],
        confidence_threshold: float,
        request_id: Optional[str] = None,
        decode_ms: float = 0.0,
    ) -> InferenceResponse:
        """
        Synchronous inference execution on a decoded numpy frame.
        Guarantees thread-safe access and accurate original coordinate space.
        """
        if not self._is_initialized or self._model is None:
            self.load_and_verify_model()

        start_infer = time.perf_counter()

        with self._model_lock:
            results = self._model.predict(
                frame,
                device=self.device,
                conf=confidence_threshold,
                verbose=False,
            )

        infer_ms = round((time.perf_counter() - start_infer) * 1000.0, 3)

        # Postprocessing and serialization
        start_serial = time.perf_counter()
        detections: List[DetectionItem] = []

        if results and len(results) > 0:
            res = results[0]
            boxes = res.boxes

            if boxes is not None and len(boxes) > 0:
                for box_item in boxes:
                    cls_id_num = int(box_item.cls[0].item())
                    cls_name = self._class_map.get(cls_id_num, "unknown")

                    # Filter strictly by requested targets
                    if cls_name not in targets:
                        continue

                    conf = float(box_item.conf[0].item())
                    if not np.isfinite(conf):
                        continue

                    # Extract xyxy bounding box in original pixel space
                    raw_coords = box_item.xyxy[0].tolist()
                    if len(raw_coords) != 4 or not all(np.isfinite(c) for c in raw_coords):
                        continue

                    x1, y1, x2, y2 = raw_coords

                    # Gentle clamp sub-pixel boundary edge cases to original frame bounds
                    x1 = max(0.0, min(float(orig_width), float(x1)))
                    y1 = max(0.0, min(float(orig_height), float(y1)))
                    x2 = max(0.0, min(float(orig_width), float(x2)))
                    y2 = max(0.0, min(float(orig_height), float(y2)))

                    # Skip degenerate or reversed boxes
                    if x2 <= x1 or y2 <= y1:
                        continue

                    width = x2 - x1
                    height = y2 - y1

                    detections.append(
                        DetectionItem(
                            classId=cls_name,  # type: ignore
                            className=cls_name,
                            confidence=conf,
                            box=(round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)),
                            box_object=BoundingBoxObject(
                                x=round(x1, 2),
                                y=round(y1, 2),
                                w=round(width, 2),
                                h=round(height, 2),
                            ),
                        )
                    )

        serial_ms = round((time.perf_counter() - start_serial) * 1000.0, 3)
        total_ms = round(decode_ms + infer_ms + serial_ms, 3)

        return InferenceResponse(
            request_id=request_id,
            model_version=f"{self._architecture or 'YOLOv11n'}-theft-v1",
            model_sha256=self._sha256 or "verified",
            device=self.device,
            original_width=orig_width,
            original_height=orig_height,
            targets=targets,
            confidence_threshold=confidence_threshold,
            detections_count=len(detections),
            detections=detections,
            timings=InferenceTimings(
                decode_ms=decode_ms,
                inference_ms=infer_ms,
                serialization_ms=serial_ms,
                total_ms=total_ms,
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def infer_image_async(
        self,
        image_bytes: bytes,
        targets: Optional[Union[str, List[str]]] = None,
        confidence_threshold: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> InferenceResponse:
        """
        Asynchronous wrapper executing blocking decoding & inference off the main event loop.
        """
        valid_targets = self.validate_targets(targets)
        valid_conf = self.validate_confidence_threshold(confidence_threshold)

        # Run decode off the event loop
        loop = asyncio.get_running_loop()
        frame, orig_w, orig_h, decode_ms = await loop.run_in_executor(
            None, self.decode_image_bytes, image_bytes
        )

        # Run model inference off the event loop
        response = await loop.run_in_executor(
            None,
            self.infer_frame_sync,
            frame,
            orig_w,
            orig_h,
            valid_targets,
            valid_conf,
            request_id,
            decode_ms,
        )

        return response

    @staticmethod
    def scale_box_to_display(
        box: Tuple[float, float, float, float],
        original_width: int,
        original_height: int,
        display_width: int,
        display_height: int,
    ) -> Tuple[float, float, float, float]:
        """
        Helper function to project original frame coordinates onto a resized preview display
        (e.g. historical 480-pixel width downscaled preview container).
        """
        if original_width <= 0 or original_height <= 0:
            raise ValueError("Original dimensions must be positive integers.")
        if display_width <= 0 or display_height <= 0:
            raise ValueError("Display dimensions must be positive integers.")

        scale_x = display_width / float(original_width)
        scale_y = display_height / float(original_height)

        x1, y1, x2, y2 = box
        return (
            round(x1 * scale_x, 2),
            round(y1 * scale_y, 2),
            round(x2 * scale_x, 2),
            round(y2 * scale_y, 2),
        )

    def cleanup(self) -> None:
        """Releases PyTorch tensors and model resources."""
        with self._model_lock:
            self._model = None
            self._is_initialized = False
            logger.info("InferenceService model resources released.")
