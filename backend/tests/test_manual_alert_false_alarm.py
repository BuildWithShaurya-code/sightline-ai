"""Manual alerts and false-alarm evidence visibility use real API/database paths."""
import pytest
from app.api.endpoints import incidents
from app.db.database import DatabaseManager
from app.services.manual_camera_alert import save_manual_camera_alert


@pytest.fixture
def api_db(client, tmp_path, monkeypatch):
    db = DatabaseManager(tmp_path / 'manual-alert.db')
    monkeypatch.setattr(incidents, 'db_manager', db)
    yield client, db
    db.close_all()


def test_manual_alert_has_no_photo_or_predictions_and_is_idempotent(api_db, valid_auth_headers, make_test_token):
    client, db = api_db
    assert client.post('/api/v1/incidents/manual-camera').status_code == 401
    headers = {**valid_auth_headers, 'Idempotency-Key': 'manual-no-photo'}
    res = client.post('/api/v1/incidents/manual-camera', headers=headers, json={'status': 'confirmed', 'frames': [{'imageDataUrl': 'forged'}], 'user_id': 'other'})
    assert res.status_code == 201, res.text
    alert = res.json()
    assert alert['status'] == 'unreviewed'
    assert alert['frames'] == alert['detections'] == []
    assert alert['thumbnail'] is None
    assert client.post('/api/v1/incidents/manual-camera', headers=headers).json()['id'] == alert['id']
    assert db.get_connection().execute('SELECT count(*) FROM incidents').fetchone()[0] == 1
    assert db.get_connection().execute('SELECT count(*) FROM evidence').fetchone()[0] == 0
    assert db.get_connection().execute('SELECT count(*) FROM detections').fetchone()[0] == 0
    other = {'Authorization': 'Bearer ' + make_test_token(sub='other-user')}
    assert client.get('/api/v1/incidents/' + alert['id'], headers=other).status_code == 404
    # A key is scoped to its authenticated owner.
    res2 = client.post('/api/v1/incidents/manual-camera', headers={**other, 'Idempotency-Key': 'manual-no-photo'})
    assert res2.status_code == 201 and res2.json()['id'] != alert['id']


def test_false_alarm_hides_evidence_persistently_and_preserves_raw_records(api_db, valid_auth_headers):
    client, db = api_db
    alert = client.post('/api/v1/incidents/manual-camera', headers=valid_auth_headers).json()
    conn = db.get_connection()
    owner = conn.execute('SELECT user_id FROM incidents WHERE id=?', (alert['id'],)).fetchone()[0]
    source = alert['sourceId']
    conn.execute("INSERT INTO evidence(id,incident_id,source_id,user_id,storage_key,image_data_url,created_at) VALUES(?,?,?,?,?,?,?)", ('raw-evidence',alert['id'],source,owner,'keyframes/test.jpg','data:image/jpeg;base64,dGVzdA==',alert['createdAt']))
    assert client.get('/api/v1/incidents/'+alert['id'], headers=valid_auth_headers).json()['frames']
    res = client.post('/api/v1/incidents/'+alert['id']+'/false-alarm', headers=valid_auth_headers)
    assert res.status_code == 200, res.text
    cleared = res.json()
    assert cleared['status'] == 'dismissed'
    assert cleared['frames'] == cleared['detections'] == []
    assert cleared['thumbnail'] is None
    assert client.post('/api/v1/incidents/'+alert['id']+'/false-alarm', headers=valid_auth_headers).status_code == 200
    assert conn.execute('SELECT count(*) FROM evidence').fetchone()[0] == 1
    assert client.get('/api/v1/incidents', headers=valid_auth_headers).json()['items'][0]['frames'] == []
    path = db.db_path
    db.close_all()
    reopened = DatabaseManager(path)
    assert reopened.get_incident(alert['id'], owner)['frames'] == []
    assert reopened.get_incident(alert['id'], owner)['status'] == 'dismissed'
    reopened.close_all()


def test_false_alarm_is_owner_scoped_and_does_not_recall_sent_dispatch(api_db, valid_auth_headers, make_test_token):
    client, db = api_db
    alert = client.post('/api/v1/incidents/manual-camera', headers=valid_auth_headers).json()
    owner = db.get_connection().execute('SELECT user_id FROM incidents WHERE id=?',(alert['id'],)).fetchone()[0]
    db.create_dispatch({'id':'disp-sent','incident_id':alert['id'],'user_id':owner,'status':'sent','provider':'test_provider'})
    route = '/api/v1/incidents/'+alert['id']+'/false-alarm'
    assert client.post(route).status_code == 401
    assert client.post(route, headers={'Authorization':'Bearer '+make_test_token(sub='intruder')}).status_code == 404
    assert db.get_incident(alert['id'],owner)['status'] == 'unreviewed'
    assert client.post(route, headers=valid_auth_headers).status_code == 200
    assert db.get_dispatch('disp-sent',owner)['status'] == 'sent'


def test_manual_alert_reopens_with_empty_evidence(tmp_path):
    path=tmp_path/'reopen.db'
    db=DatabaseManager(path)
    alert=save_manual_camera_alert(db,'test-owner','stable-key')
    db.close_all()
    other=DatabaseManager(path)
    assert other.get_incident(alert['id'],'test-owner')['frames'] == []
    assert save_manual_camera_alert(other,'test-owner','stable-key')['id'] == alert['id']
    other.close_all()
