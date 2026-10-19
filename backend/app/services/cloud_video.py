"""Direct-to-private-storage video uploads avoid Vercel's request body limit."""
from pathlib import Path
import uuid
import cv2

from ..config import get_settings
from ..core.errors import NotFoundError, ValidationError, ServiceUnavailableError
from ..db.database import DatabaseManager
from .cloud_storage import CloudStorage
from .storage import LocalMediaStorage
from .video_service import ALLOWED_EXTENSIONS


class CloudVideoService:
    def __init__(self):
        self.settings = get_settings()
        if self.settings.storage_backend != 'supabase':
            raise ServiceUnavailableError('Direct cloud uploads are not enabled.')
        self.db = DatabaseManager.get_instance()
        self.storage = CloudStorage(self.settings)

    def begin(self, owner, filename, size):
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError('Choose an MP4, AVI, MOV, MKV or WebM video.')
        if size <= 0 or size > self.settings.max_upload_size_bytes:
            raise ValidationError('Choose a non-empty video within the upload size limit.')
        source_id = 'src_' + uuid.uuid4().hex
        key = f'{owner}/{source_id}/{source_id}{ext}'
        self.db.create_source({'id':source_id,'user_id':owner,'original_filename':Path(filename).name,
                              'storage_key':key,'status':'awaiting_upload','file_size_bytes':size})
        return {'sourceId':source_id,'uploadUrl':self.storage.signed_upload(key)}

    def complete(self, owner, source_id):
        source = self.db.get_source(source_id, owner)
        if not source:
            raise NotFoundError('VideoSource', source_id)
        if source['status'] == 'ready':
            return {'sourceId':source_id,'videoUrl':f'/api/v1/videos/{source_id}/playback'}
        if source['status'] != 'awaiting_upload':
            raise ValidationError('This upload cannot be completed. Please upload the video again.')
        ext = Path(source['original_filename']).suffix.lower()
        scratch = LocalMediaStorage(self.settings.media_dir).get_media_path(f'temp/validate_{source_id}_{uuid.uuid4().hex}{ext}')
        try:
            size = self.storage.download('source-videos',source['storage_key'],scratch,self.settings.max_upload_size_bytes)
            if size != source['file_size_bytes']:
                raise ValidationError('The uploaded video size does not match. Please upload it again.')
            cap = cv2.VideoCapture(str(scratch))
            try:
                if not cap.isOpened():
                    raise ValidationError('This video could not be decoded.')
                width,height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps,frames = cap.get(cv2.CAP_PROP_FPS),cap.get(cv2.CAP_PROP_FRAME_COUNT)
                ok,_ = cap.read()
                if not ok or min(width,height,fps,frames)<=0 or frames/fps>self.settings.max_media_duration_seconds:
                    raise ValidationError('This video is invalid or exceeds the duration limit.')
            finally:
                cap.release()
            import json
            from datetime import datetime,timezone
            self.db.get_connection().execute("UPDATE sources SET status='ready',media_dimensions=?,duration_seconds=?,updated_at=? WHERE id=? AND user_id=? AND status='awaiting_upload'",(json.dumps({'width':width,'height':height}),round(frames/fps,2),datetime.now(timezone.utc).isoformat(),source_id,owner))
            return {'sourceId':source_id,'videoUrl':f'/api/v1/videos/{source_id}/playback'}
        finally:
            scratch.unlink(missing_ok=True)

    def playback(self, owner, source_id):
        source = self.db.get_source(source_id, owner)
        if not source or source['status']!='ready':
            raise NotFoundError('VideoSource', source_id)
        return self.storage.signed_urls('source-videos',[source['storage_key']])[source['storage_key']]
