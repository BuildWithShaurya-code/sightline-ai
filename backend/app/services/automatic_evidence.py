"""Save up to three real mask frames per owned camera episode, with no client-supplied predictions."""
import base64
import hashlib
import cv2
from starlette.concurrency import run_in_threadpool
from ..core.errors import ValidationError
from .storage import LocalMediaStorage

class AutomaticEvidenceService:
    def __init__(self, db, inference):
        self.db, self.inference = db, inference
        self.storage = LocalMediaStorage(inference.settings.media_dir)

    async def save(self, contents, owner, session, offset):
        episode = hashlib.sha256(f'auto:{owner}:{session}'.encode()).hexdigest()[:24]
        sample = hashlib.sha256(contents).hexdigest()[:24]
        inc_id, source_id, job_id = f'INC-AUTO-{episode.upper()}', f'src_auto_{episode}', f'job_auto_{episode}'
        ev_id = f'ev_auto_{episode}_{sample}'
        existing = await run_in_threadpool(self.db.get_incident, inc_id, owner)
        if existing and (len(existing['frames']) >= 3 or existing['status'] != 'unreviewed' or any(f['id']==ev_id for f in existing['frames'])):
            return existing
        result = await self.inference.infer_image_async(contents, 'mask', .25)
        if not any(d.classId == 'mask' for d in result.detections):
            raise ValidationError('No mask detected in this exact frame; automatic evidence was not saved.')
        # Storage and database calls are synchronous. Keep them off the event loop
        # so saving a photo cannot stall concurrent live camera inference.
        # Starlette copies the verified owner ContextVar into the worker thread.
        return await run_in_threadpool(self._save_result, contents, owner, episode, sample, offset, result)

    def _save_result(self, contents, owner, episode, sample, offset, result):
        inc_id, source_id, job_id = f'INC-AUTO-{episode.upper()}', f'src_auto_{episode}', f'job_auto_{episode}'
        ev_id = f'ev_auto_{episode}_{sample}'
        frame, width, height, _ = self.inference.decode_image_bytes(contents)
        ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY),90])
        if not ok: raise ValidationError('Evidence photo could not be encoded.')
        jpeg = encoded.tobytes()
        storage_key = self.storage.save_media(jpeg, 'automatic-mask.jpg', 'keyframes')
        dimensions = {'width':width,'height':height}
        ev = {'id':ev_id,'source_id':source_id,'user_id':owner,'storage_key':storage_key,
              'video_offset_seconds':offset,'media_dimensions':dimensions,
              'image_data_url':'data:image/jpeg;base64,'+base64.b64encode(jpeg).decode('ascii')}
        detections = [{'id':f'det_auto_{episode}_{sample}_{i}','source_id':source_id,'evidence_id':ev_id,
                       'class_id':d.classId,'class_name':d.className,'confidence':d.confidence,
                       'box':list(d.box),'frame_index':0,'video_offset_seconds':offset}
                      for i,d in enumerate(result.detections)]
        try:
            existing = self.db.get_incident(inc_id, owner)
            if not existing:
                source = {'id':source_id,'user_id':owner,'source_type':'camera_snapshot','original_filename':'Automatic mask evidence',
                          'storage_bucket':'evidence-frames','storage_key':storage_key,'media_dimensions':dimensions,'file_size_bytes':len(jpeg)}
                job = {'id':job_id,'source_id':source_id,'user_id':owner,'targets':['mask'],'status':'processing',
                       'model_version':result.model_version,'idempotency_key':f'auto:{episode}'}
                incident = {'id':inc_id,'source_id':source_id,'user_id':owner,'title':'Mask detected — automatic camera evidence',
                            'channel':'LIVE CAMERA','review_status':'unreviewed','severity':'high',
                            'reason':'Mask detected at or above 25% confidence; photos captured automatically for owner review.'}
                self.db.finalize_analysis_results(job_id,incident,[ev],detections,new_source=source,new_job=job)
            # Also handles two simultaneous first-frame requests; duplicates/cap are checked inside the transaction.
            self.db.append_automatic_evidence(inc_id,owner,job_id,ev,detections)
            saved = self.db.get_connection().execute('SELECT storage_key FROM evidence WHERE id=?',(ev_id,)).fetchone()
            if not saved or saved['storage_key'] != storage_key: self.storage.delete_media(storage_key)
        except Exception:
            # Never remove a file already committed by the first-frame transaction.
            referenced = self.db.get_connection().execute('SELECT 1 FROM evidence WHERE storage_key=?',(storage_key,)).fetchone()
            if not referenced: self.storage.delete_media(storage_key)
            raise
        return self.db.get_incident(inc_id, owner)
