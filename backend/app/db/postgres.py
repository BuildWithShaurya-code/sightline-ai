"""PostgreSQL persistence with transaction-local identities and bounded connections.

The private schema is installed by a reviewed migration, never at application startup.
Existing local transactions are retained while their few SQLite expressions are adapted.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
import base64
import json
import re
import sqlite3
import threading
import uuid

from .database import DatabaseManager
from ..core.identity import owner_id


class Row:
    def __init__(self, names, values):
        self.names, self.values = names, values
    def keys(self):
        return self.names
    def __getitem__(self, key):
        return self.values[key if isinstance(key, int) else self.names.index(key)]
    def __iter__(self):
        return iter(self.values)


class Result:
    def __init__(self, cursor=None):
        self.rowcount = cursor.rowcount if cursor else 0
        self.rows = []
        if cursor is not None and cursor.description:
            names = [c.name for c in cursor.description]
            self.rows = [Row(names, row) for row in cursor.fetchall()]
    def fetchone(self):
        return self.rows.pop(0) if self.rows else None
    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows
    def __iter__(self):
        return iter(self.fetchall())


def postgres_sql(query):
    query = query.strip().rstrip(';')
    query = re.sub(r'julianday\(([^)]+)\)', r'CAST(\1 AS timestamptz)', query)
    query = query.replace('SUM(user_id = ?)', 'SUM((user_id = ?)::int)')
    # The total queue count is a narrowly scoped, private aggregate, not owner rows.
    if query.startswith('SELECT COUNT(*), COALESCE(SUM('):
        query = query.replace('COUNT(*)', '(SELECT sightline.pending_job_count())', 1)
    for name in ('securityName', 'securityPhone', 'policePhone', 'siteAddress'):
        query = re.sub(r'(?<!["\w])' + name + r'(?!["\w])', '"' + name + '"', query)
    if 'INSERT OR IGNORE INTO' in query:
        query = query.replace('INSERT OR IGNORE INTO', 'INSERT INTO') + ' ON CONFLICT DO NOTHING'
    return query.replace('?', '%s')


class Connection:
    """A borrowed connection lives only for one statement or explicit transaction."""
    def __init__(self, db):
        self.db, self.raw = db, None

    def begin(self):
        import psycopg
        from ..core.errors import ServiceUnavailableError
        for attempt in range(2):
            self.raw = self.db.pool.getconn(timeout=10)
            try:
                # Keep identity/role transaction-local, but send setup in one network batch.
                # The pipeline exits (and raises on any error) before application SQL runs.
                role = 'sightline_worker' if self.db.settings.cloud_worker else 'sightline_api'
                claims = {'sub': owner_id.get(), 'role': 'authenticated'} if owner_id.get() else {}
                with self.raw.pipeline():
                    self.raw.execute('BEGIN')
                    self.raw.execute('SET LOCAL ROLE ' + role)
                    self.raw.execute("SET LOCAL search_path = sightline, pg_catalog")
                    self.raw.execute("SET LOCAL statement_timeout = '15s'")
                    self.raw.execute("SET LOCAL lock_timeout = '8s'")
                    self.raw.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
                return
            except psycopg.OperationalError:
                self.finish(False)
                if attempt:
                    raise ServiceUnavailableError('Private account storage is temporarily unavailable. Please retry.') from None
            except Exception:
                self.finish(False)
                raise

    def finish(self, commit):
        if self.raw is not None:
            raw, self.raw = self.raw, None
            try:
                if not raw.closed:
                    raw.execute('COMMIT' if commit else 'ROLLBACK')
            finally:
                self.db.pool.putconn(raw)

    def execute(self, query, params=()):
        command = query.strip().rstrip(';').upper()
        if command in ('BEGIN', 'BEGIN IMMEDIATE'):
            if self.raw is not None:
                raise RuntimeError('Nested cloud transactions are not supported')
            self.begin()
            self.raw.execute('SELECT pg_advisory_xact_lock(734112907)')
            return Result()
        if command in ('COMMIT', 'ROLLBACK'):
            self.finish(command == 'COMMIT')
            return Result()
        single = self.raw is None
        try:
            if single:
                self.begin()
            result = Result(self.raw.execute(postgres_sql(query), tuple(params)))
            if single:
                self.finish(True)
            return result
        except Exception as exc:
            if single:
                self.finish(False)
            if getattr(exc, 'sqlstate', '') == '23505':
                raise sqlite3.IntegrityError('A unique account record already exists') from None
            raise

    @contextmanager
    def read_scope(self):
        """Reuse identity setup for related reads without taking the write lock."""
        owns_transaction = self.raw is None
        if owns_transaction:
            self.begin()
        try:
            yield self
        except Exception:
            if owns_transaction:
                self.finish(False)
            raise
        else:
            if owns_transaction:
                self.finish(True)

    def close(self):
        self.finish(False)


class CloudDatabase(DatabaseManager):
    def __init__(self, settings):
        from psycopg_pool import ConnectionPool
        self.settings = settings
        self._local = threading.local()
        self.pool = ConnectionPool(
            settings.cloud_database_url.get_secret_value(), min_size=0, max_size=4,
            open=True, timeout=10, max_idle=60, max_lifetime=300,
            check=ConnectionPool.check_connection,
            kwargs={'autocommit': True, 'prepare_threshold': None, 'connect_timeout': 10,
                    'sslmode': 'verify-full', 'sslrootcert': str(settings.cloud_database_ca)},
        )

    def get_connection(self):
        if not hasattr(self._local, 'conn'):
            self._local.conn = Connection(self)
        return self._local.conn

    def close_all(self):
        self.get_connection().close()
        self.pool.close()

    def claim_next_queued_job(self, worker_id, *, job_id=None):
        conn = self.get_connection()
        conn.execute('BEGIN')
        try:
            query = "SELECT id FROM analysis_jobs WHERE status='queued'"
            params = ()
            if job_id is not None:
                query += ' AND id=?'
                params = (job_id,)
            row = conn.execute(query + ' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1', params).fetchone()
            if not row:
                conn.execute('COMMIT')
                return None
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE analysis_jobs SET status='processing',worker_id=?,started_at=?,updated_at=?,lease_until=now()+interval '90 seconds' WHERE id=? AND status='queued'", (worker_id, now, now, row['id']))
            job = self.get_job(row['id'])
            conn.execute('COMMIT')
            return job
        except Exception:
            conn.execute('ROLLBACK')
            raise

    def heartbeat(self, worker_id, loaded=True):
        conn = self.get_connection()
        conn.execute("INSERT INTO worker_heartbeats(id,seen_at,model_loaded) VALUES(?,now(),?) ON CONFLICT(id) DO UPDATE SET seen_at=excluded.seen_at,model_loaded=excluded.model_loaded", (worker_id, loaded))
        conn.execute("UPDATE analysis_jobs SET lease_until=now()+interval '90 seconds' WHERE worker_id=? AND status='processing' AND lease_until>now()", (worker_id,))

    def expire_leases(self, *, job_id=None):
        now = datetime.now(timezone.utc).isoformat()
        query = "UPDATE analysis_jobs SET status=CASE WHEN cancellation_requested=1 THEN 'cancelled' ELSE 'failed' END,error_message='Worker stopped before completing analysis. Please submit again.',completed_at=?,updated_at=? WHERE status='processing' AND worker_id IS NOT NULL AND lease_until<now()"
        params = (now, now)
        if job_id is not None:
            query += ' AND id=?'
            params += (job_id,)
        self.get_connection().execute(query, params)

    def worker_ready(self):
        return bool(self.get_connection().execute('SELECT sightline.worker_ready()').fetchone()[0])

    def _persist_frames(self, evidence):
        from ..services.cloud_storage import CloudStorage
        storage = CloudStorage(self.settings)
        for ev in evidence:
            data = ev.get('image_data_url')
            if data and data.startswith('data:image/jpeg;base64,'):
                key = f"{ev['user_id']}/{ev['source_id']}/{uuid.uuid4().hex}.jpg"
                storage.upload('evidence-frames', key, base64.b64decode(data.split(',', 1)[1], validate=True), 'image/jpeg')
                ev['storage_bucket'], ev['storage_key'], ev['image_data_url'] = 'evidence-frames', key, None

    def finalize_analysis_results(self, job_id, incident_dict, evidence_list, detections_list, new_source=None, new_job=None):
        # Upload immutable evidence before publishing a completed DB transaction.
        self._persist_frames(evidence_list)
        if new_source is not None and evidence_list:
            new_source['storage_key'] = evidence_list[0]['storage_key']
        try:
            return super().finalize_analysis_results(job_id, incident_dict, evidence_list, detections_list, new_source, new_job)
        finally:
            self._remove_unreferenced_frames(evidence_list)

    def append_automatic_evidence(self, incident_id, user_id, job_id, evidence, detections):
        self._persist_frames([evidence])
        try:
            return super().append_automatic_evidence(incident_id, user_id, job_id, evidence, detections)
        finally:
            self._remove_unreferenced_frames([evidence])

    def _remove_unreferenced_frames(self, evidence):
        from ..services.cloud_storage import CloudStorage
        for ev in evidence:
            key = ev['storage_key']
            try:
                referenced = self.get_connection().execute('SELECT 1 FROM evidence WHERE storage_key=?', (key,)).fetchone()
                if not referenced:
                    CloudStorage(self.settings).bucket('evidence-frames').remove([key])
            except Exception:
                # A failed lookup must never delete possibly committed evidence.
                import logging
                logging.getLogger('sightline.storage').warning('Unreferenced-frame cleanup deferred because storage or database is unavailable.')

    def get_incident(self, incident_id, user_id=None):
        with self.get_connection().read_scope():
            incident = super().get_incident(incident_id, user_id)
            if not incident or not incident['frames']:
                return incident
            rows = self.get_connection().execute('SELECT id,storage_key FROM evidence WHERE incident_id=?', (incident_id,)).fetchall()
        keys = {row['id']: row['storage_key'] for row in rows}
        self._sign_incident_media([(incident, keys)])
        return incident

    def _sign_incident_media(self, items):
        from ..services.cloud_storage import CloudStorage
        keys = list(dict.fromkeys(key for _, mapping in items for key in mapping.values()))
        if not keys:
            return
        urls = CloudStorage(self.settings).signed_urls('evidence-frames', keys)
        for incident, mapping in items:
            for frame in incident['frames']:
                frame['imageDataUrl'] = urls[mapping[frame['id']]]
            incident['thumbnail'] = incident['frames'][0]['imageDataUrl']

    def list_incidents(self, user_id, status=None, search_query=None, page=1, page_size=20, created_after=None):
        from .incident_view import incident_view
        from ..services.security_response import response_label
        conn = self.get_connection()
        clauses, params = ['user_id = ?', 'is_deleted = 0'], [user_id]
        if status:
            clauses.append('review_status = ?'); params.append(status)
        if search_query:
            clauses.append('(title LIKE ? OR channel LIKE ? OR zone LIKE ? OR id LIKE ? OR source_id LIKE ? OR EXISTS (SELECT 1 FROM sources s WHERE s.id = incidents.source_id AND s.original_filename LIKE ?))')
            params.extend(['%'+search_query+'%']*6)
        if created_after:
            clauses.append('julianday(created_at) >= julianday(?)'); params.append(created_after)
        where = ' AND '.join(clauses)
        with conn.read_scope():
            total = conn.execute('SELECT COUNT(*) AS total FROM incidents WHERE '+where, params).fetchone()['total']
            rows = conn.execute('SELECT * FROM incidents WHERE '+where+' ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?', params+[page_size,max(0,(page-1)*page_size)]).fetchall()
            ids = [row['id'] for row in rows]
            evidence, detections, events = [], [], []
            if ids:
                # Three queries for the entire page, sent together. RLS is still active.
                with conn.raw.pipeline():
                    ev_cursor = conn.raw.execute('SELECT * FROM evidence WHERE incident_id = ANY(%s) AND user_id=%s ORDER BY video_offset_seconds ASC', (ids,user_id))
                    det_cursor = conn.raw.execute('SELECT d.*, l.incident_id AS linked_incident_id FROM detections d JOIN incident_detection_links l ON d.id=l.detection_id WHERE l.incident_id = ANY(%s) ORDER BY d.confidence DESC', (ids,))
                    event_cursor = conn.raw.execute('SELECT incident_id,kind FROM response_events WHERE incident_id = ANY(%s) AND user_id=%s', (ids,user_id))
                evidence = Result(ev_cursor).fetchall()
                detections = Result(det_cursor).fetchall()
                events = Result(event_cursor).fetchall()
        by_evidence, by_detection, by_event = {}, {}, {}
        for ev in evidence: by_evidence.setdefault(ev['incident_id'],[]).append(ev)
        for det in detections: by_detection.setdefault(det['linked_incident_id'],[]).append(det)
        for event in events: by_event.setdefault(event['incident_id'],[]).append(event['kind'])
        items, media = [], []
        for row in rows:
            id = row['id']; ev = by_evidence.get(id,[])
            item = incident_view(row,ev,by_detection.get(id,[]),response_label(by_event.get(id,[]),row['review_status']))
            items.append(item)
            if item['frames']:media.append((item,{frame['id']:frame['storage_key'] for frame in ev}))
        self._sign_incident_media(media)
        return {'items':items,'pagination':{'page':page,'page_size':page_size,'total_items':total,'total_pages':max(1,(total+page_size-1)//page_size)}}
