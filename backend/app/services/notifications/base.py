"""
SightLine AI - Notification Provider Abstraction
Defines common interfaces, normalized provider outcomes, and payload models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class NotificationPayload:
    """Standardized threat alert payload formatted for notification channels."""
    incident_id: str
    timestamp: str
    review_status: str
    title: str
    channel_name: str
    zone: str
    detected_classes: List[str]
    detections: List[Dict[str, Any]]
    max_confidence: float
    keyframe_url: Optional[str] = None
    incident_url: Optional[str] = None
    reviewer_notes: Optional[str] = None


@dataclass
class ProviderResult:
    """Normalized output from any notification provider."""
    accepted: bool
    status: str  # 'sent', 'simulated', 'failed', 'uncertain'
    provider_name: str
    provider_reference: Optional[str] = None
    is_simulated: bool = False
    error_message: Optional[str] = None
    failure_details: Optional[str] = None
    retryable: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseNotificationProvider(ABC):
    """Abstract base class for all notification adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier."""
        pass

    @abstractmethod
    async def send_alert(
        self,
        payload: NotificationPayload,
        destination: str,
    ) -> ProviderResult:
        """
        Dispatches notification to destination and returns normalized result.
        Must not raise uncaught provider exceptions.
        """
        pass
