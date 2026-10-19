"""Real API/SQLite checks; no emergency calls, outbound messages or provider mocks."""
import pytest
from app.api.endpoints import incidents
from app.db.database import DatabaseManager

@pytest.fixture
def response_api(client, tmp_path, monkeypatch):
    db = DatabaseManager(tmp_path / 'response.db')
    monkeypatch.setattr(incidents, 'db_manager', db)
    yield client, db
    db.close_all()

def create(client, headers):
    return client.post('/api/v1/incidents/manual-camera', headers=headers).json()['id']

def test_contacts_are_owned_validated_and_persistent(response_api, valid_auth_headers, make_test_token):
    client, db = response_api
    path='/api/v1/incidents/response-contacts'
    assert client.get(path).status_code == 401
    assert client.get(path,headers=valid_auth_headers).json()['policePhone']=='112'
    contacts={'securityName':'Guard','securityPhone':'+919999999999','policePhone':'112','siteAddress':'Test site'}
    assert client.put(path,headers=valid_auth_headers,json=contacts).json()==contacts
    assert client.get(path,headers={'Authorization':'Bearer '+make_test_token(sub='other')}).json()['securityPhone']==''
    for bad in ['javascript:alert(1)','+0000000','123','91abc']:
        assert client.put(path,headers=valid_auth_headers,json={**contacts,'securityPhone':bad}).status_code==422
    reopened=DatabaseManager(db.db_path)
    assert reopened.get_connection().execute('SELECT siteAddress FROM response_contacts').fetchone()[0]=='Test site'
    reopened.close_all()

def test_timeline_ownership_retry_history_and_close(response_api,valid_auth_headers,make_test_token):
    client,db=response_api; id=create(client,valid_auth_headers)
    path=f'/api/v1/incidents/{id}/response'
    assert client.get(path).status_code==401
    other={'Authorization':'Bearer '+make_test_token(sub='other')}
    assert client.get(path,headers=other).status_code==404
    body={'kind':'call_opened','recipient':'police','eventId':'unique-call','detail':''}
    assert client.post(path,headers=other,json=body).status_code==404
    assert client.post(path,headers=valid_auth_headers,json=body).status_code==422
    assert client.patch('/api/v1/incidents/'+id,headers=valid_auth_headers,json={'status':'confirmed'}).status_code==200
    res=client.post(path,headers=valid_auth_headers,json=body)
    assert res.status_code==200,res.text
    assert res.json()['status']=='Call opened'
    assert client.post(path,headers=valid_auth_headers,json=body).json()==res.json()
    assert client.post(path,headers=valid_auth_headers,json={**body,'kind':'contact_confirmed'}).status_code==422
    assert client.get('/api/v1/incidents',headers=valid_auth_headers).json()['items'][0]['responseStatus']=='Call opened'
    for kind in ['whatsapp_opened','summary_shared','contact_confirmed','note','resolved']:
        res=client.post(path,headers=valid_auth_headers,json={'kind':kind,'recipient':'security' if kind in ['whatsapp_opened','summary_shared','contact_confirmed'] else 'owner','eventId':kind,'detail':'test note' if kind=='note' else ''})
        assert res.status_code==200,res.text
    assert res.json()['status']=='Resolved'
    assert res.json()['events'][3]['kind']=='contact_confirmed'
    assert client.post(path,headers=valid_auth_headers,json={**body,'eventId':'late-call'}).status_code==422
    assert db.get_connection().execute('SELECT count(*) FROM dispatches').fetchone()[0]==0
    owner=db.get_connection().execute('SELECT user_id FROM incidents WHERE id=?',(id,)).fetchone()[0]
    reopened=DatabaseManager(db.db_path)
    assert reopened.get_incident(id,owner)['responseStatus']=='Resolved'
    reopened.close_all()

def test_false_alarm_reason_clears_only_selected_evidence(response_api,valid_auth_headers):
    client,db=response_api; id=create(client,valid_auth_headers); another=create(client,valid_auth_headers)
    path=f'/api/v1/incidents/{id}/response'
    body={'kind':'false_alarm','recipient':'owner','eventId':'dismiss','detail':''}
    assert client.post(path,headers=valid_auth_headers,json=body).status_code==422
    body['detail']='Family member'
    assert client.post(path,headers=valid_auth_headers,json=body).json()['status']=='False alarm'
    inc=client.get(f'/api/v1/incidents/{id}',headers=valid_auth_headers).json()
    assert inc['frames']==[] and inc['thumbnail'] is None and inc['status']=='dismissed'
    assert inc['review_reason']=='False alarm: Family member'
    assert client.get(f'/api/v1/incidents/{another}',headers=valid_auth_headers).json()['status']=='unreviewed'
    assert client.post(path,headers=valid_auth_headers,json=body).status_code==200
    assert client.post(path,headers=valid_auth_headers,json={**body,'kind':'police_notified','eventId':'bad'}).status_code==422


def test_later_link_open_does_not_erase_owner_confirmation(response_api, valid_auth_headers):
    client, db = response_api
    id = create(client, valid_auth_headers)
    path = f'/api/v1/incidents/{id}/response'
    assert client.patch('/api/v1/incidents/'+id,headers=valid_auth_headers,json={'status':'confirmed'}).status_code==200
    for kind in ['contact_confirmed', 'call_opened', 'whatsapp_opened']:
        res = client.post(path, headers=valid_auth_headers, json={'kind':kind,'recipient':'security','eventId':kind,'detail':''})
        assert res.status_code == 200
    assert res.json()['status'] == 'Spoke to contact · confirmed by you'

def test_contact_confirmation_deduplicates_new_action_keys(response_api,valid_auth_headers):
    client,db=response_api
    id=create(client,valid_auth_headers)
    path=f'/api/v1/incidents/{id}/response'
    assert client.patch('/api/v1/incidents/'+id,headers=valid_auth_headers,json={'status':'confirmed'}).status_code==200
    for key in ['first-confirmation','another-tab-confirmation']:
        result=client.post(path,headers=valid_auth_headers,json={'kind':'contact_confirmed','recipient':'security','eventId':key,'detail':''})
        assert result.status_code==200
    assert len(result.json()['events'])==1


def test_response_contact_actions_require_confirmed_threat(response_api,valid_auth_headers):
    client,db=response_api
    id=create(client,valid_auth_headers)
    path=f'/api/v1/incidents/{id}/response'
    for kind in ['call_opened','whatsapp_opened','summary_shared','contact_confirmed','resolved']:
        body={'kind':kind,'recipient':'owner' if kind=='resolved' else 'security','eventId':kind,'detail':''}
        result=client.post(path,headers=valid_auth_headers,json=body)
        assert result.status_code==422
        assert 'Threat not confirmed' in result.json()['message']
    assert client.get(path,headers=valid_auth_headers).json()['events']==[]
