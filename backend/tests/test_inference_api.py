"""
SightLine AI - API Endpoint Tests for POST /api/v1/inference/image
Tests authentication enforcement, token validation, error payload structure,
input media validation, and response serialization.
"""

import io
import cv2
from fastapi.testclient import TestClient
import numpy as np


def create_dummy_jpeg(width: int = 640, height: int = 480) -> bytes:
    """Helper to generate encoded JPEG bytes for testing."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", img)
    return encoded.tobytes()


def test_inference_requires_authentication(client: TestClient):
    """POST /api/v1/inference/image without token must be rejected with 401."""
    jpeg_bytes = create_dummy_jpeg()
    response = client.post(
        "/api/v1/inference/image",
        files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "UNAUTHENTICATED"
    assert "Authorization header is required" in data["message"]


def test_inference_rejects_expired_token(client: TestClient, make_test_token):
    """Expired bearer token must be rejected with 401."""
    expired_token = make_test_token(exp_delta=-60)
    jpeg_bytes = create_dummy_jpeg()

    response = client.post(
        "/api/v1/inference/image",
        headers={"Authorization": f"Bearer {expired_token}"},
        files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "UNAUTHENTICATED"
    assert "expired" in data["message"].lower()


def test_inference_rejects_wrong_project_token(client: TestClient, make_test_token):
    """Token issued by a different Supabase project must be rejected with 401."""
    wrong_token = make_test_token(iss="https://other-project.supabase.co/auth/v1")
    jpeg_bytes = create_dummy_jpeg()

    response = client.post(
        "/api/v1/inference/image",
        headers={"Authorization": f"Bearer {wrong_token}"},
        files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "UNAUTHENTICATED"
    assert data["message"] == "Invalid account access token."


def test_inference_rejects_secret_key_as_credential(client: TestClient):
    """Using the server secret key as a bearer token must be rejected with 403."""
    jpeg_bytes = create_dummy_jpeg()
    response = client.post(
        "/api/v1/inference/image",
        headers={"Authorization": "Bearer test-privileged-server-secret-key-do-not-use-as-token"},
        files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "FORBIDDEN"
    assert "API key cannot be used" in data["message"]


def test_inference_with_valid_token_and_empty_frame(client: TestClient, valid_auth_headers):
    """Valid authenticated request on empty image should return 200 with 0 detections."""
    jpeg_bytes = create_dummy_jpeg(640, 480)

    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("blank.jpg", jpeg_bytes, "image/jpeg")},
        data={"targets": "person,mask,knife", "confidence_threshold": 0.3},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["original_width"] == 640
    assert data["original_height"] == 480
    assert data["confidence_threshold"] == 0.3
    assert data["targets"] == ["person", "mask", "knife"]
    assert data["detections_count"] == 0
    assert data["detections"] == []
    assert "timings" in data
    assert data["timings"]["decode_ms"] >= 0.0
    assert data["timings"]["inference_ms"] >= 0.0
    assert "X-Request-ID" in response.headers


def test_inference_rejects_corrupt_image(client: TestClient, valid_auth_headers):
    """Corrupt image payload should be rejected with structured error."""
    corrupt_bytes = b"CORRUPT_NOT_AN_IMAGE_FILE_BYTES"
    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("corrupt.jpg", corrupt_bytes, "image/jpeg")},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "VALIDATION_FAILED"
    assert "Failed to decode image" in data["message"]


def test_inference_rejects_invalid_target_class(client: TestClient, valid_auth_headers):
    """Forbidden or unknown target classes must be rejected with 422."""
    jpeg_bytes = create_dummy_jpeg()
    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
        data={"targets": "gun,person"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "VALIDATION_FAILED"
    assert "Unsupported target class 'gun'" in data["message"]
