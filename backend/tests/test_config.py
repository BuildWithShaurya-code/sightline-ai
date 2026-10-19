"""
SightLine AI - Configuration Validation Tests
Tests edge cases, origins parsing, and safety invariants on Settings.
"""

import pytest
from pydantic import ValidationError
from app.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.environment in ["development", "production", "test"]
    assert settings.api_prefix == "/api/v1"
    assert settings.max_upload_size_bytes == 104_857_600
    assert settings.max_media_duration_seconds == 300
    assert settings.job_timeout_seconds == 600
    assert isinstance(settings.cors_origins, list)
    assert len(settings.cors_origins) > 0


def test_cors_origins_json_string_parsing():
    settings = Settings(cors_origins='["http://localhost:3000", "http://example.com"]')
    assert settings.cors_origins == ["http://localhost:3000", "http://example.com"]


def test_cors_origins_comma_separated_parsing():
    settings = Settings(cors_origins="http://localhost:3000, http://example.com")
    assert settings.cors_origins == ["http://localhost:3000", "http://example.com"]


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE")


def test_invalid_upload_limits_rejected():
    # Below 1MB minimum
    with pytest.raises(ValidationError):
        Settings(max_upload_size_bytes=500)

    # Above 1GB maximum
    with pytest.raises(ValidationError):
        Settings(max_upload_size_bytes=2_000_000_000)


def test_production_rejects_insecure_placeholder_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(
            environment="production",
            session_secret="development-insecure-placeholder-change-in-production",
        )
    assert "Production requires a strong session secret" in str(exc.value)
