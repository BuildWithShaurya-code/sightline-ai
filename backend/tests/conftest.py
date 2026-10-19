"""
SightLine AI - Pytest Test Configuration & Shared Fixtures
All synthetic fixtures are explicitly marked SYNTHETIC_FIXTURE and never used in production.
"""

import os
import sys
from pathlib import Path
from typing import Optional
import pytest
from fastapi.testclient import TestClient


# Ensure both backend/ and workspace root are in sys.path
backend_dir = Path(__file__).resolve().parent.parent
repo_root = backend_dir.parent

for p in [str(backend_dir), str(repo_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Support both `from app...` and `from backend.app...`
try:
    import app
    import app.config
    import app.main
    import app.schemas
    import app.services
    sys.modules.setdefault("backend", sys.modules[__name__])
    sys.modules["backend.app"] = app
    sys.modules["backend.app.config"] = app.config
    sys.modules["backend.app.main"] = app.main
    sys.modules["backend.app.schemas"] = app.schemas
    sys.modules["backend.app.services"] = app.services
except Exception:
    pass

sys.path.insert(0, str(backend_dir / 'tests'))
from token_support import PUBLIC_JWK, PROJECT, issue_token
os.environ['SUPABASE_URL'] = PROJECT

from app.config import Settings, get_settings
from app.main import create_app

# Marker string to ensure synthetic fixtures are never mistaken for real detections
SYNTHETIC_MARKER = "SYNTHETIC_TEST_FIXTURE_DO_NOT_USE_IN_PRODUCTION"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Provides isolated settings with a temporary media directory."""
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        environment="test",
        api_prefix="/api/v1",
        media_dir=media_dir,
        model_path=Path("backend/models/best.pt"),
        log_level="DEBUG",
        session_secret="test-environment-secret-key-for-unit-testing",
        supabase_url=PROJECT,
        supabase_secret_key="test-privileged-server-secret-key-do-not-use-as-token",
        supabase_publishable_key="test-anon-publishable-key",
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    """FastAPI TestClient with overridden test settings."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def isolated_public_signing_keys(monkeypatch):
    from app.core import auth
    auth._jwks_cache.clear()
    async def keys(issuer):
        return {'keys':[PUBLIC_JWK]}
    monkeypatch.setattr(auth, '_fetch_jwks', keys)
    yield
    auth._jwks_cache.clear()


@pytest.fixture
def make_test_token(test_settings):
    return issue_token


@pytest.fixture
def valid_auth_headers(make_test_token) -> dict:
    token = make_test_token()
    return {"Authorization": f"Bearer {token}"}



@pytest.fixture
def sample_synthetic_detection():
    """Explicitly labeled synthetic detection fixture for schema verification."""
    return {
        "detection_id": f"det_synth_{SYNTHETIC_MARKER}_001",
        "classId": "person",
        "className": "Person",
        "confidence": 0.8842,
        "box": [120.0, 80.5, 340.0, 460.0],
        "frame_width": 1920,
        "frame_height": 1080,
        "frame_index": 12,
        "video_offset_ms": 400,
        "model_version": "sightline-yolo11n-v1",
    }


@pytest.fixture
def sample_synthetic_incident(sample_synthetic_detection):
    """Explicitly labeled synthetic incident fixture for schema verification."""
    return {
        "id": f"INC-TEST-{SYNTHETIC_MARKER}",
        "sourceId": "test_video_sample.mp4",
        "createdAt": "2026-10-16T12:00:00.000Z",
        "status": "unreviewed",
        "frames": [
            {
                "id": f"frame_synth_{SYNTHETIC_MARKER}_01",
                "timeSeconds": 1.25,
                "imageDataUrl": "data:image/jpeg;base64,synthetic_frame_bytes",
            }
        ],
        "detections": [sample_synthetic_detection],
        "title": "Synthetic Test Threat Event",
        "channel": "CAM-01 // MAIN GATE",
        "zone": "Zone A",
        "durationSeconds": 5.0,
        "thumbnail": "data:image/jpeg;base64,synthetic_thumb_bytes",
    }
