"""Durable Vercel daemon. Claims persisted jobs; no web-request background tasks."""
import logging
import os
import signal
import threading
import time
import uuid

from .config import get_settings


class CloudRunnerProxy:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
    @property
    def ready(self):
        try:
            return self.db.worker_ready()
        except Exception:
            return False
    def wake(self):
        pass  # The independently running daemon polls the durable queue.
    def close(self):
        return True


def run():
    settings = get_settings()
    if settings.storage_backend != 'supabase' or not settings.cloud_worker:
        raise RuntimeError('A durable worker requires explicit private cloud configuration.')
    from .core.logging import setup_logging
    from .db.database import DatabaseManager
    from .services.cloud_storage import hydrate_model
    from .services.inference_service import InferenceService
    from .services.video_worker import VideoWorker
    setup_logging(settings.log_level)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    hydrate_model(settings)
    inference = InferenceService.get_instance()
    inference.load_and_verify_model()
    db = DatabaseManager.get_instance()
    worker_id = 'cloud_' + uuid.uuid4().hex
    worker = VideoWorker(worker_id=worker_id, db=db, inference_service=inference, stop_event=stop)

    def heartbeat():
        while not stop.is_set():
            try:
                db.heartbeat(worker_id)
            except Exception:
                logging.getLogger('sightline.worker').error('Cloud worker heartbeat failed.')
            stop.wait(10)

    thread = threading.Thread(target=heartbeat, name='cloud-worker-heartbeat', daemon=True)
    thread.start()
    try:
        while not stop.is_set():
            try:
                db.expire_leases()
                result = worker.process_next_queued_job_sync()
                if not result:
                    stop.wait(1)
            except Exception:
                logging.getLogger('sightline.worker').exception('Cloud analysis iteration failed.')
                stop.wait(2)
            finally:
                # Neither original video nor generated JPEGs are durable only here.
                for folder in ('videos','keyframes'):
                    for path in (settings.media_dir/folder).glob('*'):
                        if path.is_file():
                            path.unlink(missing_ok=True)
    finally:
        stop.set()
        thread.join(timeout=12)
        try:
            db.heartbeat(worker_id, loaded=False)
        finally:
            db.close_all()
            inference.cleanup()


if __name__ == '__main__':
    run()
