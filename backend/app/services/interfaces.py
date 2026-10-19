"""
SightLine AI - Future Service Interfaces
Abstract Protocols defining boundaries between the API layer and future subsystem implementations.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from ..schemas.analysis import AnalysisJobResponse
from ..schemas.dispatch import DispatchResponse
from ..schemas.incident import IncidentSchema


class MediaStorageInterface(Protocol):
    """Abstraction for saving, retrieving, and validating media assets."""

    def save_media(self, content: bytes, filename: str, subfolder: str = "videos") -> str:
        """Saves media bytes and returns a relative URI or storage path."""
        ...

    def get_media_path(self, relative_path: str) -> Path:
        """Resolves relative storage path to a validated filesystem path."""
        ...

    def delete_media(self, relative_path: str) -> bool:
        """Deletes media asset from storage."""
        ...

    def is_writable(self) -> bool:
        """Verifies that the underlying storage medium is writable."""
        ...


class InferenceWorkerInterface(Protocol):
    """Abstraction for submitting and managing asynchronous neural detection tasks."""

    def submit_job(
        self,
        source_id: str,
        targets: List[str],
        confidence_threshold: float = 0.25,
        sample_rate_sec: float = 0.5,
    ) -> str:
        """Submits video analysis job to processing worker and returns jobId."""
        ...

    def get_job(self, job_id: str) -> Optional[AnalysisJobResponse]:
        """Queries processing state and progress metrics for a job."""
        ...

    def cancel_job(self, job_id: str) -> bool:
        """Requests premature cancellation of an active inference job."""
        ...


class IncidentRepositoryInterface(Protocol):
    """Abstraction for persistent storage of incidents, frames, and review status."""

    def get_incident(self, incident_id: str) -> Optional[IncidentSchema]:
        """Retrieves single incident by ID."""
        ...

    def save_incident(self, incident: IncidentSchema) -> IncidentSchema:
        """Persists or updates an incident record."""
        ...

    def list_incidents(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns paginated incidents list with metadata."""
        ...


class DispatchNotifierInterface(Protocol):
    """Abstraction for communicating alerts to police, guard services, or external dispatch queues."""

    def send_dispatch(self, incident_id: str, channel: str) -> DispatchResponse:
        """Dispatches emergency notification to external provider."""
        ...

    def cancel_dispatch(self, dispatch_id: str, pin: str) -> DispatchResponse:
        """Revokes active dispatch with security PIN verification."""
        ...
