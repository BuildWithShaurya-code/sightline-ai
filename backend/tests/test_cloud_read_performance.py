"""Owner context must survive batched setup and nested read scopes."""
from contextlib import contextmanager
from types import SimpleNamespace
import json
import threading
import pytest
from app.db.postgres import Connection, CloudDatabase
from app.db.database import DatabaseManager
from app.core.identity import owner_id

class Raw:
    closed = False
    def __init__(self, fail=False):
        self.calls=[]
        self.fail=fail
    @contextmanager
    def pipeline(self):
        self.calls.append(('pipeline-enter',))
        yield
        if self.fail:
            raise ValueError('setup rejected')
        self.calls.append(('pipeline-exit',))
    def execute(self, sql, params=()):
        self.calls.append((sql, params))

class Pool:
    def __init__(self, raw):
        self.raw=raw
        self.returned=[]
    def getconn(self, timeout):
        return self.raw
    def putconn(self, raw):
        self.returned.append(raw)

def connection(raw):
    return Connection(SimpleNamespace(pool=Pool(raw), settings=SimpleNamespace(cloud_worker=False)))

def test_batched_setup_has_real_owner_and_finishes_before_read():
    raw=Raw();conn=connection(raw);token=owner_id.set('verified-owner-a')
    try:
        with conn.read_scope():
            assert raw.calls[-1][0]=='pipeline-exit'
            claim=next(c for c in raw.calls if c[0].startswith('SELECT set_config'))
            assert json.loads(claim[1][0])=={'sub':'verified-owner-a','role':'authenticated'}
            assert any(c[0]=='SET LOCAL ROLE sightline_api' for c in raw.calls)
            with conn.read_scope():
                assert conn.raw is raw
            assert conn.raw is raw
        assert raw.calls[-1][0]=='COMMIT'
        assert len(conn.db.pool.returned)==1
        assert conn.raw is None
    finally:
        owner_id.reset(token)

def test_failed_setup_rolls_back_and_never_yields_for_application_sql():
    raw=Raw(fail=True);conn=connection(raw)
    with pytest.raises(ValueError, match='setup rejected'):
        with conn.read_scope():
            pytest.fail('Read must not run after rejected identity setup')
    assert raw.calls[-1][0]=='ROLLBACK'
    assert conn.raw is None
    assert len(conn.db.pool.returned)==1

def test_read_error_rolls_back_without_retaining_a_borrowed_connection():
    raw=Raw();conn=connection(raw)
    with pytest.raises(RuntimeError):
        with conn.read_scope():
            raise RuntimeError('database unavailable')
    assert raw.calls[-1][0]=='ROLLBACK'
    assert conn.raw is None

@pytest.mark.parametrize('size',[0,1,10])
def test_history_batches_reads_and_signing_without_per_incident_queries(monkeypatch,size):
    fields=['id','source_id','created_at','review_status','evidence_cleared','title']
    incidents=[(str(i),'source','2026-10-19T00:00:00Z','unreviewed',0,'Test alert') for i in range(size)]
    class Cursor:
        def __init__(self,names,rows):
            self.description=[SimpleNamespace(name=n) for n in names]
            self.rows=rows;self.rowcount=len(rows)
        def fetchall(self):return self.rows
    class PageRaw(Raw):
        def execute(self,sql,params=()):
            super().execute(sql,params)
            if sql.startswith('SELECT COUNT'):return Cursor(['total'],[(size,)])
            if sql.startswith('SELECT * FROM incidents'):return Cursor(fields,incidents)
            if sql.startswith('SELECT * FROM evidence'):
                assert params[1]=='verified-owner-a'
                return Cursor(['id','incident_id','video_offset_seconds','image_data_url','storage_key'],[(f'f{i}',str(i),i,'',f'owner/frame{i}') for i in range(size)])
            if sql.startswith('SELECT d.*'):return Cursor(['linked_incident_id'],[])
            if sql.startswith('SELECT incident_id,kind'):
                assert params[1]=='verified-owner-a'
                return Cursor(['incident_id','kind'],[])
    raw=PageRaw();conn=connection(raw);db=CloudDatabase.__new__(CloudDatabase)
    monkeypatch.setattr(db,'get_connection',lambda:conn)
    monkeypatch.setattr(db,'get_incident',lambda *a,**kw:pytest.fail('History must not fetch each incident'))
    signed=[]
    def sign(items):
        assert conn.raw is None
        signed.extend(items)
    monkeypatch.setattr(db,'_sign_incident_media',sign)
    result=db.list_incidents(user_id='verified-owner-a',page_size=10,status='unreviewed',search_query='Test',created_after='2026-10-18T00:00:00Z')
    assert len(result['items'])==size and len(signed)==size
    queries=[c for c in raw.calls if c[0].startswith('SELECT') and not c[0].startswith('SELECT set_config')]
    assert len(queries)==(5 if size else 2)
    assert result['pagination']['total_items']==size
    assert 'review_status' in queries[0][0] and 'CAST(created_at AS timestamptz)' in queries[0][0]
    assert queries[0][1][0]=='verified-owner-a'
    assert conn.raw is None
