"""Queue/restart tests use isolated SQLite records and explicitly fake processing."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.core.errors import SightLineError
from app.db.database import DatabaseManager
from app.services.job_runner import JobRunner
from app.services.video_worker import VideoWorker


@pytest.fixture
def queue_db(tmp_path):
    db = DatabaseManager(tmp_path/'sightline.db')
    db.create_source({'id':'source', 'user_id':'a', 'source_type':'video_upload', 'original_filename':'clip.mp4', 'storage_key':'a/source.mp4'})
    yield db
    db.close_all()


def add(db, name, **kwargs):
    return db.create_analysis_job(user_id='a', source_id='source', targets=['person'], job_id=name, **kwargs)


def until(predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Worker did not reach expected state')


def test_concurrent_admission_is_bounded_and_idempotency_still_works(queue_db):
    def submit(index):
        try:
            add(queue_db, f'job-{index}', max_pending=3, max_pending_per_user=2)
            return 'accepted'
        except SightLineError as error:
            assert error.status_code==429
            return 'full'
        finally:
            queue_db.close_all()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(submit,range(12)))
    assert results.count('accepted')==2
    queue_db.get_connection().execute("UPDATE analysis_jobs SET status='completed'")
    first=add(queue_db,'idempotent',idempotency_key='same',max_pending=1)
    again=add(queue_db,'ignored',idempotency_key='same',max_pending=1)
    assert first['id']==again['id']=='idempotent'


def test_restart_fails_fresh_processing_retains_and_resumes_queued(queue_db, tmp_path):
    add(queue_db,'interrupted')
    queue_db.claim_next_queued_job('dead-process')
    add(queue_db,'queued')
    runner=JobRunner(queue_db,Settings(media_dir=tmp_path/'media'),SimpleNamespace())
    seen=[]
    def fake_processing():
        job=queue_db.claim_next_queued_job('fake-test-worker')
        if job:
            seen.append(job['id'])
            queue_db.mark_job_completed(job['id'])
            return {'status':'completed'}
    runner.worker.process_next_queued_job_sync=fake_processing
    runner.start()
    try:
        until(lambda:queue_db.get_job('queued')['status']=='completed')
        assert queue_db.get_job('interrupted')['status']=='failed'
        assert 'restart' in queue_db.get_job('interrupted')['error_message']
        assert seen==['queued']
        other=JobRunner(queue_db,Settings(media_dir=tmp_path/'other'),SimpleNamespace())
        with pytest.raises(RuntimeError,match='one API process'):
            other.start()
    finally:
        assert runner.close()


def test_claim_is_atomic_between_workers(queue_db):
    add(queue_db,'single')
    def claim(index):
        try:
            return queue_db.claim_next_queued_job(f'worker-{index}')
        finally:
            queue_db.close_all()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(claim,range(6)))
    assert len([job for job in results if job])==1


def test_finalization_cannot_resurrect_cancelled_work(queue_db):
    add(queue_db,'cancelled')
    queue_db.request_job_cancellation('cancelled','a')
    result=queue_db.finalize_analysis_results('cancelled',{'id':'must-not-exist'},[],[])
    queue_db.mark_job_failed('cancelled','late failure')
    queue_db.mark_job_completed('cancelled')
    assert result is None
    assert queue_db.get_job('cancelled')['status']=='cancelled'
    assert queue_db.get_incident('must-not-exist') is None


def test_cancel_race_before_finalization_has_no_incident(queue_db):
    add(queue_db,'race')
    queue_db.claim_next_queued_job('worker')
    queue_db.request_job_cancellation('race','a')
    assert queue_db.finalize_analysis_results('race',{'id':'must-not-exist'},[],[]) is None
    assert queue_db.get_job('race')['status']=='cancelled'


def test_processing_deadline_and_shutdown_checked_between_frames(queue_db,tmp_path):
    worker=VideoWorker(db=queue_db,inference_service=SimpleNamespace())
    worker.settings=Settings(media_dir=tmp_path/'media',job_timeout_seconds=30)
    with pytest.raises(TimeoutError):
        worker._check_deadline(time.monotonic()-31)
    worker.stop_event.set()
    with pytest.raises(RuntimeError,match='shutdown'):
        worker._check_deadline(time.monotonic())


def test_readiness_tracks_worker_and_private_api_is_uncacheable(client):
    response=client.get('/api/v1/health/live')
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-frame-options']=='DENY'
    runner=client.app.state.job_runner
    assert runner.ready
    assert runner.close()
    ready=client.get('/api/v1/health/ready')
    assert ready.status_code==503
    assert ready.json()['components']['video_worker']['ready'] is False


def test_unclaimed_or_other_worker_job_cannot_run(queue_db):
    add(queue_db,'guarded')
    worker=VideoWorker(db=queue_db,inference_service=SimpleNamespace())
    with pytest.raises(ValueError,match='atomically claimed'):
        worker.process_job_sync('guarded')
    queue_db.claim_next_queued_job('another-worker')
    with pytest.raises(ValueError,match='atomically claimed'):
        worker.process_job_sync('guarded')


def test_api_admission_rejects_when_owner_limit_reached(client,valid_auth_headers):
    from token_support import issue_token
    import jwt
    owner=jwt.decode(issue_token(),options={"verify_signature":False})['sub']
    runner=client.app.state.job_runner
    assert runner.close()
    # Leave admission enabled with a controlled queue and no processing thread.
    class AdmissionOnly:
        ready=True
        settings=runner.settings
        def wake(self): pass
    client.app.state.job_runner=AdmissionOnly()
    db=DatabaseManager.get_instance()
    db.create_source({'id':'queue-limit-source','user_id':owner,'source_type':'video_upload','original_filename':'clip.mp4','storage_key':'queue-limit-source.mp4'})
    for i in range(runner.settings.max_pending_jobs_per_user):
        db.create_analysis_job(owner,'queue-limit-source',['person'],job_id=f'limit-fixture-{i}')
    response=client.post('/api/v1/analysis/start',headers=valid_auth_headers,json={'sourceId':'queue-limit-source','targets':['person']})
    assert response.status_code==429
    assert response.json()['error']=='QUEUE_FULL'
    for i in range(runner.settings.max_pending_jobs_per_user):
        db.request_job_cancellation(f'limit-fixture-{i}',owner)
    client.app.state.job_runner=runner


def test_production_health_hides_disk_paths_and_vercel_backend_is_rejected(client,monkeypatch):
    from app.config import get_settings,Settings
    from app.main import create_app
    client.app.dependency_overrides[get_settings]=lambda:Settings(environment='production',session_secret='ISOLATED_TEST_SESSION_VALUE_32_CHARACTERS_LONG')
    response=client.get('/api/v1/health/ready')
    assert response.json()['components']['media_storage']['path'] is None
    assert response.json()['components']['model_checkpoint']['path'] is None
    monkeypatch.setenv('VERCEL','1')
    with pytest.raises(RuntimeError,match='durable'):
        create_app()
