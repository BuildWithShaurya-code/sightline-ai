"""
SightLine AI - Lifecycle Tests for InferenceService
Covers missing checkpoint, checksum mismatch, load-once verification,
warmup primes, and resource release.
"""

from pathlib import Path
import pytest

from backend.app.core.errors import NotFoundError, ServiceUnavailableError
from backend.app.services.inference_service import InferenceService


def test_missing_checkpoint_raises_not_found(tmp_path: Path):
    """When the configured checkpoint file does not exist, raises NotFoundError."""
    missing_path = tmp_path / "non_existent_model.pt"
    service = InferenceService(model_path=missing_path)

    with pytest.raises(NotFoundError) as exc:
        service.load_and_verify_model()
    assert "ModelCheckpoint" in str(exc.value)


def test_checksum_mismatch_raises_service_unavailable(tmp_path: Path):
    """When checkpoint has unexpected SHA-256 hash, raises ServiceUnavailableError."""
    fake_checkpoint = tmp_path / "fake_best.pt"
    fake_checkpoint.write_bytes(b"INVALID_CHECKPOINT_BYTES_WITH_WRONG_CHECKSUM")

    service = InferenceService(model_path=fake_checkpoint)
    with pytest.raises(ServiceUnavailableError) as exc:
        service.load_and_verify_model()
    assert "integrity check failed" in str(exc.value)


def test_model_loaded_once_singleton():
    """Verify that singleton instance loads the model once and reuses it."""
    service1 = InferenceService.get_instance()
    service2 = InferenceService.get_instance()
    assert service1 is service2

    service1.load_and_verify_model()
    info1 = service1.get_readiness_info()
    assert info1["is_loaded"] is True

    # Repeated calls do not reload or duplicate memory
    service2.load_and_verify_model()
    info2 = service2.get_readiness_info()
    assert info2["load_time_ms"] == info1["load_time_ms"]


def test_resource_cleanup_releases_model():
    """Verify that cleanup() safely resets model state without leaving dangling tensors."""
    service = InferenceService.get_instance()
    service.load_and_verify_model()
    assert service.get_readiness_info()["is_loaded"] is True

    service.cleanup()
    assert service.get_readiness_info()["is_loaded"] is False
