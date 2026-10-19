"""Single-node persistent queue. One process owns the local database worker lock."""
import fcntl
import logging
import os
import threading

from .video_worker import VideoWorker

logger = logging.getLogger('sightline.queue')


class JobRunner:
    def __init__(self, db, settings, inference_service):
        self.db = db
        self.settings = settings
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.worker = VideoWorker(db=db, inference_service=inference_service, stop_event=self.stop_event)
        self.thread = None
        self.lock_file = None

    @property
    def ready(self):
        return bool(self.thread and self.thread.is_alive() and not self.stop_event.is_set())

    def start(self):
        lock_path = self.db.db_path.parent / '.analysis-worker.lock'
        self.lock_file = os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), 'r+')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError('This local database already has an analysis worker. Run one API process.') from None
        try:
            recovered = self.db.recover_interrupted_jobs()
            logger.info('Queue startup: %d interrupted jobs marked failed; queued jobs retained.', recovered)
            self.thread = threading.Thread(target=self._run, name='sightline-analysis', daemon=True)
            self.thread.start()
        except Exception:
            self.lock_file.close()
            self.lock_file = None
            raise

    def wake(self):
        self.wake_event.set()

    def _run(self):
        try:
            while not self.stop_event.is_set():
                self.wake_event.clear()
                try:
                    result = self.worker.process_next_queued_job_sync()
                except Exception:
                    logger.exception('Queue iteration failed; retrying after a bounded delay.')
                    self.stop_event.wait(1)
                    continue
                if result is None:
                    self.wake_event.wait(0.5)
        finally:
            self.db.close_all()
            self.lock_file.close()
            self.lock_file = None

    def close(self, timeout=25):
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout)
        closed = not self.thread or not self.thread.is_alive()
        if not closed:
            logger.warning('Analysis is still finishing a native frame. Interrupted work will fail explicitly on restart.')
        return closed
