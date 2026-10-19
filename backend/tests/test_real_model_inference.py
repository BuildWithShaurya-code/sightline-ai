"""
SightLine AI - Real Model Inference Tests
Runs the actual trained YOLOv11n checkpoint against positive surveillance frames,
negative scenes, and harmless objects.
"""

from pathlib import Path
import cv2
from fastapi.testclient import TestClient

from backend.app.services.inference_service import InferenceService


def test_real_model_positive_person_cctv(client: TestClient, valid_auth_headers):
    """
    Evaluates real model on CCTV surveillance image (cctv_threat_feed_1792128851832.jpg).
    Must detect positive 'person' with high confidence (>0.85).
    """
    image_path = Path("src/assets/images/cctv_threat_feed_1792128851832.jpg")
    assert image_path.exists(), f"Required test fixture {image_path} missing!"

    image_bytes = image_path.read_bytes()

    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("cctv_person.jpg", image_bytes, "image/jpeg")},
        data={"targets": "person", "confidence_threshold": 0.25},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["original_width"] == 1200
    assert data["original_height"] == 896
    assert data["detections_count"] >= 1

    person_detections = [d for d in data["detections"] if d["classId"] == "person"]
    assert len(person_detections) >= 1

    top_person = person_detections[0]
    assert top_person["confidence"] >= 0.85
    assert top_person["className"] == "person"

    x1, y1, x2, y2 = top_person["box"]
    assert 0.0 <= x1 < x2 <= 1200.0
    assert 0.0 <= y1 < y2 <= 896.0


def test_real_model_positive_mask_detection(client: TestClient, valid_auth_headers):
    """
    Evaluates real model on Frame 53 from threat_footage_h264.mp4.
    Must detect positive 'mask' with confidence > 0.80.
    """
    video_path = Path("qa/data/threat_footage_h264.mp4")
    assert video_path.exists(), f"Video fixture {video_path} missing!"

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 53)
    ret, frame = cap.read()
    cap.release()
    assert ret, "Failed to read frame 53 from test video."

    _, encoded = cv2.imencode(".jpg", frame)
    frame_bytes = encoded.tobytes()

    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("frame_53.jpg", frame_bytes, "image/jpeg")},
        data={"targets": "mask", "confidence_threshold": 0.25},
    )

    assert response.status_code == 200
    data = response.json()

    mask_detections = [d for d in data["detections"] if d["classId"] == "mask"]
    assert len(mask_detections) >= 1
    assert mask_detections[0]["confidence"] >= 0.80


def test_real_model_negative_empty_scene(client: TestClient, valid_auth_headers):
    """Evaluates real model on empty room scene; must yield 0 detections (no false alarms)."""
    empty_scene_path = Path("qa/data/empty_scene.jpg")
    assert empty_scene_path.exists()

    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("empty.jpg", empty_scene_path.read_bytes(), "image/jpeg")},
        data={"targets": "person,mask,knife", "confidence_threshold": 0.25},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["detections_count"] == 0
    assert data["detections"] == []


def test_real_model_harmless_objects_no_false_alarm(client: TestClient, valid_auth_headers):
    """
    Evaluates harmless objects (mug, spoon, phone, plate);
    must NOT false-alarm as 'knife' or 'mask'.
    """
    harmless_path = Path("qa/data/harmless_objects.jpg")
    assert harmless_path.exists()

    response = client.post(
        "/api/v1/inference/image",
        headers=valid_auth_headers,
        files={"image": ("harmless.jpg", harmless_path.read_bytes(), "image/jpeg")},
        data={"targets": "knife,mask", "confidence_threshold": 0.25},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["detections_count"] == 0
    assert data["detections"] == []


def test_knife_evaluation_gap_documentation():
    """
    Truthful verification: verifies that checkpoint contains class index 2 ('knife'),
    while documenting that positive ground-truth knife footage was absent from repo.
    """
    service = InferenceService.get_instance()
    service.load_and_verify_model()
    class_map = service.get_readiness_info()["class_map"]
    assert class_map[2] == "knife"
