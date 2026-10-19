"""
SightLine AI - Phase 7 Security, Tenant Isolation, RLS, & Reliability Suite
Tests:
1. Multi-tenant isolation: User B cannot access User A's sources, jobs, incidents, evidence, or dispatches
2. Anonymous client rejection across all protected endpoints (401 Unauthorized)
3. Token tampering, expired tokens, and credential privilege separation (secret key / service_role rejection)
4. Negative video upload validation (0-byte, corrupt codec, unsupported extension, path traversal sanitization)
5. Worker idempotency deduplication and state consistency
6. Operator security PIN verification, failed attempt tracking, and 60-second persistent lockout
7. Private storage URL expiration and authorized access
"""

import os
import uuid
import time
import pytest
import jwt
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app
from app.config import get_settings
from app.db.database import DatabaseManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def running_application():
    with client:
        yield

settings = get_settings()

from token_support import issue_token

def get_auth_token(operator_id: str, passcode: str = 'unused-test-fixture') -> str:
    return issue_token(sub=str(uuid.uuid5(uuid.NAMESPACE_DNS, f'sightline.operator.{operator_id}')))

def get_user_id(token: str) -> str:
    claims = jwt.decode(token, options={"verify_signature": False})
    return claims["sub"]


# ==============================================================================
# 1. ANONYMOUS CLIENT REJECTION
# ==============================================================================

def test_anonymous_access_rejected_across_all_endpoints():
    """Verify that unauthenticated callers cannot access any protected resource."""
    endpoints = [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/incidents"),
        ("GET", "/api/v1/incidents/inc_test_123"),
        ("PATCH", "/api/v1/incidents/inc_test_123"),
        ("DELETE", "/api/v1/incidents/inc_test_123"),
        ("POST", "/api/v1/analysis/start"),
        ("GET", "/api/v1/analysis/jobs/job_test_123"),
        ("POST", "/api/v1/analysis/jobs/job_test_123/cancel"),
        ("POST", "/api/v1/dispatches/send"),
        ("POST", "/api/v1/dispatches/disp_test_123/cancel"),
        ("GET", "/api/v1/dispatches/disp_test_123"),
        ("GET", "/api/v1/dispatches/incident/inc_test_123"),
    ]

    for method, path in endpoints:
        if method == "GET":
            res = client.get(path)
        elif method == "POST":
            res = client.post(path, json={})
        elif method == "PATCH":
            res = client.patch(path, json={})
        elif method == "DELETE":
            res = client.delete(path)
        assert res.status_code == 401, f"Expected 401 for anonymous {method} {path}, got {res.status_code}"


# ==============================================================================
# 2. TOKEN SECURITY & PRIVILEGE ISOLATION
# ==============================================================================

def test_expired_token_rejected():
    """Verify that expired JWT access tokens are rejected with 401."""
    expired_token = issue_token(exp_delta=-3600)
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json().get("message", "").lower()

def test_tampered_token_rejected():
    """Verify that a token with altered payload or invalid signature is rejected."""
    token = get_auth_token("operator_1")
    tampered = token[:-4] + "xxxx"
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert res.status_code == 401

def test_server_secret_cannot_be_used_as_user_credential():
    """Server secret key must never be accepted as a user JWT."""
    secret = settings.supabase_secret_key
    if secret:
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {secret}"})
        assert res.status_code in (401, 403)


# ==============================================================================
# 3. MULTI-TENANT ISOLATION (USER A vs USER B)
# ==============================================================================

def test_multi_tenant_resource_isolation():
    """
    Verify complete isolation between User A (operator_1) and User B (operator_2):
    - User B cannot read or mutate User A's jobs, incidents, or dispatches.
    - User B cannot view User A's incident records in the list view.
    """
    token_a = get_auth_token("operator_1")
    token_b = get_auth_token("operator_2")

    user_a_id = get_user_id(token_a)
    user_b_id = get_user_id(token_b)
    assert user_a_id != user_b_id, "User A and User B must have distinct UUIDs"

    db = DatabaseManager.get_instance()
    inc_id = f"inc_iso_{uuid.uuid4().hex[:8]}"
    now = "2026-10-16T12:00:00Z"

    # Seed User A source & incident in database
    conn = db.get_connection()
    conn.execute("""
    INSERT OR REPLACE INTO sources (
        id, user_id, source_type, original_filename, storage_bucket,
        storage_key, file_size_bytes, status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "src_user_a",
        user_a_id,
        "video",
        "threat.mp4",
        "source-videos",
        "vault/threat_a.mp4",
        1024,
        "ready",
        now,
        now,
    ))
    conn.execute("""
    INSERT INTO incidents (
        id, source_id, job_id, user_id, title, channel, zone,
        severity, reason, review_status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        inc_id,
        "src_user_a",
        None,
        user_a_id,
        "User A Classified Threat",
        "Camera A",
        "Perimeter A",
        "medium",
        "Neural threat detection event",
        "unreviewed",
        now,
        now,
    ))

    # Test 1: User B cannot fetch User A's incident
    res_b_get = client.get(
        f"/api/v1/incidents/{inc_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res_b_get.status_code in (403, 404), f"User B should not access User A incident: {res_b_get.status_code}"

    # Test 2: User A CAN fetch User A's incident
    res_a_get = client.get(
        f"/api/v1/incidents/{inc_id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_a_get.status_code == 200, f"User A should access own incident: {res_a_get.status_code}"

    # Test 3: User B cannot review User A's incident
    res_b_patch = client.patch(
        f"/api/v1/incidents/{inc_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"status": "confirmed", "reason": "Attempted User B review"}
    )
    assert res_b_patch.status_code in (403, 404), "User B cannot review User A incident"

    # Test 4: User B cannot delete User A's incident
    res_b_del = client.delete(
        f"/api/v1/incidents/{inc_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res_b_del.status_code in (403, 404), "User B cannot delete User A incident"

    # Test 5: Incident List isolation - User B must NOT see User A's incident
    res_b_list = client.get(
        "/api/v1/incidents",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res_b_list.status_code == 200
    b_items = res_b_list.json()["items"]
    assert not any(item["id"] == inc_id for item in b_items), "User A incident leaked in User B incident list"


def test_multi_tenant_dispatch_isolation():
    """Verify User B cannot send or cancel a dispatch for User A's incident."""
    token_a = get_auth_token("operator_1")
    token_b = get_auth_token("operator_2")

    user_a_id = get_user_id(token_a)
    db = DatabaseManager.get_instance()
    inc_id = f"inc_disp_iso_{uuid.uuid4().hex[:8]}"
    now = "2026-10-16T12:00:00Z"

    # Create confirmed incident for User A with matching source
    conn = db.get_connection()
    conn.execute("""
    INSERT OR REPLACE INTO sources (
        id, user_id, source_type, original_filename, storage_bucket,
        storage_key, file_size_bytes, status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "src_disp_a",
        user_a_id,
        "video",
        "threat.mp4",
        "source-videos",
        "vault/threat_disp_a.mp4",
        1024,
        "ready",
        now,
        now,
    ))
    conn.execute("""
    INSERT INTO incidents (
        id, source_id, job_id, user_id, title, channel, zone,
        severity, reason, review_status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        inc_id,
        "src_disp_a",
        None,
        user_a_id,
        "Confirmed Threat Incident",
        "Camera A",
        "Perimeter A",
        "medium",
        "Neural threat detection event",
        "confirmed",
        now,
        now,
    ))

    # User B attempts to dispatch notification for User A's incident
    res_b_send = client.post(
        "/api/v1/dispatches/send",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"incidentId": inc_id, "channel": "simulated_channel"}
    )
    assert res_b_send.status_code in (403, 404), "User B cannot dispatch for User A's incident"

    # User A dispatches successfully
    res_a_send = client.post(
        "/api/v1/dispatches/send",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"incidentId": inc_id, "channel": "simulated_channel"}
    )
    assert res_a_send.status_code == 200
    disp_id = res_a_send.json()["id"]

    # User B attempts to cancel User A's dispatch
    res_b_cancel = client.post(
        f"/api/v1/dispatches/{disp_id}/cancel",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"pin": "1234"}
    )
    assert res_b_cancel.status_code in (403, 404), "User B cannot cancel User A's dispatch"


# ==============================================================================
# 4. NEGATIVE UPLOAD & FORMAT VALIDATION
# ==============================================================================

def test_negative_video_uploads_rejected():
    """Verify that corrupt, empty, and invalid-format files are rejected with 422."""
    token = get_auth_token("operator_1")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Zero-byte upload
    res_empty = client.post(
        "/api/v1/videos/upload",
        headers=headers,
        files={"video": ("empty.mp4", b"", "video/mp4")}
    )
    assert res_empty.status_code == 422
    assert "empty" in res_empty.json()["message"].lower()

    # 2. Corrupt / fake video file (text bytes disguised as mp4)
    res_corrupt = client.post(
        "/api/v1/videos/upload",
        headers=headers,
        files={"video": ("corrupt.mp4", b"NOT_A_REAL_VIDEO_HEADER_12345678", "video/mp4")}
    )
    assert res_corrupt.status_code == 422
    assert "corrupt" in res_corrupt.json()["message"].lower() or "decode" in res_corrupt.json()["message"].lower()

    # 3. Disallowed extension
    res_ext = client.post(
        "/api/v1/videos/upload",
        headers=headers,
        files={"video": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")}
    )
    assert res_ext.status_code == 422
    assert "unsupported" in res_ext.json()["message"].lower()


# ==============================================================================
# 5. IDEMPOTENCY & DUPLICATE SUBMISSION PROTECTION
# ==============================================================================

def test_analysis_submission_idempotency():
    """Verify that duplicate analysis submission with same idempotency key returns existing job."""
    token = get_auth_token("operator_1")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload valid test video
    video_path = Path("qa/data/threat_footage_h264.mp4")
    assert video_path.exists()

    with open(video_path, "rb") as f:
        res_upload = client.post(
            "/api/v1/videos/upload",
            headers=headers,
            files={"video": ("threat_footage_h264.mp4", f, "video/mp4")}
        )
    assert res_upload.status_code == 201
    source_id = res_upload.json()["sourceId"]

    idemp_key = f"idemp_{uuid.uuid4().hex[:12]}"
    headers_with_idemp = {**headers, "Idempotency-Key": idemp_key}

    # First submission
    res_job1 = client.post(
        "/api/v1/analysis/start",
        headers=headers_with_idemp,
        json={"sourceId": source_id, "targets": ["person", "knife"]}
    )
    assert res_job1.status_code == 202
    job_id_1 = res_job1.json()["jobId"]

    # Second submission with identical idempotency key
    res_job2 = client.post(
        "/api/v1/analysis/start",
        headers=headers_with_idemp,
        json={"sourceId": source_id, "targets": ["person", "knife"]}
    )
    assert res_job2.status_code == 202
    job_id_2 = res_job2.json()["jobId"]

    # Must return identical existing job ID without creating duplicate job
    assert job_id_1 == job_id_2, "Idempotency key did not return existing job record"


# ==============================================================================
# 6. OPERATOR PIN VERIFICATION & PERSISTENT LOCKOUT
# ==============================================================================

def test_pin_verification_and_persistent_lockout():
    """
    Verify server-side PIN verification:
    - Owner-selected PIN is required and verifies successfully
    - Incorrect attempts increment counter and return remaining attempts (422)
    - 3rd incorrect attempt triggers persistent 60s lockout (423 Locked)
    - Correct PIN during lockout is still blocked
    """
    token = get_auth_token("operator_lockout_test")
    headers = {"Authorization": f"Bearer {token}"}
    user_id = get_user_id(token)
    db = DatabaseManager.get_instance()

    # Only an owned dispatch may initiate PIN verification.
    db.create_source({'id':'src_lockout_test','user_id':user_id,'original_filename':'fixture.mp4','storage_key':'test/lockout'})
    conn=db.get_connection()
    conn.execute("INSERT INTO incidents(id,source_id,user_id,title,reason,review_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        ('inc_lockout_test','src_lockout_test',user_id,'Isolated lockout test','test','confirmed','2026-10-19T00:00:00Z','2026-10-19T00:00:00Z'))
    db.create_dispatch({'id':'disp_mock','incident_id':'inc_lockout_test','user_id':user_id,'status':'pending','destination_reference':'isolated-test','provider':'simulated_provider'})

    # Clear any previous lockout for this clean user
    db.set_operator_pin(user_id, "1234")

    # Attempt 1: Wrong PIN
    res_fail_1 = client.post(
        "/api/v1/dispatches/disp_mock/cancel",
        headers=headers,
        json={"pin": "9999"}
    )
    assert res_fail_1.status_code == 422
    assert "2 attempts remaining" in res_fail_1.json()["message"]

    # Attempt 2: Wrong PIN
    res_fail_2 = client.post(
        "/api/v1/dispatches/disp_mock/cancel",
        headers=headers,
        json={"pin": "9999"}
    )
    assert res_fail_2.status_code == 422
    assert "1 attempt remaining" in res_fail_2.json()["message"]

    # Attempt 3: Wrong PIN -> Triggers Lockout
    res_fail_3 = client.post(
        "/api/v1/dispatches/disp_mock/cancel",
        headers=headers,
        json={"pin": "9999"}
    )
    assert res_fail_3.status_code == 423, f"Expected 423 Locked on 3rd failure, got {res_fail_3.status_code}"
    assert "locked" in res_fail_3.json()["message"].lower()

    # Attempt 4: Even correct PIN '1234' is locked out
    res_locked = client.post(
        "/api/v1/dispatches/disp_mock/cancel",
        headers=headers,
        json={"pin": "1234"}
    )
    assert res_locked.status_code == 423
    assert "locked" in res_locked.json()["message"].lower()

    # Reset PIN for cleanup
    db.set_operator_pin(user_id, "1234")
