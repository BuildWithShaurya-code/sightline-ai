"""
SightLine AI - Model Compatibility & Checkpoint Tests
Tests checkpoint presence, SHA256 integrity, architecture, and exact class equality.
"""

from pathlib import Path
from app.services.model_checker import ModelChecker, EXPECTED_CLASSES


def test_model_checkpoint_inspection():
    checker = ModelChecker(Path("models/best.pt"))
    info = checker.inspect_checkpoint()

    assert info["checkpoint_found"] is True
    assert info["model_compatible"] is True
    assert info["file_size_bytes"] == 5_451_802
    assert info["sha256"] == "0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8"
    assert info["classes_count"] == 3
    assert info["class_map"] == EXPECTED_CLASSES
    assert info["has_forbidden_classes"] is False
    assert info["model_loaded_in_api"] is False
    assert "DetectionModel" in info.get("architecture", "")


def test_model_capabilities_endpoint(client):
    """Test GET /api/v1/model/capabilities returns validated capabilities."""
    response = client.get("/api/v1/model/capabilities")
    assert response.status_code == 200
    data = response.json()

    assert data["model_id"] == "sightline-yolo11n-v1"
    assert data["supported_classes"] == ["person", "mask", "knife"]
    assert data["class_map"] == {"0": "person", "1": "mask", "2": "knife"}
    assert data["default_confidence_threshold"] == 0.25
    assert data["readiness"]["compatible"] is True
    assert data["readiness"]["model_loaded_in_api"] is True

