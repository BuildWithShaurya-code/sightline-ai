"""Offline restore drill on disposable fixtures; no real footage or credentials."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest
from app.db.database import DatabaseManager
from app.services.job_runner import JobRunner
from app.config import Settings
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('storage_snapshot',Path(__file__).resolve().parents[2]/'scripts/storage_snapshot.py')
snapshot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


@pytest.fixture
def storage(tmp_path):
    root=tmp_path/'storage'
    (root/'data').mkdir(parents=True)
    db=DatabaseManager(root/'data/sightline.db')
    db.create_source({'id':'fixture','user_id':'owner-a','source_type':'video_upload','original_filename':'fixture.mp4','storage_key':'owner-a/fixture.mp4'})
    db.configure_operator_pin('owner-a','473826')
    db.close_all()
    with sqlite3.connect(root/'data/account_aliases.sqlite3') as conn:
        conn.execute('CREATE TABLE fixture(value TEXT)')
        conn.execute("INSERT INTO fixture VALUES ('isolated-alias')")
    (root/'media/videos').mkdir(parents=True)
    (root/'media/videos/fixture.mp4').write_bytes(b'ISOLATED_TEST_MEDIA')
    (root/'media/keyframes').mkdir()
    (root/'media/keyframes/fixture.jpg').write_bytes(b'ISOLATED_TEST_FRAME')
    (root/'media/temp').mkdir()
    (root/'media/temp/unfinished.mp4').write_bytes(b'not-part-of-backup')
    (root/'.env').write_text('DO_NOT_COPY_TEST_MARKER')
    return root


def test_offline_backup_restore_keeps_data_aliases_pin_and_media(storage,tmp_path):
    result=snapshot.backup(storage,tmp_path/'backup')
    manifest=json.loads((result/'manifest.json').read_text())
    assert len(manifest['files'])==4
    restored=snapshot.restore(result,tmp_path/'restored')
    db=DatabaseManager(restored/'data/sightline.db')
    assert db.get_source('fixture','owner-a') is not None
    assert db.get_source('fixture','other-owner') is None
    assert db.verify_operator_pin('owner-a','473826')
    db.close_all()
    assert (restored/'media/videos/fixture.mp4').read_bytes()==b'ISOLATED_TEST_MEDIA'
    assert not (result/'.env').exists()
    assert not (result/'media/temp').exists()
    for file in result.rglob('*'):
        if file.is_file():
            assert file.stat().st_mode & 0o777==0o600


def test_restore_refuses_corrupt_backup_without_touching_target(storage,tmp_path):
    source=snapshot.backup(storage,tmp_path/'backup')
    (source/'media/videos/fixture.mp4').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):
        snapshot.restore(source,tmp_path/'restored')
    assert not (tmp_path/'restored').exists()


def test_restore_never_overwrites_existing_data(storage,tmp_path):
    source=snapshot.backup(storage,tmp_path/'backup')
    target=tmp_path/'existing'
    target.mkdir()
    marker=target/'keep.txt'
    marker.write_text('keep')
    with pytest.raises(ValueError,match='never overwritten'):
        snapshot.restore(source,target)
    assert marker.read_text()=='keep'


def test_snapshot_refuses_symlinks_and_traversal(storage,tmp_path):
    (storage/'media/videos/link.mp4').symlink_to(storage/'.env')
    with pytest.raises(ValueError,match='Symbolic'):
        snapshot.backup(storage,tmp_path/'backup')
    assert not (tmp_path/'backup').exists()
    assert not snapshot.valid_name('../.env')
    assert not snapshot.valid_name('media/videos/../../.env')
    assert not snapshot.valid_name('data/private.env')


def test_backup_refuses_running_worker(storage,tmp_path):
    db=DatabaseManager(storage/'data/sightline.db')
    runner=JobRunner(db,Settings(media_dir=storage/'media'),SimpleNamespace())
    runner.start()
    try:
        with pytest.raises(ValueError,match='Stop the backend'):
            snapshot.backup(storage,tmp_path/'backup')
    finally:
        assert runner.close()
        db.close_all()
