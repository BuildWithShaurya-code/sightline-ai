"""Synthetic-positive transport/storage tests; no claims of model accuracy."""
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from app.db.database import DatabaseManager
from app.api.endpoints import incidents
from app.services.inference_service import InferenceService

@pytest.fixture
def automatic_api(client,test_settings,tmp_path,monkeypatch):
    db=DatabaseManager(tmp_path/'auto.db')
    class SyntheticInference:
        settings=test_settings
        async def infer_image_async(self,contents,*args,**kwargs):
            image=cv2.imdecode(np.frombuffer(contents,np.uint8),cv2.IMREAD_COLOR)
            return SimpleNamespace(model_version='SYNTHETIC_FIXTURE',detections=[] if image is None or image.mean()<1 else [SimpleNamespace(classId='mask',className='Mask',confidence=.81,box=[0,0,8,8])])
        def decode_image_bytes(self,contents):
            img=cv2.imdecode(np.frombuffer(contents,np.uint8),cv2.IMREAD_COLOR)
            return img,img.shape[1],img.shape[0],0
    inference=SyntheticInference()
    monkeypatch.setattr(incidents,'db_manager',db)
    monkeypatch.setattr(InferenceService,'get_instance',classmethod(lambda cls:inference))
    yield client,db
    db.close_all()

def frame(value):
    return cv2.imencode('.jpg',np.full((12,12,3),value,dtype=np.uint8))[1].tobytes()

def post(client,headers,value=30,session='episode-one',time=0):
    return client.post('/api/v1/incidents/auto-evidence',headers=headers,files={'image':('synthetic.jpg',frame(value),'image/jpeg')},data={'session_key':session,'time_seconds':time})

def test_auto_frame_exact_images_idempotency_cap_and_persistence(automatic_api,valid_auth_headers):
    client,db=automatic_api
    first=post(client,valid_auth_headers)
    assert first.status_code==201,first.text
    inc=first.json();assert inc['status']=='unreviewed' and len(inc['frames'])==1
    assert inc['detections'][0]['classId']=='mask'
    assert post(client,valid_auth_headers).json()['frames']==inc['frames']
    for value,time in [(60,.7),(90,1.4),(120,2.1)]:
        inc=post(client,valid_auth_headers,value,time=time).json()
    assert len(inc['frames'])==3
    assert [f['timeSeconds'] for f in inc['frames']]==[0,.7,1.4]
    assert len({f['imageDataUrl'] for f in inc['frames']})==3
    assert db.get_connection().execute('SELECT count(*) FROM incidents').fetchone()[0]==1
    owner=db.get_connection().execute('SELECT user_id FROM incidents').fetchone()[0]
    reopened=DatabaseManager(db.db_path)
    assert reopened.get_incident(inc['id'],owner)['frames']==inc['frames']
    reopened.close_all()

def test_auto_capture_owner_scope_and_confirmed_freeze(automatic_api,valid_auth_headers,make_test_token):
    client,db=automatic_api
    assert post(client,{},30).status_code==401
    inc=post(client,valid_auth_headers).json()
    other={'Authorization':'Bearer '+make_test_token(sub='other-auto-owner')}
    assert client.get('/api/v1/incidents/'+inc['id'],headers=other).status_code==404
    assert post(client,other).json()['id']!=inc['id']
    assert client.patch('/api/v1/incidents/'+inc['id'],headers=valid_auth_headers,json={'status':'confirmed'}).status_code==200
    frozen=post(client,valid_auth_headers,80).json()
    assert frozen['status']=='confirmed' and len(frozen['frames'])==1

def test_auto_negative_frame_does_not_fabricate_evidence(automatic_api,valid_auth_headers):
    client,db=automatic_api
    assert post(client,valid_auth_headers,0).status_code==422
    assert db.get_connection().execute('SELECT count(*) FROM incidents').fetchone()[0]==0

from test_alert_history_persistence import snapshot_api, masked_jpeg

def test_real_model_mask_creates_automatic_evidence(snapshot_api,valid_auth_headers,masked_jpeg):
    client,db=snapshot_api
    res=client.post('/api/v1/incidents/auto-evidence',headers=valid_auth_headers,
        files={'image':('real-mask.jpg',masked_jpeg,'image/jpeg')},data={'session_key':'real-mask-test','time_seconds':0})
    assert res.status_code==201,res.text
    incident=res.json()
    assert incident['status']=='unreviewed'
    assert len(incident['frames'])==1 and incident['frames'][0]['imageDataUrl'].startswith('data:image/jpeg;base64,')
    assert any(d['classId']=='mask' and d['confidence']>.8 for d in incident['detections'])
    assert all(d['evidence_id']==incident['frames'][0]['id'] for d in incident['detections'])


def test_automatic_lookup_is_off_event_loop_and_preserves_owner(tmp_path):
    import asyncio,threading
    from app.services.automatic_evidence import AutomaticEvidenceService
    from app.core.identity import owner_id
    owner='verified-test-owner'
    main_thread=threading.get_ident()
    existing={'frames':[{'id':'a'},{'id':'b'},{'id':'c'}],'status':'unreviewed'}
    class IsolatedDatabase:
        def get_incident(self,incident_id,user_id):
            assert threading.get_ident()!=main_thread
            assert owner_id.get()==owner and user_id==owner
            return existing
    inference=SimpleNamespace(settings=SimpleNamespace(media_dir=tmp_path/'media'))
    token=owner_id.set(owner)
    try:
        assert asyncio.run(AutomaticEvidenceService(IsolatedDatabase(),inference).save(b'fixture',owner,'episode',0)) is existing
    finally:owner_id.reset(token)
