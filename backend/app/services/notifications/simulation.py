"""
SightLine AI - Simulation Notification Provider
Provides safe, explicitly labeled simulation for demos and tests without external API dependencies.
"""

import logging
import uuid
from .base import BaseNotificationProvider, NotificationPayload, ProviderResult

logger = logging.getLogger("sightline.notifications.simulation")


class SimulationProvider(BaseNotificationProvider):
    """Explicitly labeled simulation provider."""

    @property
    def name(self) -> str:
        return "simulated_provider"

    async def send_alert(
        self,
        payload: NotificationPayload,
        destination: str,
    ) -> ProviderResult:
        logger.info(
            "[SIMULATION NOTIFIER] Simulating alert dispatch for Incident #%s to destination [%s]. Threats: %s",
            payload.incident_id,
            destination,
            payload.detected_classes,
        )

        sim_ref = f"SIM-ALERT-{uuid.uuid4().hex[:8].upper()}"
        return ProviderResult(
            accepted=True,
            status="simulated",
            provider_name=self.name,
            provider_reference=sim_ref,
            is_simulated=True,
            error_message=None,
            failure_details=None,
            retryable=False,
        )
