-- Private server-only schema. No Data API exposure or browser credentials.
BEGIN;
CREATE SCHEMA IF NOT EXISTS sightline;
REVOKE ALL ON SCHEMA sightline FROM PUBLIC, anon, authenticated;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sightline_api') THEN CREATE ROLE sightline_api NOLOGIN NOBYPASSRLS; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sightline_worker') THEN CREATE ROLE sightline_worker NOLOGIN NOBYPASSRLS; END IF;
END $$;
GRANT sightline_api, sightline_worker TO postgres;
GRANT USAGE ON SCHEMA sightline, auth TO sightline_api, sightline_worker;
SET LOCAL search_path = sightline, pg_catalog;
CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                storage_bucket TEXT NOT NULL DEFAULT 'source-videos',
                storage_key TEXT NOT NULL UNIQUE,
                media_dimensions TEXT,
                duration_seconds REAL,
                file_size_bytes INTEGER,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS analysis_jobs (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                targets TEXT NOT NULL,
                confidence_threshold REAL NOT NULL DEFAULT 0.25,
                sample_rate_sec REAL NOT NULL DEFAULT 0.5,
                model_version TEXT NOT NULL DEFAULT 'yolo11n-theft-v1',
                settings TEXT NOT NULL DEFAULT '{}',
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                error_details TEXT,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                incident_id TEXT,
                worker_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_user_idempotency UNIQUE(user_id, idempotency_key)
            );

CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                job_id TEXT REFERENCES analysis_jobs(id) ON DELETE SET NULL,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'Surveillance Node 1',
                zone TEXT NOT NULL DEFAULT 'Retail Floor Zone A',
                severity TEXT NOT NULL DEFAULT 'medium',
                reason TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                reviewer_id TEXT,
                reviewer_notes TEXT,
                reviewed_at TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0,
 evidence_cleared INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL DEFAULT 'key_frame',
                storage_bucket TEXT NOT NULL DEFAULT 'evidence-frames',
                storage_key TEXT NOT NULL,
                video_offset_seconds REAL,
                media_dimensions TEXT,
                image_data_url TEXT,
                created_at TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS detections (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
                class_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                box TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                video_offset_seconds REAL NOT NULL,
                created_at TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS incident_detection_links (
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                detection_id TEXT NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (incident_id, detection_id)
            );

CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                actor_id TEXT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                request_id TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

CREATE TABLE IF NOT EXISTS dispatches (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'telegram',
                destination_reference TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'simulated_provider',
                provider_reference TEXT,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                is_simulated INTEGER NOT NULL DEFAULT 0,
                failure_reason TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT,
                cancelled_at TEXT,
                cancelled_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_dispatch_idempotency UNIQUE(user_id, idempotency_key)
            );

CREATE TABLE IF NOT EXISTS operator_security (
                user_id TEXT PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_failed_at TEXT,
                updated_at TEXT NOT NULL
            );

CREATE INDEX IF NOT EXISTS idx_sources_user ON sources(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON analysis_jobs(user_id, status);

CREATE INDEX IF NOT EXISTS idx_jobs_queued ON analysis_jobs(status, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_incidents_user ON incidents(user_id, is_deleted, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id);

CREATE INDEX IF NOT EXISTS idx_detections_job ON detections(job_id);

CREATE INDEX IF NOT EXISTS idx_dispatches_user ON dispatches(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dispatches_incident ON dispatches(incident_id);

CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status);

CREATE TABLE IF NOT EXISTS response_contacts (
                user_id TEXT PRIMARY KEY, "securityName" TEXT NOT NULL DEFAULT '',
                "securityPhone" TEXT NOT NULL DEFAULT '', "policePhone" TEXT NOT NULL DEFAULT '112',
                "siteAddress" TEXT NOT NULL DEFAULT ''
            );

CREATE TABLE IF NOT EXISTS response_events (
                seq BIGSERIAL PRIMARY KEY, event_id TEXT NOT NULL,
                incident_id TEXT NOT NULL REFERENCES incidents(id), user_id TEXT NOT NULL,
                kind TEXT NOT NULL, recipient TEXT NOT NULL, detail TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(user_id, incident_id, event_id)
            );

CREATE INDEX IF NOT EXISTS idx_response_incident ON response_events(incident_id, user_id, seq);

ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS lease_until timestamptz;
CREATE TABLE IF NOT EXISTS worker_heartbeats(id TEXT PRIMARY KEY,seen_at timestamptz NOT NULL,model_loaded boolean NOT NULL);
CREATE TABLE IF NOT EXISTS aliases(project TEXT NOT NULL,user_id TEXT NOT NULL,username TEXT NOT NULL,email TEXT NOT NULL,PRIMARY KEY(project,user_id),UNIQUE(project,username));
CREATE INDEX IF NOT EXISTS idx_heartbeat_seen ON worker_heartbeats(seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON analysis_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_incidents_source ON incidents(source_id);
CREATE INDEX IF NOT EXISTS idx_incidents_job ON incidents(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_detections_source ON detections(source_id);
CREATE INDEX IF NOT EXISTS idx_detections_evidence ON detections(evidence_id);
CREATE INDEX IF NOT EXISTS idx_link_detection ON incident_detection_links(detection_id);
CREATE INDEX IF NOT EXISTS idx_jobs_leases ON analysis_jobs(lease_until) WHERE status='processing';

ALTER TABLE sightline.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.sources FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.sources TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.sources TO sightline_api;
CREATE POLICY worker_access ON sightline.sources TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.sources TO sightline_worker;
ALTER TABLE sightline.analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.analysis_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.analysis_jobs TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.analysis_jobs TO sightline_api;
CREATE POLICY worker_access ON sightline.analysis_jobs TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.analysis_jobs TO sightline_worker;
ALTER TABLE sightline.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.incidents FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.incidents TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.incidents TO sightline_api;
CREATE POLICY worker_access ON sightline.incidents TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.incidents TO sightline_worker;
ALTER TABLE sightline.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.evidence FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.evidence TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.evidence TO sightline_api;
CREATE POLICY worker_access ON sightline.evidence TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.evidence TO sightline_worker;
ALTER TABLE sightline.detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.detections FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.detections TO sightline_api USING (EXISTS (SELECT 1 FROM sightline.analysis_jobs j WHERE j.id=job_id AND j.user_id=(SELECT auth.uid())::text)) WITH CHECK (EXISTS (SELECT 1 FROM sightline.analysis_jobs j WHERE j.id=job_id AND j.user_id=(SELECT auth.uid())::text));
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.detections TO sightline_api;
CREATE POLICY worker_access ON sightline.detections TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.detections TO sightline_worker;
ALTER TABLE sightline.incident_detection_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.incident_detection_links FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.incident_detection_links TO sightline_api USING (EXISTS (SELECT 1 FROM sightline.incidents i WHERE i.id=incident_id AND i.user_id=(SELECT auth.uid())::text) AND EXISTS (SELECT 1 FROM sightline.detections d WHERE d.id=detection_id)) WITH CHECK (EXISTS (SELECT 1 FROM sightline.incidents i WHERE i.id=incident_id AND i.user_id=(SELECT auth.uid())::text) AND EXISTS (SELECT 1 FROM sightline.detections d WHERE d.id=detection_id));
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.incident_detection_links TO sightline_api;
CREATE POLICY worker_access ON sightline.incident_detection_links TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.incident_detection_links TO sightline_worker;
ALTER TABLE sightline.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.audit_events TO sightline_api USING (actor_id = (SELECT auth.uid())::text) WITH CHECK (actor_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.audit_events TO sightline_api;
CREATE POLICY worker_access ON sightline.audit_events TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.audit_events TO sightline_worker;
ALTER TABLE sightline.dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.dispatches FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.dispatches TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.dispatches TO sightline_api;
ALTER TABLE sightline.operator_security ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.operator_security FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.operator_security TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.operator_security TO sightline_api;
ALTER TABLE sightline.response_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.response_contacts FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.response_contacts TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.response_contacts TO sightline_api;
ALTER TABLE sightline.response_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.response_events FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.response_events TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.response_events TO sightline_api;
ALTER TABLE sightline.worker_heartbeats ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.worker_heartbeats FORCE ROW LEVEL SECURITY;
CREATE POLICY worker_access ON sightline.worker_heartbeats TO sightline_worker USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON sightline.worker_heartbeats TO sightline_worker;
ALTER TABLE sightline.aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.aliases FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_access ON sightline.aliases TO sightline_api USING (user_id = (SELECT auth.uid())::text) WITH CHECK (user_id = (SELECT auth.uid())::text);
GRANT SELECT,INSERT,UPDATE,DELETE ON sightline.aliases TO sightline_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA sightline TO sightline_api, sightline_worker;

-- These private aggregates expose no records. Only the server's API role can call them.
CREATE FUNCTION sightline.pending_job_count() RETURNS bigint LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT CASE WHEN (SELECT auth.uid()) IS NULL THEN 0 ELSE (SELECT count(*) FROM sightline.analysis_jobs WHERE status IN ('queued','processing')) END
$$;
CREATE FUNCTION sightline.worker_ready() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT EXISTS(SELECT 1 FROM sightline.worker_heartbeats WHERE seen_at>now()-interval '35 seconds' AND model_loaded)
$$;
-- A username never returns credentials. The API must complete Supabase password verification
-- and compare its returned user ID before returning an authenticated session.
CREATE FUNCTION sightline.alias_lookup(project_name text, alias_name text) RETURNS TABLE(user_id text,email text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT a.user_id,a.email FROM sightline.aliases a WHERE a.project=project_name AND a.username=alias_name LIMIT 1
$$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sightline FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION sightline.pending_job_count(), sightline.worker_ready(), sightline.alias_lookup(text,text) TO sightline_api;
GRANT EXECUTE ON FUNCTION sightline.pending_job_count(), sightline.worker_ready() TO sightline_worker;
COMMIT;
