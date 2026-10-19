"""Supabase-only identity. The local arbitrary-password token route is removed."""
def test_legacy_login_is_removed(client):
    for payload in [{'operatorId':'OP-991','passcode':'secret123'}, {'operatorId':'OP-991','passcode':'12'}]:
        assert client.post('/api/v1/auth/login',json=payload).status_code==404

def test_auth_me_accepts_verified_project_token(client,valid_auth_headers):
    res=client.get('/api/v1/auth/me',headers=valid_auth_headers)
    assert res.status_code==200
    assert res.json()['id']=='00000000-0000-0000-0000-000000000001'
    assert res.json()['role']=='authenticated'

def test_auth_me_requires_token(client):
    assert client.get('/api/v1/auth/me').status_code==401
