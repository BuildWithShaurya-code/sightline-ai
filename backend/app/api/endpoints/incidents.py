"""
SightLine AI - Incident Management Endpoints
Provides authenticated incident listing with pagination/search,
detailed retrieval with keyframe evidence & bounding boxes, operator review updates, and soft deletion.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status, File, Form, Header, Request, UploadFile

from ...core.auth import AuthenticatedUser, get_current_user
from ...core.errors import NotFoundError, ValidationError
from ...db.database import DatabaseManager
from ...schemas.common import PaginatedResponse, PaginationMeta
from ...schemas.incident import IncidentReviewRequest, IncidentSchema

logger = logging.getLogger("sightline.api.incidents")
router = APIRouter(prefix="/incidents", tags=["Incidents"])

db_manager = DatabaseManager.get_instance()


@router.get(
    "",
    response_model=PaginatedResponse[IncidentSchema],
    summary="List authenticated operator incidents with search and pagination",
    description="Returns incidents owned by authenticated user. Supports status filter, textual search, and stable pagination.",
)
def list_incidents(
    q: Optional[str] = Query(None, description="Search query across title, channel, zone, ID"),
    status: Optional[str] = Query(None, description="Filter by review status ('unreviewed', 'confirmed', 'dismissed')"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    created_after: Optional[datetime] = Query(None, description="Inclusive timezone-aware date cutoff before pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PaginatedResponse[IncidentSchema]:
    """
    Paginated incident list endpoint.
    Strictly isolated to incidents belonging to the verified caller.
    """
    if created_after is not None and created_after.tzinfo is None:
        raise ValidationError("created_after must include a timezone")
    res = db_manager.list_incidents(
        user_id=current_user.id,
        status=status,
        search_query=q,
        page=page,
        page_size=page_size,
        created_after=created_after.astimezone(timezone.utc).isoformat() if created_after else None,
    )

    items = [IncidentSchema(**item) for item in res["items"]]
    pagination = PaginationMeta(**res["pagination"])

    return PaginatedResponse[IncidentSchema](
        items=items,
        pagination=pagination,
    )


from ...schemas.security_response import ResponseContacts, ResponseAction
from ...services.security_response import get_response, add_response

@router.get('/response-contacts', response_model=ResponseContacts)
def response_contacts(current_user: AuthenticatedUser = Depends(get_current_user)):
    row = db_manager.get_connection().execute('SELECT securityName,securityPhone,policePhone,siteAddress FROM response_contacts WHERE user_id=?', (current_user.id,)).fetchone()
    return ResponseContacts(**dict(row)) if row else ResponseContacts()

@router.put('/response-contacts', response_model=ResponseContacts)
def save_response_contacts(payload: ResponseContacts, current_user: AuthenticatedUser = Depends(get_current_user)):
    db_manager.get_connection().execute("""INSERT INTO response_contacts(user_id,securityName,securityPhone,policePhone,siteAddress) VALUES(?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET securityName=excluded.securityName, securityPhone=excluded.securityPhone, policePhone=excluded.policePhone, siteAddress=excluded.siteAddress""",
        (current_user.id,payload.securityName,payload.securityPhone,payload.policePhone,payload.siteAddress))
    return payload

@router.get('/{id}/response')
def incident_response(id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    return get_response(db_manager, id, current_user.id)

@router.post('/{id}/response')
def record_response(id: str, payload: ResponseAction, current_user: AuthenticatedUser = Depends(get_current_user)):
    return add_response(db_manager, id, current_user.id, payload)

@router.post("/from-frame", response_model=IncidentSchema, status_code=201,
             summary="Analyze and save an operator-selected camera frame as an unreviewed alert")
async def save_camera_frame(
    request: Request,
    image: UploadFile = File(...),
    targets: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    from ...services.snapshot_incident import SnapshotIncidentService
    from ...services.inference_service import InferenceService
    from .inference import get_inference_semaphore
    service = InferenceService.get_instance()
    contents = await image.read(service.settings.max_inference_image_bytes + 1)
    async with get_inference_semaphore():
        result = await SnapshotIncidentService(db_manager, service).save(
            contents, current_user.id, targets, idempotency_key,
            getattr(request.state, "request_id", None),
        )
    return IncidentSchema(**result)


@router.post('/auto-evidence', response_model=IncidentSchema, status_code=201)
async def automatic_mask_evidence(
    image: UploadFile = File(...), session_key: str = Form(..., min_length=1, max_length=128),
    time_seconds: float = Form(0, ge=0, le=86400),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    from ...services.automatic_evidence import AutomaticEvidenceService
    from ...services.inference_service import InferenceService
    from .inference import get_inference_semaphore
    service = InferenceService.get_instance()
    contents = await image.read(service.settings.max_inference_image_bytes+1)
    async with get_inference_semaphore():
        incident = await AutomaticEvidenceService(db_manager,service).save(contents,current_user.id,session_key,time_seconds)
    return IncidentSchema(**incident)


@router.post("/manual-camera", response_model=IncidentSchema, status_code=201,
             summary="Save an operator-reported camera alert without a photo or model detections")
def create_manual_camera_alert(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    from ...services.manual_camera_alert import save_manual_camera_alert
    return IncidentSchema(**save_manual_camera_alert(db_manager, current_user.id, idempotency_key))


@router.post("/{id}/false-alarm", response_model=IncidentSchema,
             summary="Dismiss an owned incident and clear its evidence from operator views")
def dismiss_false_alarm(id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    result = db_manager.dismiss_and_clear_evidence(id, current_user.id)
    if not result:
        raise NotFoundError("Incident", id)
    return IncidentSchema(**result)


@router.get(
    "/{id}",
    response_model=IncidentSchema,
    summary="Retrieve incident details with keyframe evidence and detections",
    description="Returns full incident details including evidence frames and model detection bounding boxes in original pixel coordinates.",
)
def get_incident(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> IncidentSchema:
    """
    Retrieves a single incident for verified owner.
    Rejects cross-owner queries with 404.
    """
    inc = db_manager.get_incident(incident_id=id, user_id=current_user.id)
    if not inc:
        raise NotFoundError("Incident", id)

    return IncidentSchema(**inc)


@router.patch(
    "/{id}",
    response_model=IncidentSchema,
    summary="Operator review update for an incident",
    description="Updates review status ('confirmed' or 'dismissed') with operator ID, timestamp, and optional rationale notes.",
)
def review_incident(
    id: str,
    payload: IncidentReviewRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> IncidentSchema:
    """
    Performs human operator review decision transition.
    Records reviewer identity and UTC timestamp.
    """
    updated = db_manager.update_incident_review(
        incident_id=id,
        user_id=current_user.id,
        new_status=payload.status.value,
        reviewer_id=current_user.id,
        reviewer_notes=payload.reason,
    )
    if not updated:
        raise NotFoundError("Incident", id)

    return IncidentSchema(**updated)


@router.delete(
    "/{id}",
    summary="Soft-delete an incident from active operator history",
    description="Soft-deletes incident record. Active media source files are preserved for referential integrity.",
)
def delete_incident(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Soft-deletes incident for owner. Rejects cross-owner deletion.
    """
    deleted = db_manager.soft_delete_incident(incident_id=id, user_id=current_user.id)
    if not deleted:
        raise NotFoundError("Incident", id)

    return {
        "success": True,
        "id": id,
        "deleted": True,
    }
