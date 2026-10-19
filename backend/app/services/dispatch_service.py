"""
SightLine AI - Dispatch Service Layer
Orchestrates notification dispatch requests, idempotency enforcement, provider routing,
audit trail logging, and secure PIN-based revocation.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid

from ..config import Settings, get_settings
from ..core.auth import AuthenticatedUser
from ..core.errors import AuthorizationError, NotFoundError, ValidationError
from ..db.database import DatabaseManager
from ..schemas.dispatch import (
    DispatchCancelResponse,
    DispatchNotificationChannel,
    DispatchResponse,
    DispatchStatus,
)
from .notifications.base import BaseNotificationProvider, NotificationPayload, ProviderResult
from .notifications.simulation import SimulationProvider
from .notifications.telegram import TelegramProvider

logger = logging.getLogger("sightline.dispatch")


class DispatchService:
    """Service handling incident notifications and secure revocation."""

    def __init__(self, db: Optional[DatabaseManager] = None, settings: Optional[Settings] = None):
        self.db = db or DatabaseManager.get_instance()
        self.settings = settings or get_settings()

    def _get_provider(self, requested_channel: Optional[DispatchNotificationChannel] = None) -> BaseNotificationProvider:
        """Selects the appropriate provider based on settings and channel."""
        provider_type = self.settings.dispatch_provider.lower()

        # If telegram is configured and token is present
        if provider_type == "telegram" and self.settings.telegram_bot_token:
            return TelegramProvider(
                bot_token=self.settings.telegram_bot_token,
                default_chat_id=self.settings.telegram_chat_id,
                timeout_seconds=self.settings.dispatch_timeout_seconds,
            )

        # Explicit simulation provider
        return SimulationProvider()

    async def send_dispatch(
        self,
        incident_id: str,
        current_user: AuthenticatedUser,
        channel: DispatchNotificationChannel = DispatchNotificationChannel.TELEGRAM,
        destination_reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> DispatchResponse:
        """
        Submits and executes an emergency notification dispatch for a verified incident.
        """
        # 1. Verify Incident Ownership and Eligibility
        incident = self.db.get_incident(incident_id, user_id=current_user.id)
        if not incident:
            # Check if incident exists at all for security/privacy isolation
            other_user_inc = self.db.get_incident(incident_id)
            if other_user_inc:
                logger.warning(
                    "Tenant isolation: User [%s] attempted to dispatch unauthorized incident [%s]",
                    current_user.id,
                    incident_id,
                )
                raise NotFoundError("Incident", incident_id)
            raise NotFoundError("Incident", incident_id)

        # Enforce review rules: prefer explicit confirmation before dispatch
        review_status = incident.get("status") or incident.get("review_status", "unreviewed")
        if review_status == "dismissed":
            raise ValidationError(
                f"Cannot dispatch notification for dismissed incident #{incident_id}. Threat was cleared by operator review."
            )
        if review_status != "confirmed":
            raise ValidationError("Operator confirmation is required before sending a notification.")

        # 2. Check Idempotency Key
        if idempotency_key:
            existing_by_key = self.db.get_dispatch_by_idempotency_key(idempotency_key, user_id=current_user.id)
            if existing_by_key:
                logger.info(
                    "Idempotent replay detected for dispatch idempotency_key [%s] (Dispatch #%s)",
                    idempotency_key,
                    existing_by_key["id"],
                )
                return DispatchResponse(**existing_by_key)

        # 3. Check for existing dispatch on this incident
        existing_dispatch = self.db.get_dispatch_by_incident(incident_id, user_id=current_user.id)
        if existing_dispatch:
            st = existing_dispatch.get("status")
            if st in ("sent", "simulated", "pending"):
                logger.info(
                    "Incident #%s already has active dispatch #%s with status [%s]. Returning existing record.",
                    incident_id,
                    existing_dispatch["id"],
                    st,
                )
                return DispatchResponse(**existing_dispatch)

        # 4. Prepare Destination
        provider = self._get_provider(channel)
        is_simulation = provider.name == "simulated_provider"

        # Server-enforced destination validation
        if provider.name == "telegram":
            # Must use server-authorized destination or configured default
            dest = self.settings.telegram_chat_id or destination_reference or "authorized_telegram_chat"
        else:
            dest = destination_reference or "simulated_terminal_destination"

        dispatch_id = f"disp_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # 5. Persist initial queued/pending dispatch in database
        dispatch_record = {
            "id": dispatch_id,
            "incident_id": incident_id,
            "user_id": current_user.id,
            "channel": channel.value,
            "destination_reference": dest,
            "provider": provider.name,
            "provider_reference": None,
            "idempotency_key": idempotency_key or f"auto_{dispatch_id}",
            "status": DispatchStatus.PENDING.value,
            "is_simulated": is_simulation,
            "failure_reason": None,
            "attempt_count": 1,
            "delivered_at": None,
            "cancelled_at": None,
            "cancelled_by": None,
            "created_at": now,
            "updated_at": now,
        }
        created = self.db.create_dispatch(dispatch_record)

        # Record audit event: DISPATCH_REQUESTED
        self.db.record_audit_event(
            actor_id=current_user.id,
            action="DISPATCH_REQUESTED",
            resource_type="dispatch",
            resource_id=dispatch_id,
            request_id=request_id,
            metadata={
                "incident_id": incident_id,
                "provider": provider.name,
                "is_simulation": is_simulation,
                "channel": channel.value,
            },
        )

        # 6. Build Notification Payload
        detections = incident.get("detections", [])
        classes = list(dict.fromkeys(d.get("classId") or d.get("className", "threat") for d in detections))
        confidences = [d.get("confidence", 0.0) for d in detections if d.get("confidence") is not None]
        max_conf = max(confidences) if confidences else 0.85

        keyframe_url = None
        frames = incident.get("frames", [])
        if frames:
            keyframe_url = frames[0].get("imageDataUrl")

        payload = NotificationPayload(
            incident_id=incident_id,
            timestamp=incident.get("createdAt") or incident.get("created_at") or now,
            review_status=review_status,
            title=incident.get("title") or f"Threat Alert: {', '.join(classes)}",
            channel_name=incident.get("channel") or "Surveillance Node",
            zone=incident.get("zone") or "Primary Security Perimeter",
            detected_classes=classes,
            detections=detections,
            max_confidence=max_conf,
            keyframe_url=keyframe_url,
            incident_url=f"/#/threat-detail/{incident_id}",
            reviewer_notes=incident.get("reviewer_notes"),
        )

        # 7. Execute Sending through Provider
        result: ProviderResult = await provider.send_alert(payload, dest)

        # 8. Transactionally update dispatch record with final provider outcome
        update_fields: Dict[str, Any] = {
            "status": result.status,
            "provider_reference": result.provider_reference,
            "is_simulated": result.is_simulated,
            "failure_reason": result.error_message,
        }
        # Provider acceptance and simulation do not prove delivery to a recipient.

        updated = self.db.update_dispatch(dispatch_id, update_fields)

        # Record audit event: DISPATCH_COMPLETED / DISPATCH_FAILED
        audit_action = "DISPATCH_ACCEPTED" if result.accepted else "DISPATCH_FAILED"
        self.db.record_audit_event(
            actor_id=current_user.id,
            action=audit_action,
            resource_type="dispatch",
            resource_id=dispatch_id,
            request_id=request_id,
            metadata={
                "status": result.status,
                "provider": provider.name,
                "provider_reference": result.provider_reference,
                "error": result.error_message,
            },
        )

        return DispatchResponse(**(updated or created))

    def cancel_dispatch(
        self,
        dispatch_id: str,
        current_user: AuthenticatedUser,
        pin: str,
        request_id: Optional[str] = None,
    ) -> DispatchCancelResponse:
        """
        Securely cancels/revokes a dispatch after server-side cryptographic PIN verification.
        """
        if not self.db.get_dispatch(dispatch_id, user_id=current_user.id):
            raise NotFoundError("Dispatch", dispatch_id)

        # 1. Verify Operator PIN on Server
        # Raises LockedError (HTTP 423) or ValidationError (HTTP 422) if invalid
        self.db.verify_operator_pin(
            user_id=current_user.id,
            pin=pin,
            max_attempts=self.settings.pin_max_attempts,
            lockout_seconds=self.settings.pin_lockout_seconds,
        )

        # 2. Attempt Atomic Database Cancellation
        success, dispatch_dict, message = self.db.cancel_dispatch(dispatch_id, current_user.id)
        if not dispatch_dict:
            raise NotFoundError("Dispatch", dispatch_id)

        # Record audit event: DISPATCH_CANCELLED
        self.db.record_audit_event(
            actor_id=current_user.id,
            action="DISPATCH_REVOKED" if success else "DISPATCH_REVOKE_REJECTED",
            resource_type="dispatch",
            resource_id=dispatch_id,
            request_id=request_id,
            metadata={
                "success": success,
                "message": message,
                "status": dispatch_dict.get("status"),
            },
        )

        return DispatchCancelResponse(
            success=success,
            dispatch=DispatchResponse(**dispatch_dict),
            message=message,
        )

    def get_dispatch(self, dispatch_id: str, current_user: AuthenticatedUser) -> DispatchResponse:
        """Retrieves dispatch by ID with tenant isolation."""
        disp = self.db.get_dispatch(dispatch_id, user_id=current_user.id)
        if not disp:
            # Check tenant isolation
            if self.db.get_dispatch(dispatch_id):
                logger.warning(
                    "Tenant isolation: User [%s] attempted to inspect unauthorized dispatch [%s]",
                    current_user.id,
                    dispatch_id,
                )
            raise NotFoundError("Dispatch", dispatch_id)
        return DispatchResponse(**disp)

    def get_dispatch_by_incident(self, incident_id: str, current_user: AuthenticatedUser) -> Optional[DispatchResponse]:
        """Retrieves active dispatch for an incident."""
        disp = self.db.get_dispatch_by_incident(incident_id, user_id=current_user.id)
        if not disp:
            return None
        return DispatchResponse(**disp)
