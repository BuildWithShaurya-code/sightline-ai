"""
SightLine AI - Data Schema Validation Tests
Tests edge cases, rejected invalid inputs, and constraints across shared schemas.
Uses explicitly labeled synthetic fixtures.
"""

import pytest
from pydantic import ValidationError

from app.schemas.analysis import AnalysisStartRequest, AnalysisJobResponse, JobStatus
from app.schemas.capabilities import ModelCapabilitiesResponse
from app.schemas.common import ErrorResponse, PaginationMeta, PaginatedResponse
from app.schemas.detection import DetectionSchema
from app.schemas.dispatch import (
    DispatchCancelRequest,
    DispatchResponse,
    DispatchSendRequest,
    DispatchStatus,
)
from app.schemas.incident import IncidentSchema, IncidentStatus
from app.schemas.source import SourceResponse, SourceType


# ==============================================================================
# 1. DETECTION SCHEMA TESTS
# ==============================================================================

def test_detection_valid_synthetic(sample_synthetic_detection):
    det = DetectionSchema(**sample_synthetic_detection)
    assert det.classId == "person"
    assert det.confidence == 0.8842
    assert det.box == (120.0, 80.5, 340.0, 460.0)
    assert det.class_id_numeric == 0
    assert det.className == "Person"


def test_detection_rejects_unsupported_classes():
    """Unsupported classes (gun, motion, weapon, vehicle) must be strictly rejected."""
    forbidden = ["gun", "motion", "weapon", "fire", "dog", "car"]
    for cls_name in forbidden:
        with pytest.raises(ValidationError):
            DetectionSchema(
                classId=cls_name,
                confidence=0.85,
                box=[10, 20, 100, 200],
            )


def test_detection_rejects_confidence_out_of_bounds():
    """Confidence must strictly be between 0.0 and 1.0."""
    # Negative confidence
    with pytest.raises(ValidationError):
        DetectionSchema(classId="person", confidence=-0.1, box=[10, 20, 100, 200])

    # Greater than 1.0
    with pytest.raises(ValidationError):
        DetectionSchema(classId="person", confidence=1.01, box=[10, 20, 100, 200])


def test_detection_rejects_display_string_confidence():
    """Display strings like '89%' or 'MASK: 92%' must never be accepted as numeric confidence."""
    with pytest.raises(ValidationError):
        DetectionSchema(classId="mask", confidence="89%", box=[10, 20, 100, 200])

    with pytest.raises(ValidationError):
        DetectionSchema(classId="knife", confidence="0.95", box=[10, 20, 100, 200])


def test_detection_rejects_malformed_bounding_boxes():
    """Bounding box must be exactly 4 numeric values."""
    # Only 3 coordinates
    with pytest.raises(ValidationError):
        DetectionSchema(classId="knife", confidence=0.75, box=[10, 20, 100])

    # 5 coordinates
    with pytest.raises(ValidationError):
        DetectionSchema(classId="knife", confidence=0.75, box=[10, 20, 100, 200, 300])

    # Non-numeric
    with pytest.raises(ValidationError):
        DetectionSchema(classId="knife", confidence=0.75, box=["a", "b", "c", "d"])


def test_detection_rejects_reversed_bounding_boxes():
    """Reversed bounding boxes (x2 < x1 or y2 < y1) must be rejected."""
    # x2 < x1
    with pytest.raises(ValidationError) as exc:
        DetectionSchema(classId="knife", confidence=0.75, box=[300, 20, 100, 200])
    assert "x2" in str(exc.value)

    # y2 < y1
    with pytest.raises(ValidationError) as exc:
        DetectionSchema(classId="knife", confidence=0.75, box=[100, 400, 200, 200])
    assert "y2" in str(exc.value)


def test_detection_rejects_negative_bounding_boxes():
    """Bounding box with negative coordinates must be rejected."""
    with pytest.raises(ValidationError):
        DetectionSchema(classId="knife", confidence=0.75, box=[-10, 20, 100, 200])


# ==============================================================================
# 2. ANALYSIS REQUEST & JOB TESTS
# ==============================================================================

def test_analysis_request_valid():
    req = AnalysisStartRequest(
        sourceId="src_001",
        targets=["person", "mask"],
        confidence_threshold=0.3,
    )
    assert req.sourceId == "src_001"
    assert req.targets == ["person", "mask"]
    assert req.confidence_threshold == 0.3


def test_analysis_request_rejects_empty_source():
    with pytest.raises(ValidationError):
        AnalysisStartRequest(sourceId="", targets=["person"])


def test_analysis_request_rejects_empty_targets():
    with pytest.raises(ValidationError):
        AnalysisStartRequest(sourceId="src_001", targets=[])


def test_analysis_request_rejects_forbidden_targets():
    with pytest.raises(ValidationError) as exc:
        AnalysisStartRequest(sourceId="src_001", targets=["person", "gun"])
    assert "Unsupported detection target" in str(exc.value)


def test_analysis_job_lifecycle_states():
    for valid_status in ["queued", "processing", "completed", "failed", "cancelled"]:
        job = AnalysisJobResponse(id="job_123", status=valid_status)
        assert job.status.value == valid_status

    with pytest.raises(ValidationError):
        AnalysisJobResponse(id="job_123", status="invalid_status")


def test_analysis_job_progress_bounds():
    job = AnalysisJobResponse(id="job_123", status="processing", progress=75)
    assert job.progress == 75

    with pytest.raises(ValidationError):
        AnalysisJobResponse(id="job_123", status="processing", progress=-5)

    with pytest.raises(ValidationError):
        AnalysisJobResponse(id="job_123", status="processing", progress=105)


# ==============================================================================
# 3. INCIDENT SCHEMA TESTS
# ==============================================================================

def test_incident_valid_synthetic(sample_synthetic_incident):
    inc = IncidentSchema(**sample_synthetic_incident)
    assert inc.id == sample_synthetic_incident["id"]
    assert inc.status == IncidentStatus.UNREVIEWED
    assert len(inc.frames) == 1
    assert len(inc.detections) == 1


def test_incident_rejects_invalid_status():
    """Status must strictly be unreviewed, confirmed, or dismissed."""
    with pytest.raises(ValidationError):
        IncidentSchema(
            id="INC-001",
            sourceId="src_01",
            createdAt="2026-10-16T12:00:00Z",
            status="threat_confirmed",  # Old invalid status from README
        )


def test_incident_rejects_invalid_iso_timestamp():
    with pytest.raises(ValidationError):
        IncidentSchema(
            id="INC-001",
            sourceId="src_01",
            createdAt="not-a-valid-date",
            status="unreviewed",
        )


# ==============================================================================
# 4. DISPATCH SCHEMA TESTS
# ==============================================================================

def test_dispatch_send_request_valid():
    req = DispatchSendRequest(incidentId="INC-001")
    assert req.incidentId == "INC-001"
    assert req.channel.value == "police_dispatch"


def test_dispatch_cancel_pin_numeric_validation():
    req = DispatchCancelRequest(pin="1234")
    assert req.pin == "1234"

    # Non-numeric
    with pytest.raises(ValidationError):
        DispatchCancelRequest(pin="abcd")

    # Too short (<4 digits)
    with pytest.raises(ValidationError):
        DispatchCancelRequest(pin="12")

    # Too long (>8 digits)
    with pytest.raises(ValidationError):
        DispatchCancelRequest(pin="123456789")


def test_dispatch_lifecycle_statuses():
    for status_val in ["not_sent", "pending", "sent", "failed", "cancelled"]:
        disp = DispatchResponse(id="disp_1", incidentId="INC-1", status=status_val)
        assert disp.status.value == status_val

    with pytest.raises(ValidationError):
        DispatchResponse(id="disp_1", incidentId="INC-1", status="dispatched")


# ==============================================================================
# 5. COMMON ERROR & PAGINATION SCHEMAS
# ==============================================================================

def test_error_response_schema():
    err = ErrorResponse(
        error="INVALID_PAYLOAD",
        message="Detailed explanation",
        details={"field": "targets"},
        request_id="req-test-123",
    )
    assert err.error == "INVALID_PAYLOAD"
    assert err.request_id == "req-test-123"


def test_pagination_meta_schema():
    meta = PaginationMeta(page=2, page_size=10, total_items=25, total_pages=3)
    assert meta.page == 2
    assert meta.total_pages == 3

    with pytest.raises(ValidationError):
        PaginationMeta(page=0, page_size=10, total_items=25, total_pages=3)
