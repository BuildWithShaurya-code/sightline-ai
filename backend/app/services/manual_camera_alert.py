"""Operator-reported camera alerts without an evidence capture."""
import hashlib
import uuid


def save_manual_camera_alert(db, user_id, key=None):
    digest = hashlib.sha256(f"manual:{user_id}:{key or uuid.uuid4().hex}".encode()).hexdigest()[:24]
    incident_id, source_id, job_id = f"INC-MAN-{digest.upper()}", f"src_manual_{digest}", f"job_manual_{digest}"
    existing = db.get_incident(incident_id, user_id)
    if existing:
        return existing
    source = {"id": source_id, "user_id": user_id, "source_type": "webcam_session",
              "original_filename": "Operator camera alert (no photo)", "storage_key": f"manual-no-media/{digest}", "file_size_bytes": 0}
    job = {"id": job_id, "source_id": source_id, "user_id": user_id, "targets": [],
           "model_version": "operator-reported", "status": "processing", "idempotency_key": f"manual:{digest}"}
    incident = {"id": incident_id, "source_id": source_id, "user_id": user_id,
                "title": "Operator camera alert", "channel": "LIVE CAMERA", "review_status": "unreviewed",
                "severity": "medium", "reason": "Operator triggered an alert without capturing a photo; no model result is attached."}
    db.finalize_analysis_results(job_id, incident, [], [], new_source=source, new_job=job)
    return db.get_incident(incident_id, user_id)
