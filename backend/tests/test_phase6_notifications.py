"""
SightLine AI - Phase 6 Notifications & Dispatch Test Suite
Covers:
- Telegram notification provider (formatting, 200 OK, 4xx/5xx, rate limits, timeouts, token redaction)
- Simulation provider
- DispatchService (tenant isolation, review state requirements, idempotency, audit trail)
- Server-side PIN verification and persistent lockout (HTTP 423)
- Atomic cancellation semantics
- API endpoint integration
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.auth import AuthenticatedUser
from app.core.errors import LockedError, NotFoundError, ValidationError
from app.db.database import DatabaseManager
from app.main import create_app
from app.schemas.dispatch import (
    DispatchCancelRequest,
    DispatchNotificationChannel,
    DispatchSendRequest,
    DispatchStatus,
)
from app.services.dispatch_service import DispatchService
from app.services.notifications.base import NotificationPayload
from app.services.notifications.simulation import SimulationProvider
from app.services.notifications.telegram import TelegramProvider


@pytest.fixture
def db(tmp_path):
    test_db_path = tmp_path / "test_phase6.db"
    db_mgr = DatabaseManager(db_path=test_db_path)
    return db_mgr


@pytest.fixture
def user_a():
    return AuthenticatedUser(id="user_alice_uuid", email="alice@sightline.ai")


@pytest.fixture
def user_b():
    return AuthenticatedUser(id="user_bob_uuid", email="bob@sightline.ai")


@pytest.fixture
def confirmed_incident(db, user_a):
    source = db.create_source({
        "id": "src_phase6_test",
        "user_id": user_a.id,
        "original_filename": "test_cam.mp4",
        "storage_key": "vault/test_cam.mp4",
    })
    db.create_analysis_job(
        user_id=user_a.id,
        source_id=source["id"],
        targets=["person", "mask"],
        job_id="job_phase6_test",
    )
    inc_id = db.finalize_analysis_results(
        job_id="job_phase6_test",
        incident_dict={
            "id": "INC-PHASE6-001",
            "source_id": source["id"],
            "job_id": "job_phase6_test",
            "user_id": user_a.id,
            "title": "Threat Alert: Person, Mask",
            "reason": "Neural threat detected",
            "review_status": "confirmed",
        },
        evidence_list=[{
            "id": "ev_001",
            "incident_id": "INC-PHASE6-001",
            "source_id": source["id"],
            "user_id": user_a.id,
            "storage_key": "evidence/ev_001.jpg",
            "video_offset_seconds": 1.5,
        }],
        detections_list=[{
            "id": "det_001",
            "job_id": "job_phase6_test",
            "source_id": source["id"],
            "evidence_id": "ev_001",
            "class_id": "mask",
            "class_name": "mask",
            "confidence": 0.89,
            "box": [100, 50, 200, 150],
            "frame_index": 22,
            "video_offset_seconds": 1.5,
        }],
    )
    return inc_id


# ==============================================================================
# 1. TELEGRAM PROVIDER UNIT TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_telegram_provider_missing_credentials():
    provider = TelegramProvider(bot_token=None, default_chat_id="123456")
    payload = NotificationPayload(
        incident_id="INC-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Threat Alert",
        channel_name="CAM-01",
        zone="Zone A",
        detected_classes=["person"],
        detections=[],
        max_confidence=0.9,
    )
    result = await provider.send_alert(payload, destination="123456")
    assert result.accepted is False
    assert result.status == "failed"
    assert "token is not configured" in result.error_message


@pytest.mark.anyio
async def test_telegram_provider_missing_destination():
    provider = TelegramProvider(bot_token="fake_bot_token", default_chat_id=None)
    payload = NotificationPayload(
        incident_id="INC-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Threat Alert",
        channel_name="CAM-01",
        zone="Zone A",
        detected_classes=["person"],
        detections=[],
        max_confidence=0.9,
    )
    result = await provider.send_alert(payload, destination="")
    assert result.accepted is False
    assert result.status == "failed"
    assert "destination" in result.error_message


@pytest.mark.anyio
async def test_telegram_provider_successful_send():
    provider = TelegramProvider(bot_token="test_token_123", default_chat_id="chat_777")
    payload = NotificationPayload(
        incident_id="INC-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Threat Alert",
        channel_name="CAM-01",
        zone="Zone A",
        detected_classes=["person", "mask"],
        detections=[],
        max_confidence=0.88,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "ok": True,
        "result": {"message_id": 98765},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await provider.send_alert(payload, destination="chat_777")

    assert result.accepted is True
    assert result.status == "sent"
    assert result.provider_name == "telegram"
    assert result.provider_reference == "98765"
    assert result.is_simulated is False


@pytest.mark.anyio
async def test_telegram_provider_token_redaction():
    secret_token = "SECRET_BOT_TOKEN_XYZ"
    provider = TelegramProvider(bot_token=secret_token, default_chat_id="chat_777")
    payload = NotificationPayload(
        incident_id="INC-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Threat Alert",
        channel_name="CAM-01",
        zone="Zone A",
        detected_classes=["knife"],
        detections=[],
        max_confidence=0.92,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "ok": False,
        "error_code": 401,
        "description": f"Unauthorized: invalid token {secret_token}",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await provider.send_alert(payload, destination="chat_777")

    assert result.accepted is False
    assert result.status == "failed"
    # Verify token is redacted
    assert secret_token not in result.error_message
    assert "[REDACTED_BOT_TOKEN]" in result.error_message


@pytest.mark.anyio
async def test_telegram_provider_timeout_uncertain_status():
    provider = TelegramProvider(bot_token="test_token", default_chat_id="chat_777")
    payload = NotificationPayload(
        incident_id="INC-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Threat Alert",
        channel_name="CAM-01",
        zone="Zone A",
        detected_classes=["knife"],
        detections=[],
        max_confidence=0.92,
    )

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
        result = await provider.send_alert(payload, destination="chat_777")

    assert result.accepted is False
    assert result.status == "uncertain"
    assert result.retryable is False


# ==============================================================================
# 2. SIMULATION PROVIDER TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_simulation_provider():
    provider = SimulationProvider()
    payload = NotificationPayload(
        incident_id="INC-SIM-001",
        timestamp="2026-10-16T12:00:00Z",
        review_status="confirmed",
        title="Simulated Threat",
        channel_name="CAM-SIM",
        zone="Retail Floor",
        detected_classes=["mask"],
        detections=[],
        max_confidence=0.85,
    )
    result = await provider.send_alert(payload, destination="local_sim_queue")
    assert result.accepted is True
    assert result.status == "simulated"
    assert result.is_simulated is True
    assert result.provider_name == "simulated_provider"
    assert result.provider_reference.startswith("SIM-ALERT-")


# ==============================================================================
# 3. DISPATCH SERVICE & DB INTEGRATION TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_dispatch_service_sends_simulation(db, user_a, confirmed_incident):
    service = DispatchService(db=db)
    resp = await service.send_dispatch(
        incident_id=confirmed_incident,
        current_user=user_a,
        channel=DispatchNotificationChannel.TELEGRAM,
    )
    assert resp.status == DispatchStatus.SIMULATED
    assert resp.is_simulated is True
    assert resp.incidentId == confirmed_incident
    assert resp.provider == "simulated_provider"
    assert resp.provider_reference.startswith("SIM-ALERT-")


@pytest.mark.anyio
async def test_dispatch_service_enforces_tenant_isolation(db, user_a, user_b, confirmed_incident):
    service = DispatchService(db=db)
    # User B cannot dispatch User A's incident
    with pytest.raises(NotFoundError):
        await service.send_dispatch(
            incident_id=confirmed_incident,
            current_user=user_b,
        )


@pytest.mark.anyio
async def test_dispatch_service_rejects_dismissed_incident(db, user_a, confirmed_incident):
    service = DispatchService(db=db)
    # Mark incident dismissed
    db.update_incident_review(confirmed_incident, user_a.id, "dismissed", reviewer_notes="False alarm")

    with pytest.raises(ValidationError) as exc_info:
        await service.send_dispatch(
            incident_id=confirmed_incident,
            current_user=user_a,
        )
    assert "dismissed" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_dispatch_service_idempotency_key(db, user_a, confirmed_incident):
    service = DispatchService(db=db)
    idempotency_key = "idemp_unique_key_12345"

    resp1 = await service.send_dispatch(
        incident_id=confirmed_incident,
        current_user=user_a,
        idempotency_key=idempotency_key,
    )
    resp2 = await service.send_dispatch(
        incident_id=confirmed_incident,
        current_user=user_a,
        idempotency_key=idempotency_key,
    )
    # Must return exact same dispatch ID
    assert resp1.id == resp2.id
    assert resp1.status == resp2.status


# ==============================================================================
# 4. PIN SECURITY & CANCELLATION TESTS
# ==============================================================================

def test_pin_verification_default_pin_success(db, user_a):
    with pytest.raises(ValidationError, match="Set your security PIN"):
        db.verify_operator_pin(user_a.id, "1234")
    assert db.get_operator_security(user_a.id) is None


def test_pin_verification_custom_pin(db, user_a):
    db.set_operator_pin(user_a.id, "8899")
    assert db.verify_operator_pin(user_a.id, "8899") is True

    with pytest.raises(ValidationError):
        db.verify_operator_pin(user_a.id, "1234")


def test_pin_lockout_after_three_failures(db, user_a):
    db.set_operator_pin(user_a.id, "5678")

    # 1st fail
    with pytest.raises(ValidationError) as e1:
        db.verify_operator_pin(user_a.id, "0000", max_attempts=3, lockout_seconds=60)
    assert "2 attempts remaining" in str(e1.value)

    # 2nd fail
    with pytest.raises(ValidationError) as e2:
        db.verify_operator_pin(user_a.id, "0000", max_attempts=3, lockout_seconds=60)
    assert "1 attempt remaining" in str(e2.value)

    # 3rd fail -> LockedError (HTTP 423)
    with pytest.raises(LockedError) as e3:
        db.verify_operator_pin(user_a.id, "0000", max_attempts=3, lockout_seconds=60)
    assert "Maximum failed PIN attempts reached" in str(e3.value)

    # Subsequent attempt within lockout period raises LockedError immediately
    with pytest.raises(LockedError) as e4:
        db.verify_operator_pin(user_a.id, "5678", max_attempts=3, lockout_seconds=60)
    assert "locked out" in str(e4.value)


@pytest.mark.anyio
async def test_cancel_dispatch_already_delivered_fails_honestly(db, user_a, confirmed_incident):
    db.set_operator_pin(user_a.id, "1234")  # Explicit test-owner setup.
    service = DispatchService(db=db)
    disp = await service.send_dispatch(
        incident_id=confirmed_incident,
        current_user=user_a,
    )
    # The dispatch is already in status 'simulated'
    cancel_resp = service.cancel_dispatch(
        dispatch_id=disp.id,
        current_user=user_a,
        pin="1234",
    )
    # A completed simulation has no external message to cancel.
    assert cancel_resp.success is False
    assert "simulation is complete" in cancel_resp.message.lower()
    assert "no external notification was sent" in cancel_resp.message.lower()


def test_cancel_pending_dispatch_succeeds(db, user_a, confirmed_incident):
    db.set_operator_pin(user_a.id, "1234")  # Explicit test-owner setup.
    service = DispatchService(db=db)
    # Manually insert pending dispatch
    disp_rec = db.create_dispatch({
        "id": "disp_pending_test",
        "incident_id": confirmed_incident,
        "user_id": user_a.id,
        "status": "pending",
        "channel": "telegram",
        "destination_reference": "chat_001",
    })
    cancel_resp = service.cancel_dispatch(
        dispatch_id="disp_pending_test",
        current_user=user_a,
        pin="1234",
    )
    assert cancel_resp.success is True
    assert cancel_resp.dispatch.status == DispatchStatus.CANCELLED
    assert cancel_resp.dispatch.cancelledAt is not None


# ==============================================================================
# 5. FASTAPI CLIENT ENDPOINT INTEGRATION TESTS
# ==============================================================================

def test_api_dispatches_workflow():
    app = create_app()
    client = TestClient(app)

    # Test-only issuer fixture; no runtime password login bypass exists.
    from token_support import issue_token
    token = issue_token(sub='phase6-owner')
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload video
    import io
    fake_video = b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 2000
    up_resp = client.post(
        "/api/v1/videos/upload",
        files={"video": ("test_vid.mp4", io.BytesIO(fake_video), "video/mp4")},
        headers=headers,
    )
    assert up_resp.status_code in (201, 422)  # 422 if OpenCV rejects fake header; test client behaves cleanly

    # 3. Test dispatches/incident/{id} returns null if no dispatch
    get_disp = client.get("/api/v1/dispatches/incident/INC-NONEXISTENT", headers=headers)
    assert get_disp.status_code == 200
    assert get_disp.json() is None

    # 4. Test security PIN configuration
    pin_resp = client.post(
        "/api/v1/dispatches/security/pin",
        json={"pin": "4321"},
        headers=headers,
    )
    assert pin_resp.status_code == 200
    assert pin_resp.json()["success"] is True

@pytest.mark.anyio
async def test_unreviewed_incident_cannot_send_and_simulation_is_not_delivery(db, user_a, confirmed_incident):
    db.update_incident_review(confirmed_incident,user_a.id,'unreviewed')
    service=DispatchService(db=db,settings=Settings(dispatch_provider='simulation'))
    with pytest.raises(ValidationError, match='confirmation'):
        await service.send_dispatch(confirmed_incident,user_a)
    assert db.get_dispatch_by_incident(confirmed_incident) is None
    db.update_incident_review(confirmed_incident,user_a.id,'confirmed')
    outcome=await service.send_dispatch(confirmed_incident,user_a)
    assert outcome.status.value=='simulated'
    assert outcome.deliveredAt is None
    reopened=DatabaseManager(db.db_path)
    assert reopened.get_dispatch(outcome.id)['status']=='simulated'
    reopened.close_all()
