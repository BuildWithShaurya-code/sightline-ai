"""The account service does not depend on model availability or inference imports."""
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.identity import app


def test_identity_rejects_anonymous_and_legacy_login():
    with TestClient(app) as client:
        response=client.get('/api/v1/auth/me')
        assert response.status_code==401
        assert response.headers['cache-control']=='no-store'
        assert client.post('/api/v1/auth/login',json={'username':'anything','password':'anything'}).status_code==404
        assert client.get('/api/v1/incidents').status_code==404


def test_identity_import_does_not_load_neural_stack():
    backend=Path(__file__).resolve().parents[1]
    script="import sys;import app.identity;assert not any(n in sys.modules for n in ['cv2','torch','ultralytics','app.services.inference_service']);print('lightweight')"
    result=subprocess.run([sys.executable,'-c',script],cwd=backend,text=True,capture_output=True,timeout=20)
    assert result.returncode==0, result.stderr
    assert result.stdout.strip()=='lightweight'
