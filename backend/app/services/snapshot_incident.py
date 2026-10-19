"""Server-generated, owner-scoped camera alerts with atomic database persistence."""
import base64
import hashlib
import uuid

import cv2

from ..core.errors import ValidationError
from .storage import LocalMediaStorage


class SnapshotIncidentService:
    def __init__(self, db, inference):
        self.db = db
        self.inference = inference
        self.storage = LocalMediaStorage(inference.settings.media_dir)

    async def save(self, contents, user_id, targets=None, key=None, request_id=None):
        digest = hashlib.sha256(f"camera:{user_id}:{key or uuid.uuid4().hex}".encode()).hexdigest()[:24]
        incident_id, source_id, job_id, evidence_id = (
            f"INC-CAM-{digest.upper()}", f"src_cam_{digest}", f"job_cam_{digest}", f"ev_cam_{digest}")
        existing = self.db.get_incident(incident_id, user_id)
        if existing:
            return existing
        prediction = await self.inference.infer_image_async(contents, targets, None, request_id)
        if not prediction.detections:
            raise ValidationError("No selected targets were detected in this frame. No alert was saved.")
        frame, width, height, _ = self.inference.decode_image_bytes(contents)
        success, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not success:
            raise ValidationError("The camera evidence frame could not be encoded.")
        jpeg = encoded.tobytes()
        storage_key = self.storage.save_media(jpeg, 'camera.jpg', 'keyframes')
        dimensions = {'width': width, 'height': height}
        classes = sorted({d.classId for d in prediction.detections})
        source = {'id': source_id, 'user_id': user_id, 'source_type': 'camera_snapshot',
                  'original_filename': 'camera-snapshot.jpg', 'storage_bucket': 'evidence-frames',
                  'storage_key': storage_key, 'media_dimensions': dimensions, 'file_size_bytes': len(jpeg)}
        job = {'id': job_id, 'source_id': source_id, 'user_id': user_id, 'targets': prediction.targets,
               'confidence_threshold': prediction.confidence_threshold, 'status': 'processing',
               'idempotency_key': f'camera:{digest}'}
        incident = {'id': incident_id, 'source_id': source_id, 'user_id': user_id,
                    'title': f"Camera alert: {', '.join(classes)}", 'channel': 'LIVE CAMERA',
                    'review_status': 'unreviewed', 'reason': 'Operator saved model predictions for review.',
                    'severity': 'critical' if 'knife' in classes else 'high' if 'mask' in classes else 'medium'}
        evidence = [{'id': evidence_id, 'source_id': source_id, 'user_id': user_id,
                     'storage_key': storage_key, 'video_offset_seconds': 0, 'media_dimensions': dimensions,
                     'image_data_url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')}]
        detections = [{'id': f'det_cam_{digest}_{i}', 'source_id': source_id, 'evidence_id': evidence_id,
                       'class_id': d.classId, 'class_name': d.className, 'confidence': d.confidence,
                       'box': list(d.box), 'frame_index': 0, 'video_offset_seconds': 0}
                      for i, d in enumerate(prediction.detections)]
        try:
            self.db.finalize_analysis_results(job_id, incident, evidence, detections,
                                              new_source=source, new_job=job)
        except Exception:
            self.storage.delete_media(storage_key)
            raise
        # A concurrent idempotent request may already have committed its own file.
        stored = self.db.get_source(source_id, user_id)
        if stored['storage_key'] != storage_key:
            self.storage.delete_media(storage_key)
        return self.db.get_incident(incident_id, user_id)
