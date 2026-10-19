"""Release regression tests use generated keys and isolated records, never real credentials."""
import asyncio,time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx,jwt,pytest
from app.core import auth
from app.core.auth import _fetch_jwks as real_fetch_jwks
from app.core.errors import AuthenticationError,LockedError,ValidationError,ServiceUnavailableError
from app.db.database import DatabaseManager
from token_support import PRIVATE_KEY,PUBLIC_JWK,PROJECT,issue_token


def raw_token(**changes):
    now=int(time.time())
    payload={'sub':'00000000-0000-0000-0000-000000000001','aud':'authenticated','role':'authenticated','iss':PROJECT+'/auth/v1','iat':now,'exp':now+300}
    payload.update(changes)
    payload={k:v for k,v in payload.items() if v is not None}
    return jwt.encode(payload,PRIVATE_KEY,algorithm='ES256',headers={'kid':'isolated-test-key'})


@pytest.mark.parametrize('changes',[
    {'exp':None},{'iat':None},{'iss':None},{'sub':None},{'role':None},
    {'iss':'https://unrelated.example/auth/v1'},{'aud':'test-aud'},{'aud':['authenticated']},
    {'sub':'not-a-uuid'},{'exp':False},{'exp':str(int(time.time())+300)},
    {'exp':int(time.time())-1},{'nbf':'future'},{'iat':'future'}])
def test_invalid_signed_claims_are_rejected(client,changes):
    changes={key: int(time.time())+600 if value=='future' else value for key,value in changes.items()}
    response=client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+raw_token(**changes)})
    assert response.status_code==401


@pytest.mark.parametrize('algorithm',['none','HS256'])
def test_no_unsigned_or_symmetric_fallback(client,algorithm):
    now=int(time.time())
    token=jwt.encode({'sub':'00000000-0000-0000-0000-000000000001','aud':'authenticated','role':'authenticated','iss':PROJECT+'/auth/v1','iat':now,'exp':now+300},'' if algorithm=='none' else 'attacker-controlled-test-secret-key',algorithm=algorithm)
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+token}).status_code==401


def test_bad_signature_and_privileged_roles_denied(client):
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+issue_token(secret='other-key')}).status_code==401
    for change in [{'role':'service_role'},{'role':'anon'},{'is_anonymous':True}]:
        assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+raw_token(**change)}).status_code==403


def test_missing_project_configuration_does_not_decode(test_settings):
    test_settings.supabase_url=None
    with pytest.raises(AuthenticationError):asyncio.run(auth.get_current_user('Bearer '+raw_token(),test_settings))


def test_jwks_outage_and_empty_keys_fail_closed(client,monkeypatch):
    async def unavailable(issuer):raise ServiceUnavailableError()
    monkeypatch.setattr(auth,'_fetch_jwks',unavailable)
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+raw_token()}).status_code==503
    async def empty(issuer):return {'keys':[]}
    monkeypatch.setattr(auth,'_fetch_jwks',empty)
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+raw_token()}).status_code==401


def test_key_cache_expiration_and_rotation(client,monkeypatch):
    calls=[]
    async def fetch(issuer):calls.append(issuer);return {'keys':[PUBLIC_JWK]}
    monkeypatch.setattr(auth,'_fetch_jwks',fetch)
    headers={'Authorization':'Bearer '+raw_token()}
    assert client.get('/api/v1/auth/me',headers=headers).status_code==200
    assert client.get('/api/v1/auth/me',headers=headers).status_code==200
    assert calls==[PROJECT+'/auth/v1']
    async def revoked(issuer):return {'keys':[]}
    monkeypatch.setattr(auth,'_fetch_jwks',revoked)
    issuer=PROJECT+'/auth/v1';auth._jwks_cache[issuer]=(0,0,auth._jwks_cache[issuer][2])
    assert client.get('/api/v1/auth/me',headers=headers).status_code==401


def test_jwks_transport_is_fixed_project_public_read(monkeypatch):
    requests=[];original=httpx.AsyncClient
    def handler(request):requests.append(request);return httpx.Response(200,json={'keys':[PUBLIC_JWK]})
    monkeypatch.setattr(auth.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    assert asyncio.run(real_fetch_jwks(PROJECT+'/auth/v1'))['keys']
    assert str(requests[0].url)==PROJECT+'/auth/v1/.well-known/jwks.json'
    assert 'authorization' not in requests[0].headers and 'apikey' not in requests[0].headers


def test_owner_pin_setup_change_legacy_and_concurrent_lockout(tmp_path):
    db=DatabaseManager(tmp_path/'private.db')
    with pytest.raises(ValidationError,match='Set your security PIN'):db.verify_operator_pin('new-owner','1234')
    assert db.get_operator_security('new-owner') is None
    db.get_connection().execute('INSERT INTO operator_security(user_id,pin_hash,updated_at) VALUES(?,?,?)',('old-owner','a'*64,'2026-01-01T00:00:00Z'))
    assert not db.has_operator_pin('old-owner')
    with pytest.raises(ValidationError):db.verify_operator_pin('old-owner','1234')
    db.configure_operator_pin('old-owner','6392')
    assert db.has_operator_pin('old-owner') and db.verify_operator_pin('old-owner','6392')
    with pytest.raises(ValidationError,match='current security PIN'):db.configure_operator_pin('old-owner','5271')
    db.configure_operator_pin('old-owner','5271','6392')
    assert db.verify_operator_pin('old-owner','5271')
    db.set_operator_pin('second-owner','5271')
    assert db.get_operator_security('old-owner')['pin_hash']!=db.get_operator_security('second-owner')['pin_hash']
    def wrong(_):
        try:db.verify_operator_pin('old-owner','0000')
        except (ValidationError,LockedError):return True
        finally:db.close_all()
    with ThreadPoolExecutor(max_workers=5) as pool:assert all(pool.map(wrong,range(5)))
    assert db.get_operator_security('old-owner')['failed_attempts']==3
    reopened=DatabaseManager(db.db_path)
    with pytest.raises(LockedError):reopened.verify_operator_pin('old-owner','5271')
    reopened.close_all();db.close_all()


def test_pin_api_owner_bound_and_no_hash_or_pin_response(client,valid_auth_headers,tmp_path,monkeypatch):
    from app.api.endpoints import dispatches
    db=DatabaseManager(tmp_path/'pin-api.db')
    monkeypatch.setattr(dispatches.DatabaseManager,'get_instance',classmethod(lambda cls:db))
    path='/api/v1/dispatches/security/pin'
    assert client.get(path,headers=valid_auth_headers).json()=={'configured':False}
    bad={**valid_auth_headers,'X-Expected-Owner':'another-owner'}
    assert client.post(path,headers=bad,json={'pin':'6382'}).status_code==403
    result=client.post(path,headers=valid_auth_headers,json={'pin':'6382'})
    assert result.status_code==200 and '6382' not in result.text and 'hash' not in result.text
    assert client.get(path,headers=valid_auth_headers).json()=={'configured':True}
    assert client.post(path,headers=valid_auth_headers,json={'pin':'5271'}).status_code==422
    assert client.post(path,headers=valid_auth_headers,json={'pin':'5271','currentPin':'6382'}).status_code==200
    assert client.post(path,headers=valid_auth_headers,json={'pin':'abcd','currentPin':'5271'}).status_code==422
    db.close_all()


def test_unloaded_checkpoint_cannot_be_ready(client,monkeypatch):
    from app.services.inference_service import InferenceService
    monkeypatch.setattr(InferenceService,'get_instance',classmethod(lambda cls:SimpleNamespace(get_readiness_info=lambda:{'checkpoint_found':True,'is_loaded':False})))
    response=client.get('/api/v1/health/ready')
    assert response.status_code==503
    assert response.json()['components']['inference_service']['ready'] is False
    assert response.json()['components']['video_worker']['ready'] is False
