"""
SightLine AI - Dispatch & Security Revocation Endpoints
Handles emergency alert dispatches, outcome tracking, and secure PIN-based revocation.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field, SecretStr

from ...config import Settings, get_settings
from ...core.auth import AuthenticatedUser, get_current_user
from ...db.database import DatabaseManager
from ...schemas.dispatch import (
    DispatchCancelRequest,
    DispatchCancelResponse,
    DispatchResponse,
    DispatchSendRequest,
)
from ...services.dispatch_service import DispatchService

router = APIRouter(prefix="/dispatches", tags=["Dispatches"])


def get_dispatch_service(
    settings: Settings = Depends(get_settings),
) -> DispatchService:
    return DispatchService(db=DatabaseManager.get_instance(), settings=settings)


@router.post(
    "/send",
    response_model=DispatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch verified threat notification to authorized destination",
)
async def send_dispatch(
    payload: DispatchSendRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: DispatchService = Depends(get_dispatch_service),
) -> DispatchResponse:
    """
    Initiates an emergency threat notification for an operator-reviewed incident.
    Enforces tenant ownership, review state verification, and idempotency protection.
    """
    idempotency_key = idempotency_key_header or payload.idempotency_key
    req_id = getattr(request.state, "request_id", None)

    return await service.send_dispatch(
        incident_id=payload.incidentId,
        current_user=current_user,
        channel=payload.channel,
        destination_reference=payload.destination_reference,
        idempotency_key=idempotency_key,
        request_id=req_id,
    )


@router.post(
    "/{dispatch_id}/cancel",
    response_model=DispatchCancelResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke active dispatch with operator security PIN verification",
)
async def cancel_dispatch(
    dispatch_id: str,
    payload: DispatchCancelRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: DispatchService = Depends(get_dispatch_service),
) -> DispatchCancelResponse:
    """
    Revokes a pending dispatch request.
    Verifies operator security PIN server-side with persistent attempt counting and lockout.
    """
    req_id = getattr(request.state, "request_id", None)
    return service.cancel_dispatch(
        dispatch_id=dispatch_id,
        current_user=current_user,
        pin=payload.pin,
        request_id=req_id,
    )


@router.get(
    "/{dispatch_id}",
    response_model=DispatchResponse,
    summary="Query status and delivery outcome of a dispatch",
)
async def get_dispatch(
    dispatch_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: DispatchService = Depends(get_dispatch_service),
) -> DispatchResponse:
    """Retrieves current dispatch status and provider delivery confirmation."""
    return service.get_dispatch(dispatch_id=dispatch_id, current_user=current_user)


@router.get(
    "/incident/{incident_id}",
    response_model=Optional[DispatchResponse],
    summary="Retrieve active dispatch linked to an incident",
)
async def get_incident_dispatch(
    incident_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: DispatchService = Depends(get_dispatch_service),
) -> Optional[DispatchResponse]:
    """Retrieves the latest dispatch associated with an incident if one exists."""
    return service.get_dispatch_by_incident(incident_id=incident_id, current_user=current_user)


# PINs are owner-selected; no known default or legacy hash is accepted.
class PinSetupRequest(BaseModel):
    pin: SecretStr = Field(min_length=4, max_length=8)
    currentPin: Optional[SecretStr] = Field(default=None, min_length=4, max_length=8)


@router.get('/security/pin', summary='Check whether this owner has configured a security PIN')
async def pin_status(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {'configured': DatabaseManager.get_instance().has_operator_pin(current_user.id)}


@router.post('/security/pin', summary='Set your first PIN or change it using your current PIN')
async def configure_pin(payload: PinSetupRequest, current_user: AuthenticatedUser = Depends(get_current_user),
                        expected_owner: Optional[str] = Header(default=None, alias='X-Expected-Owner')):
    from ...core.errors import AuthorizationError
    if expected_owner and expected_owner != current_user.id:
        raise AuthorizationError('Account changed. Reopen Account settings before continuing.')
    db = DatabaseManager.get_instance()
    db.configure_operator_pin(current_user.id, payload.pin.get_secret_value(),
        payload.currentPin.get_secret_value() if payload.currentPin else None)
    return {'success': True, 'message': 'Security PIN saved.'}
