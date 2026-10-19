"""
SightLine AI - Health & Readiness Endpoint Tests
Verifies truthful status reporting across API foundation, model inference service, and deferred workers.
"""

from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_health_live_endpoint(client: TestClient):
    """GET /api/v1/health/live should return 200 with live status and timestamp."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert data["service"] == "sightline-api"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"


def test_health_ready_endpoint(client: TestClient):
    """
    GET /api/v1/health/ready should return 200 and accurately describe
    API readiness, model checkpoint, and inference service readiness.
    """
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["phase"] == 4

    components = data["components"]
    # 1. API foundation ready
    assert components["api_foundation"]["ready"] is True

    # 2. Media storage ready
    assert components["media_storage"]["ready"] is True

    # 3. Model checkpoint verified
    assert components["model_checkpoint"]["ready"] is True
    assert components["model_checkpoint"]["classes_count"] == 3
    assert set(components["model_checkpoint"]["supported_classes"]) == {"person", "mask", "knife"}

    # 4. Inference service ready
    assert components["inference_service"]["ready"] is True

    # 5. Background video worker and database ready in Phase 4
    assert components["video_worker"]["ready"] is True
    assert components["database"]["ready"] is True



def test_response_headers_correlation_and_timing(client: TestClient):
    """Verify that every response carries X-Request-ID and X-Process-Time-Ms headers."""
    response = client.get("/api/v1/health/live")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].startswith("req-")
    assert "X-Process-Time-Ms" in response.headers


def test_readiness_reports_503_when_storage_unwritable(client: TestClient):
    """When media storage is unwritable, readiness must truthfully return 503 Service Unavailable."""
    with patch("app.services.storage.LocalMediaStorage.is_writable", return_value=False), \
         patch("backend.app.services.storage.LocalMediaStorage.is_writable", return_value=False), \
         patch("app.api.endpoints.health.LocalMediaStorage.is_writable", return_value=False, create=True), \
         patch("backend.app.api.endpoints.health.LocalMediaStorage.is_writable", return_value=False, create=True):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["media_storage"]["ready"] is False

