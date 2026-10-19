from pathlib import Path
import cv2
import pytest

from app.db.database import DatabaseManager
from app.services.inference_service import InferenceService
from app.api.endpoints import incidents

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot_api(client, test_settings, monkeypatch, tmp_path):
    db = DatabaseManager(tmp_path / 'camera-alert-test.db')
    inference = InferenceService(model_path=PROJECT_ROOT / 'backend/models/best.pt', device='cpu')
    inference.settings = test_settings
    monkeypatch.setattr(incidents, 'db_manager', db)
    monkeypatch.setattr(InferenceService, 'get_instance', classmethod(lambda cls: inference))
    return client, db


@pytest.fixture
def masked_jpeg():
    cap = cv2.VideoCapture(str(PROJECT_ROOT / 'qa/data/threat_footage_h264.mp4'))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 53)
    ok, frame = cap.read()
    cap.release()
    assert ok
    ok, encoded = cv2.imencode('.jpg', frame)
    assert ok
    return encoded.tobytes()


def test_camera_save_is_persistent_owner_scoped_and_idempotent(snapshot_api, valid_auth_headers, make_test_token, masked_jpeg):
    client, db = snapshot_api
    headers = {**valid_auth_headers, 'Idempotency-Key': 'isolated-camera-save-test'}
    response = client.post('/api/v1/incidents/from-frame', headers=headers,
                           files={'image': ('camera.jpg', masked_jpeg, 'image/jpeg')},
                           data={'targets': 'mask', 'status': 'confirmed', 'user_id': 'forged-owner'})
    assert response.status_code == 201, response.text
    incident = response.json()
    assert incident['status'] == 'unreviewed'
    assert incident['frames'] and incident['detections'][0]['classId'] == 'mask'
    assert incident['detections'][0]['evidence_id'] == incident['frames'][0]['id']
    again = client.post('/api/v1/incidents/from-frame', headers=headers,
                        files={'image': ('camera.jpg', masked_jpeg, 'image/jpeg')}, data={'targets': 'mask'})
    assert again.json()['id'] == incident['id']
    assert db.get_connection().execute('SELECT COUNT(*) FROM incidents').fetchone()[0] == 1
    assert db.get_connection().execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 1
    assert len(list(db.get_source(incident['sourceId'])['storage_key'].split('/'))) >= 2
    assert client.get('/api/v1/incidents', headers=valid_auth_headers).json()['pagination']['total_items'] == 1
    other = {'Authorization': 'Bearer ' + make_test_token(sub='other-user')}
    assert client.get('/api/v1/incidents/'+incident['id'], headers=other).status_code == 404
    assert client.get('/api/v1/incidents', headers=other).json()['items'] == []
    db.close_all()
    reopened = DatabaseManager(db.db_path)
    restored = reopened.get_incident(incident['id'])
    assert restored['frames'] == incident['frames']
    assert restored['status'] == 'unreviewed'
    reopened.close_all()


def test_no_detection_or_anonymous_does_not_create_camera_alert(snapshot_api, valid_auth_headers):
    import numpy as np
    client, db = snapshot_api
    _, encoded = cv2.imencode('.jpg', np.zeros((240,320,3),dtype=np.uint8))
    files={'image': ('empty.jpg', encoded.tobytes(), 'image/jpeg')}
    assert client.post('/api/v1/incidents/from-frame', files=files).status_code == 401
    result = client.post('/api/v1/incidents/from-frame', files=files, headers=valid_auth_headers)
    assert result.status_code == 422
    assert db.get_connection().execute('SELECT COUNT(*) FROM incidents').fetchone()[0] == 0


def test_snapshot_database_failure_rolls_back_all_entities(tmp_path):
    db = DatabaseManager(tmp_path/'atomic-test.db')
    source={'id':'s','user_id':'owner','original_filename':'camera.jpg','storage_key':'keyframes/test.jpg'}
    job={'id':'j','source_id':'s','user_id':'owner'}
    incident={'id':'i','source_id':'s','user_id':'owner'}
    with pytest.raises(KeyError):
        db.finalize_analysis_results('j',incident,[],[{'id':'broken-detection'}],new_source=source,new_job=job)
    assert db.get_source('s') is None
    assert db.get_job('j') is None
    assert db.get_incident('i') is None


def test_history_dates_filter_before_pagination_and_searches_source(tmp_path):
    db = DatabaseManager(tmp_path/'dates.db')
    for i in range(14):
        source=db.create_source({'id':f's{i}','user_id':'owner','original_filename':f'recording-{i}.mp4','storage_key':f'videos/{i}.mp4'})
        db.create_analysis_job('owner',source['id'],['person'],job_id=f'j{i}')
        db.finalize_analysis_results(f'j{i}',{'id':f'i{i}','source_id':source['id'],'user_id':'owner',
              'created_at':f'2026-10-{1+i:02d}T00:00:00+00:00'},[],[])
    result=db.list_incidents('owner',page=1,page_size=2,created_after='2026-10-12T00:00:00+00:00')
    assert result['pagination']['total_items']==3
    assert [item['id'] for item in result['items']]==['i13','i12']
    second=db.list_incidents('owner',page=2,page_size=2,created_after='2026-10-12T00:00:00+00:00')
    assert [item['id'] for item in second['items']]==['i11']
    assert [item['id'] for item in db.list_incidents('owner',search_query='recording-7.mp4')['items']]==['i7']
