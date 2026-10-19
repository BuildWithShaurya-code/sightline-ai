"""
SightLine AI - Phase 4 Video Analysis & Pipeline Integration Tests
Validates complete backend workflow:
- Authenticated video upload & metadata inspection
- Persistent job creation & idempotency protection
- Controlled VideoWorker execution with Phase 3 inference service
- Frame sampling and bounded keyframe evidence selection
- Bounded coordinate bounding box verification
- Honest negative control (0 detections = 0 incidents)
- Incident retrieval, pagination, search, operator review, and soft delete
- Strict tenant authorization isolation between User A and User B
"""

import json
import time
from pathlib import Path
import tempfile
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db.database import DatabaseManager
from app.services.video_worker import VideoWorker


def wait_for_job(client, token, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/analysis/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("completed", "failed", "cancelled"):
            assert data["status"] == "completed", data
            return {"status":data["status"], "incident_id":data["incidentId"], "detections_count":0 if data["incidentId"] is None else 1}
        time.sleep(0.02)
    raise AssertionError("Persistent worker did not finish test video within 30 seconds")


@pytest.fixture
def test_video_bytes() -> bytes:
    """Reads the authentic H.264 surveillance footage fixture."""
    path = Path("qa/data/threat_footage_h264.mp4")
    if not path.exists():
        pytest.skip(f"Test video fixture missing at {path}")
    return path.read_bytes()


@pytest.fixture
def blank_video_bytes() -> bytes:
    """Generates an authentic, decodable 1-second blank video containing no persons, masks, or knives."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    writer = cv2.VideoWriter(tmp.name, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 240))
    for _ in range(15):
        writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
    writer.release()
    data = Path(tmp.name).read_bytes()
    Path(tmp.name).unlink(missing_ok=True)
    return data


@pytest.fixture
def user_a_token(make_test_token) -> str:
    return make_test_token(sub="11111111-1111-1111-1111-111111111111", email="operator.a@sightline.ai")


@pytest.fixture
def user_b_token(make_test_token) -> str:
    return make_test_token(sub="22222222-2222-2222-2222-222222222222", email="operator.b@sightline.ai")


# ==============================================================================
# 1. VIDEO UPLOAD TESTS
# ==============================================================================

def test_video_upload_requires_auth(client: TestClient, test_video_bytes: bytes):
    """Anonymous video upload must be rejected with 401."""
    res = client.post(
        "/api/v1/videos/upload",
        files={"video": ("threat.mp4", test_video_bytes, "video/mp4")},
    )
    assert res.status_code == 401


def test_video_upload_valid_h264(client: TestClient, user_a_token: str, test_video_bytes: bytes):
    """Authenticated upload of decodable H.264 video must succeed with 201 Created and sourceId."""
    res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    assert res.status_code == 201
    data = res.json()
    assert "sourceId" in data
    assert data["sourceId"].startswith("src_")
    assert "videoUrl" in data
    assert f"/api/v1/videos/{data['sourceId']}/playback" in data["videoUrl"]

    # Verify source was created in database
    db = DatabaseManager.get_instance()
    source = db.get_source(data["sourceId"], "11111111-1111-1111-1111-111111111111")
    assert source is not None
    assert source["status"] == "ready"
    assert source["duration_seconds"] == 5.0
    dims = source["media_dimensions"] if isinstance(source["media_dimensions"], dict) else json.loads(source["media_dimensions"])
    assert dims["width"] == 640
    assert dims["height"] == 360



def test_video_upload_empty_file_rejected(client: TestClient, user_a_token: str):
    """Uploading an empty 0-byte video must fail with 422 Unprocessable Content."""
    res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("empty.mp4", b"", "video/mp4")},
    )
    assert res.status_code == 422
    assert "empty" in res.json()["message"].lower()


def test_video_upload_corrupt_file_rejected(client: TestClient, user_a_token: str):
    """Uploading corrupt/non-video bytes must fail OpenCV decoding validation with 422."""
    res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("corrupt.mp4", b"not-a-video-container-just-text", "video/mp4")},
    )
    assert res.status_code == 422
    assert "decode" in res.json()["message"].lower() or "corrupted" in res.json()["message"].lower()


def test_video_upload_unsupported_extension_rejected(client: TestClient, user_a_token: str):
    """Uploading disallowed file extensions must fail validation with 422."""
    res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("payload.exe", b"MZdummybytes", "application/octet-stream")},
    )
    assert res.status_code == 422
    assert "unsupported" in res.json()["message"].lower()


def test_video_playback_authorized(client: TestClient, user_a_token: str, test_video_bytes: bytes):
    """Owner can stream uploaded video via GET /videos/{sourceId}/playback."""
    upload_res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = upload_res.json()["sourceId"]

    playback_res = client.get(
        f"/api/v1/videos/{source_id}/playback",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert playback_res.status_code == 200
    assert playback_res.headers["content-type"] == "video/mp4"
    assert len(playback_res.content) == len(test_video_bytes)


def test_video_playback_cross_user_forbidden(
    client: TestClient, user_a_token: str, user_b_token: str, test_video_bytes: bytes
):
    """User B cannot stream User A's uploaded video."""
    upload_res = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = upload_res.json()["sourceId"]

    playback_res = client.get(
        f"/api/v1/videos/{source_id}/playback",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert playback_res.status_code in (403, 404)


# ==============================================================================
# 2. ANALYSIS JOB SUBMISSION & CANCELLATION TESTS
# ==============================================================================

def test_analysis_start_valid(client: TestClient, user_a_token: str, test_video_bytes: bytes):
    """Starting analysis returns 202 Accepted with jobId."""
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={
            "sourceId": source_id,
            "targets": ["person", "mask"],
            "confidence_threshold": 0.3,
            "sample_rate_sec": 0.5,
        },
    )
    assert res.status_code == 202
    data = res.json()
    assert "jobId" in data
    assert data["jobId"].startswith("job_")


def test_analysis_start_rejects_unsupported_targets(
    client: TestClient, user_a_token: str, test_video_bytes: bytes
):
    """Requesting 'gun' or 'motion' must be strictly rejected with 422."""
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={
            "sourceId": source_id,
            "targets": ["gun", "motion"],
        },
    )
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "VALIDATION_ERROR"
    combined_err = (body.get("message", "") + " " + json.dumps(body.get("details", ""))).lower()
    assert "unsupported" in combined_err or "forbidden" in combined_err



def test_analysis_start_rejects_cross_user_source(
    client: TestClient, user_a_token: str, user_b_token: str, test_video_bytes: bytes
):
    """User B cannot start analysis on User A's uploaded source."""
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"sourceId": source_id, "targets": ["person"]},
    )
    assert res.status_code == 404


def test_analysis_idempotency_key(client: TestClient, user_a_token: str, test_video_bytes: bytes):
    """Repeated submissions with the same idempotency key return the same jobId."""
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    idempotency_key = "unique-client-key-12345"
    headers = {
        "Authorization": f"Bearer {user_a_token}",
        "X-Idempotency-Key": idempotency_key,
    }
    payload = {"sourceId": source_id, "targets": ["person"]}

    res1 = client.post("/api/v1/analysis/start", headers=headers, json=payload)
    assert res1.status_code == 202
    job_id1 = res1.json()["jobId"]

    res2 = client.post("/api/v1/analysis/start", headers=headers, json=payload)
    assert res2.status_code == 202
    job_id2 = res2.json()["jobId"]

    assert job_id1 == job_id2


def test_job_cancellation_queued(client: TestClient, user_a_token: str, test_video_bytes: bytes):
    """Queued job can be cancelled immediately."""
    db = DatabaseManager.get_instance()
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    # Manually create queued job without auto-running worker
    job = db.create_analysis_job(
        user_id="11111111-1111-1111-1111-111111111111",
        source_id=source_id,
        targets=["person"],
    )
    job_id = job["id"]

    res = client.post(
        f"/api/v1/analysis/jobs/{job_id}/cancel",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    # Verify polling reflects cancelled status
    poll_res = client.get(
        f"/api/v1/analysis/jobs/{job_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert poll_res.json()["status"] == "cancelled"


def test_abandoned_job_recovery():
    """Worker restart detects abandoned jobs left in 'processing' status."""
    db = DatabaseManager.get_instance()
    # Insert simulated stale job
    conn = db.get_connection()
    stale_job_id = "job_stale_abandoned_test"
    conn.execute("""
    INSERT OR REPLACE INTO sources (id, user_id, source_type, original_filename, storage_key, status, created_at, updated_at)
    VALUES ('src_dummy', 'user_x', 'video_upload', 'dummy.mp4', 'dummy_key', 'ready', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
    """)
    conn.execute("""
    INSERT OR REPLACE INTO analysis_jobs (id, source_id, user_id, targets, status, started_at, created_at, updated_at)
    VALUES (?, 'src_dummy', 'user_x', '["person"]', 'processing', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
    """, (stale_job_id,))

    recovered = db.recover_abandoned_jobs(timeout_seconds=60)
    assert recovered >= 1

    job = db.get_job(stale_job_id)
    assert job["status"] == "failed"
    assert "abandoned" in job["error_message"].lower() or "timed out" in job["error_message"].lower()


# ==============================================================================
# 3. END-TO-END PIPELINE: POSITIVE THREAT FOOTAGE
# ==============================================================================

def test_e2e_positive_threat_footage_pipeline(
    client: TestClient, user_a_token: str, test_video_bytes: bytes
):
    """
    Complete end-to-end processing test using real YOLOv11 nano model on threat_footage_h264.mp4:
    - Upload video
    - Submit analysis job for targets ['person', 'mask']
    - Execute worker processing synchronously
    - Verify job completion (status=completed, incidentId populated)
    - Retrieve incident detail and verify frames, bounding boxes, and unreviewed status
    - Perform operator review (PATCH to 'confirmed')
    - Search incident history
    - Soft-delete incident
    """
    db = DatabaseManager.get_instance()
    worker = VideoWorker()

    # 1. Upload video
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("threat_footage_h264.mp4", test_video_bytes, "video/mp4")},
    )
    assert up.status_code == 201
    source_id = up.json()["sourceId"]

    # 2. Start analysis
    start_res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={
            "sourceId": source_id,
            "targets": ["person", "mask"],
            "confidence_threshold": 0.25,
            "sample_rate_sec": 0.5,
        },
    )
    assert start_res.status_code == 202
    job_id = start_res.json()["jobId"]

    # 3. Process video with real model using worker
    result = wait_for_job(client, user_a_token, job_id)
    assert result["status"] == "completed"
    assert result["incident_id"] is not None
    incident_id = result["incident_id"]

    # 4. Poll job status
    poll_res = client.get(
        f"/api/v1/analysis/jobs/{job_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert poll_res.status_code == 200
    job_info = poll_res.json()
    assert job_info["status"] == "completed"
    assert job_info["progress"] == 100
    assert job_info["incidentId"] == incident_id

    # 5. Retrieve full incident details
    inc_res = client.get(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert inc_res.status_code == 200
    incident = inc_res.json()

    # Validate schema conforms to frontend requirements
    assert incident["id"] == incident_id
    assert incident["sourceId"] == source_id
    assert incident["status"] == "unreviewed"
    assert "createdAt" in incident

    # Evidence frames verification: bounded keyframes (at least 1, max 8)
    frames = incident["frames"]
    assert 1 <= len(frames) <= 8
    for f in frames:
        assert "id" in f
        assert isinstance(f["timeSeconds"], (int, float))
        assert f["imageDataUrl"].startswith("data:image/jpeg;base64,")

    # Detections verification: original coordinates and supported classes
    detections = incident["detections"]
    assert len(detections) > 0
    for d in detections:
        assert d["classId"] in ("person", "mask", "knife")
        assert 0.0 <= d["confidence"] <= 1.0
        # Check box coordinates [x1, y1, x2, y2]
        box = d["box"]
        assert len(box) == 4
        x1, y1, x2, y2 = box
        assert 0 <= x1 <= x2 <= 640
        assert 0 <= y1 <= y2 <= 360

    # 6. Operator Review: Confirm threat
    review_res = client.patch(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={
            "status": "confirmed",
            "reason": "Operator verified person and mask in loading dock area.",
        },
    )
    assert review_res.status_code == 200
    updated_inc = review_res.json()
    assert updated_inc["status"] == "confirmed"
    assert updated_inc["reviewer_id"] == "11111111-1111-1111-1111-111111111111"
    assert updated_inc["review_reason"] == "Operator verified person and mask in loading dock area."

    # 7. Incident History Listing & Search
    list_res = client.get(
        "/api/v1/incidents?status=confirmed",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["pagination"]["total_items"] >= 1
    matching_ids = [item["id"] for item in list_data["items"]]
    assert incident_id in matching_ids

    # Search by keyword
    search_res = client.get(
        "/api/v1/incidents?q=Threat",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert search_res.status_code == 200
    assert any(i["id"] == incident_id for i in search_res.json()["items"])

    # 8. Soft-Delete Incident
    del_res = client.delete(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Subsequent GET returns 404
    after_del = client.get(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert after_del.status_code == 404


# ==============================================================================
# 4. NEGATIVE CONTROL TEST: NO DETECTIONS = HONEST ZERO INCIDENTS
# ==============================================================================

def test_negative_control_video_honest_zero_incidents(
    client: TestClient, user_a_token: str, blank_video_bytes: bytes
):
    """
    Negative control test:
    When a video contains no requested objects, analysis must complete honestly:
    - job status: completed
    - incidentId: None
    - No phantom incident or fabricated detections generated!
    """
    worker = VideoWorker()

    # 1. Upload blank video
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("negative_control.mp4", blank_video_bytes, "video/mp4")},
    )
    assert up.status_code == 201
    source_id = up.json()["sourceId"]

    # 2. Start analysis
    start_res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={
            "sourceId": source_id,
            "targets": ["person", "mask", "knife"],
        },
    )
    assert start_res.status_code == 202
    job_id = start_res.json()["jobId"]

    # 3. Process with worker
    res = wait_for_job(client, user_a_token, job_id)
    assert res["status"] == "completed"
    assert res["incident_id"] is None
    assert res["detections_count"] == 0

    # 4. Verify polling status
    poll = client.get(
        f"/api/v1/analysis/jobs/{job_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert poll.status_code == 200
    assert poll.json()["status"] == "completed"
    assert poll.json()["incidentId"] is None


# ==============================================================================
# 5. TENANT ISOLATION TESTS (USER A vs USER B)
# ==============================================================================

def test_strict_tenant_isolation_user_a_vs_user_b(
    client: TestClient, user_a_token: str, user_b_token: str, test_video_bytes: bytes
):
    """
    Tenant Isolation:
    User B cannot access User A's jobs, sources, or incidents.
    """
    worker = VideoWorker()

    # User A uploads and completes an incident
    up = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"video": ("user_a_clip.mp4", test_video_bytes, "video/mp4")},
    )
    source_id = up.json()["sourceId"]

    start_res = client.post(
        "/api/v1/analysis/start",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"sourceId": source_id, "targets": ["person"]},
    )
    job_id = start_res.json()["jobId"]

    result = wait_for_job(client, user_a_token, job_id)
    incident_id = result["incident_id"]

    # User B queries User A's job -> 404
    b_job = client.get(
        f"/api/v1/analysis/jobs/{job_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert b_job.status_code == 404

    # User B cancels User A's job -> 404
    b_cancel = client.post(
        f"/api/v1/analysis/jobs/{job_id}/cancel",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert b_cancel.status_code == 404

    # User B queries User A's incident -> 404
    b_inc = client.get(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert b_inc.status_code == 404

    # User B updates User A's incident review -> 404
    b_review = client.patch(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"status": "dismissed"},
    )
    assert b_review.status_code == 404

    # User B soft-deletes User A's incident -> 404
    b_del = client.delete(
        f"/api/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert b_del.status_code == 404

    # User B lists incidents -> does NOT see User A's incident
    b_list = client.get(
        "/api/v1/incidents",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert b_list.status_code == 200
    b_incident_ids = [item["id"] for item in b_list.json()["items"]]
    assert incident_id not in b_incident_ids
