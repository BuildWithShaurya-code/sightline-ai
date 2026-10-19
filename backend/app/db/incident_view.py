"""Identical incident wire representation for detail and bulk history reads."""
import json

def incident_view(row, evidence_rows, detection_rows, response_label):
    inc = dict(row)
    frames = []
    for ev in evidence_rows:
        frames.append({
            "id": ev["id"],
            "timeSeconds": ev["video_offset_seconds"] or 0.0,
            "imageDataUrl": ev["image_data_url"] or f"/api/v1/evidence/{ev['id']}/image",
        })
    inc["frames"] = frames

    detections = []
    for d in detection_rows:
        box_parsed = json.loads(d["box"]) if d["box"] else [0, 0, 0, 0]
        detections.append({
            "detection_id": d["id"],
            "classId": d["class_id"],
            "className": d["class_name"],
            "confidence": round(float(d["confidence"]), 4),
            "box": box_parsed,
            "evidence_id": d["evidence_id"],
            "frame_index": d["frame_index"],
            "video_offset_seconds": d["video_offset_seconds"],
        })
    inc["detections"] = detections

    # Map to frontend field names
    inc["sourceId"] = inc["source_id"]
    inc["createdAt"] = inc["created_at"]
    inc["status"] = inc["review_status"]
    if frames and not inc.get("thumbnail"):
        inc["thumbnail"] = frames[0]["imageDataUrl"]
    if inc.get("reviewer_notes"):
        inc["review_reason"] = inc["reviewer_notes"]

    if inc.get("evidence_cleared"):
        inc["frames"] = []
        inc["detections"] = []
        inc["thumbnail"] = None
    inc['responseStatus'] = response_label
    return inc
