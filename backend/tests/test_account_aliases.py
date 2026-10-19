"""Isolated verified-provider adapter + real SQLite; no real accounts/passwords changed."""
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
import httpx
from app.core.errors import AuthenticationError, ConflictError, ServiceUnavailableError, SightLineError
from app.services import account_aliases as accounts
from app.api.endpoints import account_settings

A={'id':'00000000-0000-0000-0000-000000000001','email':'a@example.test'}
B={'id':'00000000-0000-0000-0000-000000000002','email':'b@example.test'}


def test_alias_ownership_uniqueness_reopen_and_project_scope(tmp_path):
    store=accounts.AliasStore(tmp_path/'aliases.db','https://one.supabase.co')
    assert store.own(A) is None
    assert store.save(A,'Test_Owner')=='test_owner'
    assert store.own(B) is None
    with pytest.raises(ConflictError):store.save(B,'test_owner')
    assert store.save(B,'second_owner')=='second_owner'
    assert store.save(A,'changed_owner')=='changed_owner'
    assert store.lookup('test_owner') is None
    assert store.lookup('changed_owner')=={'user_id':A['id'],'email':A['email']}
    assert accounts.AliasStore(store.path,store.project).own(A)=='changed_owner'
    assert accounts.AliasStore(store.path,'https://two.supabase.co').lookup('changed_owner') is None
    assert os.stat(store.path).st_mode & 0o777 == 0o600
    for bad in ['a','x@y.test','bad/name','a\nb','😀bad','x'*33]:
        with pytest.raises(Exception):store.save(A,bad)


@pytest.fixture
def alias_api(client,test_settings,tmp_path,monkeypatch):
    store=accounts.AliasStore(tmp_path/'account-aliases.db',test_settings.supabase_url)
    monkeypatch.setattr(accounts,'alias_store',lambda settings:store)
    calls=[]
    async def provider(settings,method,path,*,bearer=None,payload=None):
        calls.append((method,path))
        if method=='GET':
            if bearer=='verified-a':return A
            if bearer=='verified-b':return B
            raise AuthenticationError()
        if payload=={'email':A['email'],'password':'isolated-test-password'}:
            return {'user':A,'access_token':'isolated-access','refresh_token':'isolated-refresh'}
        raise AuthenticationError('Username or password is incorrect, or your session has ended.')
    monkeypatch.setattr(accounts,'provider_request',provider)
    accounts._attempts.clear()
    return client,store,calls


def test_verified_identity_required_no_local_token_fallback(alias_api):
    client,store,calls=alias_api
    for headers in [{},{'Authorization':'Bearer fabricated-local-jwt'}]:
        assert client.put('/api/v1/auth/username',headers=headers,json={'username':'test_owner'}).status_code==401
    assert store.lookup('test_owner') is None
    good={'Authorization':'Bearer verified-a'}
    assert client.put('/api/v1/auth/username',headers=good,json={'username':'test_owner'}).json()=={'username':'test_owner'}
    result=client.get('/api/v1/auth/username',headers=good)
    assert result.headers['cache-control']=='no-store'
    assert result.json()=={'username':'test_owner'}
    other={'Authorization':'Bearer verified-b'}
    assert client.get('/api/v1/auth/username',headers=other).json()=={'username':None}
    assert client.put('/api/v1/auth/username',headers=other,json={'username':'test_owner'}).status_code==409
    assert A['email'] not in result.text


def test_username_login_real_provider_only_and_private_response(alias_api):
    client,store,calls=alias_api;store.save(A,'test_owner')
    for name,password in [('unknown_owner','isolated-test-password'),('test_owner','incorrect-test-password')]:
        r=client.post('/api/v1/auth/username-login',json={'username':name,'password':password})
        assert r.status_code==401
        assert A['email'] not in r.text and password not in r.text
    r=client.post('/api/v1/auth/username-login',json={'username':'TEST_OWNER','password':'isolated-test-password'})
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert r.json()=={'access_token':'isolated-access','refresh_token':'isolated-refresh'}
    assert ('POST','token?grant_type=password') in calls
    assert 'password' not in store.path.read_bytes().decode('latin1')


def test_username_login_rejects_provider_owner_mismatch(alias_api,monkeypatch):
    client,store,calls=alias_api;store.save(A,'test_owner')
    async def provider(*args,**kwargs):return {'user':B,'access_token':'wrong','refresh_token':'wrong'}
    monkeypatch.setattr(accounts,'provider_request',provider)
    assert client.post('/api/v1/auth/username-login',json={'username':'test_owner','password':'isolated-test-password'}).status_code==401


def test_username_login_throttles_and_redacts_invalid_payload(alias_api):
    client,store,calls=alias_api
    for _ in range(10):assert client.post('/api/v1/auth/username-login',json={'username':'unknown_owner','password':'not-a-real-password'}).status_code==401
    assert client.post('/api/v1/auth/username-login',json={'username':'unknown_owner','password':'not-a-real-password'}).status_code==429
    assert 'not-a-real-password' not in client.post('/api/v1/auth/username-login',json={'username':'/bad/','password':'not-a-real-password'}).text
    accounts._attempts.clear()


def test_provider_rejects_missing_configuration():
    with pytest.raises(ServiceUnavailableError):accounts.provider_config(SimpleNamespace(supabase_url=None,supabase_publishable_key=None))
    with pytest.raises(ServiceUnavailableError):accounts.provider_config(SimpleNamespace(supabase_url='http://one.supabase.co',supabase_publishable_key='public-test-key'))


def test_provider_transport_uses_scoped_headers_and_hides_errors(monkeypatch):
    import asyncio
    original=httpx.AsyncClient
    seen=[]
    def handler(request):
        seen.append(request)
        if request.url.path.endswith('/user'):
            return httpx.Response(200,json=A)
        return httpx.Response(400,json={'message':'internal provider diagnostic must not be forwarded'})
    monkeypatch.setattr(accounts.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    settings=SimpleNamespace(supabase_url='https://one.supabase.co',supabase_publishable_key='public-test-key')
    verified=asyncio.run(accounts.verified_account(settings,'Bearer isolated-test-access'))
    assert verified==A
    assert seen[0].headers['Authorization']=='Bearer isolated-test-access'
    assert seen[0].headers['apikey']=='public-test-key'
    assert str(seen[0].url)=='https://one.supabase.co/auth/v1/user'
    with pytest.raises(AuthenticationError) as error:
        asyncio.run(accounts.provider_request(settings,'POST','token?grant_type=password',payload={'email':A['email'],'password':'isolated-password'}))
    assert 'internal provider diagnostic' not in str(error.value)
    assert 'Authorization' not in seen[1].headers


def test_unconfirmed_username_login_has_actionable_message(monkeypatch):
    import asyncio
    original=httpx.AsyncClient
    def handler(request):
        return httpx.Response(400,json={'error_code':'email_not_confirmed','msg':'Email not confirmed'})
    monkeypatch.setattr(accounts.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    settings=SimpleNamespace(supabase_url='https://one.supabase.co',supabase_publishable_key='public-test-key')
    with pytest.raises(SightLineError) as error:
        asyncio.run(accounts.provider_request(settings,'POST','token?grant_type=password',payload={'email':A['email'],'password':'isolated'}))
    assert error.value.error_code=='EMAIL_NOT_CONFIRMED'
    assert A['email'] not in str(error.value.message)


def test_usernames_accept_spaces_and_leading_numbers(tmp_path):
    store=accounts.AliasStore(tmp_path/'flexible-aliases.db','https://one.supabase.co')
    assert store.save(A,'  123 New User  ')=='123 new user'
    assert store.lookup('123 new user')['user_id']==A['id']
    assert store.save(B,'Jane Doe')=='jane doe'
    with pytest.raises(ConflictError):store.save(B,'123 NEW USER')
    for invalid in ['ab','name@example.com','name/other','name\tother','x'*33]:
        with pytest.raises(Exception):accounts.username_value(invalid)


@pytest.mark.parametrize('correct',[False,True])
def test_pending_account_activation_requires_existing_password(monkeypatch,correct):
    import asyncio
    calls=[]
    stored={'user_id':A['id'],'email':A['email']}
    async def provider(*args,**kwargs):
        if not calls:raise SightLineError('EMAIL_NOT_CONFIRMED','Pending account',401)
        return {'user':A,'access_token':'verified-access','refresh_token':'verified-refresh'}
    async def admin(settings,method,path,payload):
        calls.append((method,path,payload));return {**A,'email':payload['email']}
    monkeypatch.setattr(accounts,'provider_request',provider)
    monkeypatch.setattr(accounts,'admin_request',admin)
    monkeypatch.setattr(accounts,'verify_pending_password',lambda *args:correct)
    if correct:
        result=asyncio.run(accounts.password_session(None,stored,'exact password'))
        assert result['access_token']=='verified-access'
        assert len(calls)==1 and calls[0][:2]==('PUT','users/'+A['id'])
        assert calls[0][2]['email_confirm'] is True and calls[0][2]['email'].endswith('@accounts.sightline.invalid')
    else:
        with pytest.raises(AuthenticationError):asyncio.run(accounts.password_session(None,stored,'wrong password'))
        assert calls==[]


def test_username_registration_uses_server_identifier_and_real_provider(alias_api,test_settings,monkeypatch):
    client,store,calls=alias_api
    monkeypatch.setattr(test_settings,'storage_backend','supabase')
    seen=[]
    async def admin(settings,method,path,payload):
        seen.append(payload)
        assert payload['email'].endswith('@accounts.sightline.invalid')
        assert payload['email_confirm'] is True and payload['password']=='isolated-test-password'
        assert payload['app_metadata']=={'account_kind':'username_only'}
        store.save({'id':A['id'],'email':payload['email']},payload['user_metadata']['username'])
        return {'id':A['id']}
    async def provider(settings,method,path,**kwargs):
        return {'user':A,'access_token':'verified-access','refresh_token':'verified-refresh'}
    monkeypatch.setattr(accounts,'admin_request',admin);monkeypatch.setattr(accounts,'provider_request',provider)
    r=client.post('/api/v1/auth/register',json={'username':'New User','password':'isolated-test-password','email':'attacker@example.test','user_id':B['id']})
    assert r.status_code==201,r.text
    assert r.json()=={'access_token':'verified-access','refresh_token':'verified-refresh'}
    assert r.headers['cache-control']=='no-store' and len(seen)==1
    assert store.lookup('new user')['user_id']==A['id']
    duplicate=client.post('/api/v1/auth/register',json={'username':'NEW USER','password':'isolated-test-password'})
    assert duplicate.status_code==409 and len(seen)==1
    for password in ['short','😀'*19]:
        r=client.post('/api/v1/auth/register',json={'username':'valid user','password':password})
        assert r.status_code==422 and password not in r.text
    assert len(seen)==1


def test_username_registration_fails_without_private_storage(alias_api):
    client,store,calls=alias_api
    r=client.post('/api/v1/auth/register',json={'username':'new user','password':'isolated-test-password'})
    assert r.status_code==503 and store.lookup('new user') is None


def test_registration_password_keeps_exact_value():
    assert accounts.registration_password(' exact spaces ')==' exact spaces '
    with pytest.raises(Exception):accounts.registration_password('😀'*19)
