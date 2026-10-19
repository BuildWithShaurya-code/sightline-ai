"""
SightLine AI - Dispatch & Revocation Schemas
Covers tactical dispatch requests, status tracking, provider delivery confirmations,
and secure PIN-based revocation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class DispatchStatus(str, Enum):
    NOT_SENT = "not_sent"
    PENDING = "pending"
    SENT = "sent"
    SIMULATED = "simulated"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNCERTAIN = "uncertain"


class DispatchNotificationChannel(str, Enum):
    TELEGRAM = "telegram"
    SIMULATED_CHANNEL = "simulated_channel"
    POLICE_DISPATCH = "police_dispatch"
    PRIVATE_SECURITY = "private_security"
    ONSITE_GUARD = "onsite_guard"
    AUDIBLE_ALARM = "audible_alarm"


class DispatchSendRequest(BaseModel):
    incidentId: str = Field(..., min_length=1, description="Incident ID to dispatch security for")
    channel: DispatchNotificationChannel = Field(
        default=DispatchNotificationChannel.POLICE_DISPATCH,
        description="Designated security notification channel",
    )
    destination_reference: Optional[str] = Field(
        None,
        description="Target precinct, dispatch queue, or contact number",
    )
    idempotency_key: Optional[str] = Field(
        None,
        description="Client-generated idempotency key preventing duplicate dispatches",
    )


class DispatchCancelRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, description="Operator security revocation PIN")

    @field_validator("pin")
    @classmethod
    def validate_pin_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Operator revocation PIN must be numeric digits")
        return v


class DispatchResponse(BaseModel):
    """Dispatch record compatible with frontend isValidDispatch()."""
    id: str = Field(..., min_length=1, description="Dispatch identifier")
    incidentId: str = Field(..., min_length=1, description="Associated incident ID")
    status: DispatchStatus = Field(..., description="Dispatch transmission status")
    provider: str = Field(default="simulated_provider", description="Notification provider used")
    provider_reference: Optional[str] = Field(None, description="External provider ticket or message ID")
    is_simulated: bool = Field(default=False, description="Whether this dispatch is explicitly simulated")
    destination_reference: Optional[str] = Field(None, description="Authorized recipient or destination")
    error: Optional[str] = Field(None, description="Failure reason if status is failed")
    failure_details: Optional[str] = Field(None, description="Diagnostic error details from provider")
    createdAt: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of dispatch transmission")
    deliveredAt: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of provider delivery acceptance")
    cancelledAt: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of cancellation")
    channel: Optional[DispatchNotificationChannel] = Field(None, description="Notification channel used")
    callSign: Optional[str] = Field(None, description="Dispatched unit callsign (e.g. 'UNIT-7')")
    etaMinutes: Optional[int] = Field(None, ge=0, description="Estimated response time in minutes")
    attempt_count: int = Field(default=1, ge=1, description="Number of transmission attempts")


class DispatchCancelResponse(BaseModel):
    success: bool = Field(..., description="Whether the revocation PIN was verified and cancellation accepted")
    dispatch: DispatchResponse = Field(..., description="Updated dispatch entity")
    message: Optional[str] = Field(None, description="Human-readable cancellation status message")
