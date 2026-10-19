"""
SightLine AI - Unit Tests for InferenceService
Validates exact class mapping, target filtering, confidence thresholds, image decoding,
bounding box integrity, coordinate projection, and tensor serialization.
"""

import numpy as np
import pytest

from backend.app.core.errors import PayloadTooLargeError, ValidationError
from backend.app.services.inference_service import (
    EXPECTED_CLASS_MAP,
    EXPECTED_SHA256,
    InferenceService,
)


def test_exact_numeric_class_mapping():
    """Verify that expected classes are strictly numeric 0, 1, 2 mapping to person, mask, knife."""
    assert EXPECTED_CLASS_MAP == {0: "person", 1: "mask", 2: "knife"}
    assert EXPECTED_CLASS_MAP[0] == "person"
    assert EXPECTED_CLASS_MAP[1] == "mask"
    assert EXPECTED_CLASS_MAP[2] == "knife"
    assert "gun" not in EXPECTED_CLASS_MAP.values()
    assert "motion" not in EXPECTED_CLASS_MAP.values()


def test_target_filtering_validation():
    """Verify target list validation and deduplication."""
    service = InferenceService.get_instance()

    # None defaults to all three classes
    assert service.validate_targets(None) == ["person", "mask", "knife"]

    # Comma-separated string
    assert service.validate_targets("person,mask") == ["person", "mask"]

    # Deduplication while preserving order
    assert service.validate_targets(["person", "person", "mask"]) == ["person", "mask"]

    # Rejection of unsupported target
    with pytest.raises(ValidationError) as exc:
        service.validate_targets("person,gun")
    assert "Unsupported target class 'gun'" in str(exc.value)

    # Rejection of empty target list
    with pytest.raises(ValidationError):
        service.validate_targets("")


def test_confidence_threshold_validation():
    """Verify confidence threshold bounds and type constraints."""
    service = InferenceService.get_instance()

    # None returns configured default (0.25)
    assert service.validate_confidence_threshold(None) == 0.25

    # Valid values
    assert service.validate_confidence_threshold(0.5) == 0.5
    assert service.validate_confidence_threshold(0.0) == 0.0
    assert service.validate_confidence_threshold(1.0) == 1.0

    # Out-of-bounds rejection
    with pytest.raises(ValidationError):
        service.validate_confidence_threshold(-0.1)

    with pytest.raises(ValidationError):
        service.validate_confidence_threshold(1.05)

    # Non-finite values rejection
    with pytest.raises(ValidationError):
        service.validate_confidence_threshold(float("nan"))

    with pytest.raises(ValidationError):
        service.validate_confidence_threshold(float("inf"))

    with pytest.raises(ValidationError):
        service.validate_confidence_threshold("invalid_float")  # type: ignore


def test_image_decoding_empty_and_corrupt():
    """Verify image decoding handles empty, corrupt, and truncated payloads."""
    service = InferenceService.get_instance()

    # Empty payload
    with pytest.raises(ValidationError) as exc:
        service.decode_image_bytes(b"")
    assert "Empty image payload" in str(exc.value)

    # Corrupt payload
    with pytest.raises(ValidationError) as exc:
        service.decode_image_bytes(b"NOT_A_VALID_IMAGE_HEADER_GARBAGE_BYTES")
    assert "Failed to decode image" in str(exc.value)


def test_image_decoding_dimensions_and_channels():
    """Verify image decoding handles grayscale, RGBA, and valid BGR."""
    import cv2
    service = InferenceService.get_instance()

    # 1. Valid BGR (640x480)
    img_bgr = np.zeros((480, 640, 3), dtype=np.uint8)
    _, encoded_jpg = cv2.imencode(".jpg", img_bgr)
    decoded, w, h, decode_ms = service.decode_image_bytes(encoded_jpg.tobytes())
    assert w == 640
    assert h == 480
    assert decoded.shape == (480, 640, 3)
    assert decode_ms >= 0.0

    # 2. Grayscale broadcast to 3-channel
    img_gray = np.zeros((300, 400), dtype=np.uint8)
    _, encoded_gray = cv2.imencode(".png", img_gray)
    decoded_gray, w_g, h_g, _ = service.decode_image_bytes(encoded_gray.tobytes())
    assert w_g == 400
    assert h_g == 300
    assert decoded_gray.shape == (300, 400, 3)

    # 3. RGBA alpha stripping
    img_rgba = np.zeros((200, 200, 4), dtype=np.uint8)
    _, encoded_rgba = cv2.imencode(".png", img_rgba)
    decoded_rgba, w_a, h_a, _ = service.decode_image_bytes(encoded_rgba.tobytes())
    assert decoded_rgba.shape == (200, 200, 3)

    # 4. Too small dimensions (<16x16)
    img_tiny = np.zeros((8, 8, 3), dtype=np.uint8)
    _, encoded_tiny = cv2.imencode(".jpg", img_tiny)
    with pytest.raises(ValidationError) as exc:
        service.decode_image_bytes(encoded_tiny.tobytes())
    assert "Image dimensions too small" in str(exc.value)


def test_coordinate_scaling_preview_downscaling_regression():
    """
    Regression test for historical preview downsizing issue:
    Verifies that original coordinates are accurately projected to a 480-pixel width display.
    """
    orig_w, orig_h = 1920, 1080
    display_w, display_h = 480, 270

    original_box = (192.0, 108.0, 960.0, 540.0)
    scaled_box = InferenceService.scale_box_to_display(
        original_box,
        original_width=orig_w,
        original_height=orig_h,
        display_width=display_w,
        display_height=display_h,
    )

    # Scaling factor is 480 / 1920 = 0.25
    expected_box = (48.0, 27.0, 240.0, 135.0)
    assert scaled_box == expected_box

    # Rejection of invalid display bounds
    with pytest.raises(ValueError):
        InferenceService.scale_box_to_display(original_box, 0, 1080, 480, 270)


def test_serialization_contains_no_tensors_or_numpy_types():
    """
    Ensures that inference response payloads serialize into pure Python primitives
    and conform strictly to standard JSON requirements.
    """
    import json
    service = InferenceService.get_instance()

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    response = service.infer_frame_sync(
        dummy_frame,
        orig_width=640,
        orig_height=480,
        targets=["person", "mask", "knife"],
        confidence_threshold=0.25,
        request_id="test-req-001",
    )

    # Verify Pydantic model serialization to dict and JSON string
    res_dict = response.model_dump()
    json_str = response.model_dump_json()

    assert isinstance(json_str, str)
    parsed = json.loads(json_str)

    assert parsed["original_width"] == 640
    assert parsed["original_height"] == 480
    assert isinstance(parsed["detections"], list)
    assert isinstance(parsed["timings"]["decode_ms"], float)
    assert isinstance(parsed["timings"]["inference_ms"], float)
