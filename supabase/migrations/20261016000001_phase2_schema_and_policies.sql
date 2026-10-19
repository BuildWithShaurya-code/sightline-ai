-- ==============================================================================
-- SightLine AI / Theft Retirement System - Phase 2 Schema & Security Migration
-- Migration: 20261016000001_phase2_schema_and_policies.sql
-- Targets: Profiles, Sources, Analysis Jobs, Detections, Incidents, Evidence,
--          Incident Detection Links, Dispatches, Audit Events, Operator Security,
--          Row Level Security (RLS) policies, and Storage policies.
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. APPLICATION TABLES
-- ==============================================================================

-- 2.1 Operator Profiles (linked to auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    operator_identifier TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.2 Surveillance Media Sources
CREATE TABLE IF NOT EXISTS public.sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('video_upload', 'live_stream', 'cctv_feed', 'demo_clip')),
    original_filename TEXT NOT NULL,
    storage_bucket TEXT NOT NULL DEFAULT 'source-videos',
    storage_key TEXT NOT NULL,
    media_dimensions JSONB DEFAULT NULL,
    duration_seconds NUMERIC(8, 2) DEFAULT NULL,
    file_size_bytes BIGINT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('uploading', 'ready', 'failed', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_source_storage_key UNIQUE (storage_bucket, storage_key)
);

-- 2.3 Analysis Processing Jobs
CREATE TABLE IF NOT EXISTS public.analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    targets TEXT[] NOT NULL DEFAULT ARRAY['person', 'mask', 'knife']::TEXT[],
    confidence_threshold NUMERIC(4, 3) NOT NULL DEFAULT 0.450 CHECK (confidence_threshold >= 0.0 AND confidence_threshold <= 1.0),
    model_version TEXT NOT NULL DEFAULT 'yolo11n-theft-v1',
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    error_message TEXT DEFAULT NULL,
    error_details JSONB DEFAULT NULL,
    cancellation_requested BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ DEFAULT NULL,
    completed_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.4 Neural Detections (Strictly 3 classes: person, mask, knife)
CREATE TABLE IF NOT EXISTS public.detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES public.analysis_jobs(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL CHECK (class_id IN ('person', 'mask', 'knife')),
    class_index SMALLINT NOT NULL CHECK (class_index IN (0, 1, 2)),
    class_name TEXT NOT NULL CHECK (class_name IN ('person', 'mask', 'knife')),
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    box INTEGER[] NOT NULL CHECK (array_length(box, 1) = 4),
    frame_index INTEGER NOT NULL CHECK (frame_index >= 0),
    video_offset_seconds NUMERIC(8, 3) NOT NULL CHECK (video_offset_seconds >= 0.0),
    frame_dimensions INTEGER[] NOT NULL CHECK (array_length(frame_dimensions, 1) = 2),
    model_version TEXT NOT NULL DEFAULT 'yolo11n-theft-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_detection_class_consistency CHECK (
        (class_index = 0 AND class_id = 'person' AND class_name = 'person') OR
        (class_index = 1 AND class_id = 'mask' AND class_name = 'mask') OR
        (class_index = 2 AND class_id = 'knife' AND class_name = 'knife')
    )
);

-- 2.5 Security Incidents & Threat Events
CREATE TABLE IF NOT EXISTS public.incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
    job_id UUID REFERENCES public.analysis_jobs(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'Surveillance Node 1',
    zone TEXT NOT NULL DEFAULT 'Retail Floor Zone A',
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    reason TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'confirmed_threat', 'dismissed_threat')),
    reviewer_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    reviewer_notes TEXT DEFAULT NULL,
    reviewed_at TIMESTAMPTZ DEFAULT NULL,
    original_dimensions INTEGER[] DEFAULT NULL CHECK (original_dimensions IS NULL OR array_length(original_dimensions, 1) = 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.6 Incident Evidence (Key frames, crops, clips)
CREATE TABLE IF NOT EXISTS public.evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('key_frame', 'annotated_frame', 'video_clip')),
    storage_bucket TEXT NOT NULL CHECK (storage_bucket IN ('evidence-frames', 'evidence-clips')),
    storage_key TEXT NOT NULL,
    video_offset_seconds NUMERIC(8, 3) DEFAULT NULL CHECK (video_offset_seconds IS NULL OR video_offset_seconds >= 0.0),
    media_dimensions INTEGER[] DEFAULT NULL CHECK (media_dimensions IS NULL OR array_length(media_dimensions, 1) = 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.7 Incident - Detection Junction Table
CREATE TABLE IF NOT EXISTS public.incident_detection_links (
    incident_id UUID NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
    detection_id UUID NOT NULL REFERENCES public.detections(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (incident_id, detection_id)
);

-- 2.8 Security Dispatches
CREATE TABLE IF NOT EXISTS public.dispatches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('police_dispatch', 'security_guard', 'sms_alert', 'email_notification')),
    destination_reference TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'simulated_provider',
    provider_reference TEXT DEFAULT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed', 'cancelled')),
    failure_reason TEXT DEFAULT NULL,
    delivered_at TIMESTAMPTZ DEFAULT NULL,
    cancelled_at TIMESTAMPTZ DEFAULT NULL,
    cancelled_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.9 Immutable Audit Events Log
CREATE TABLE IF NOT EXISTS public.audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT DEFAULT NULL,
    request_id TEXT DEFAULT NULL,
    ip_address TEXT DEFAULT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- 2.10 Operator Security (PIN hash & Lockout tracking - Server access only)
CREATE TABLE IF NOT EXISTS public.operator_security (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    pin_hash TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until TIMESTAMPTZ DEFAULT NULL,
    last_failed_at TIMESTAMPTZ DEFAULT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

-- ==============================================================================
-- 3. PERFORMANCE & QUERY INDEXES
-- ==============================================================================

CREATE INDEX IF NOT EXISTS idx_sources_user_created ON public.sources(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_source ON public.analysis_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_user_status ON public.analysis_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_detections_job_frame ON public.detections(job_id, frame_index);
CREATE INDEX IF NOT EXISTS idx_detections_source ON public.detections(source_id);
CREATE INDEX IF NOT EXISTS idx_incidents_user_created ON public.incidents(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_source ON public.incidents(source_id);
CREATE INDEX IF NOT EXISTS idx_incidents_job ON public.incidents(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_incident ON public.evidence(incident_id);
CREATE INDEX IF NOT EXISTS idx_evidence_user ON public.evidence(user_id);
CREATE INDEX IF NOT EXISTS idx_dispatches_incident ON public.dispatches(incident_id);
CREATE INDEX IF NOT EXISTS idx_dispatches_user_status ON public.dispatches(user_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON public.audit_events(actor_id, created_at DESC);

-- ==============================================================================
-- 4. ROW LEVEL SECURITY (RLS) ACTIVATION
-- ==============================================================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_detection_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operator_security ENABLE ROW LEVEL SECURITY;

-- ==============================================================================
-- 5. LEAST-PRIVILEGE PERMISSIONS (GRANTS)
-- ==============================================================================

-- Revoke all public/anon/authenticated access to server-only security table
REVOKE ALL ON public.operator_security FROM anon, authenticated, public;

-- Revoke all default table permissions from anon (Anonymous cannot read application data)
REVOKE ALL ON public.profiles FROM anon;
REVOKE ALL ON public.sources FROM anon;
REVOKE ALL ON public.analysis_jobs FROM anon;
REVOKE ALL ON public.detections FROM anon;
REVOKE ALL ON public.incidents FROM anon;
REVOKE ALL ON public.evidence FROM anon;
REVOKE ALL ON public.incident_detection_links FROM anon;
REVOKE ALL ON public.dispatches FROM anon;
REVOKE ALL ON public.audit_events FROM anon;

-- Explicit grants for authenticated users
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sources TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.analysis_jobs TO authenticated;
GRANT SELECT ON public.detections TO authenticated; -- Server-generated only!
GRANT SELECT, INSERT, UPDATE, DELETE ON public.incidents TO authenticated;
GRANT SELECT ON public.evidence TO authenticated; -- Server-generated only!
GRANT SELECT ON public.incident_detection_links TO authenticated; -- Server-generated only!
GRANT SELECT, INSERT, UPDATE ON public.dispatches TO authenticated;
GRANT SELECT ON public.audit_events TO authenticated;

-- Service role has full access to all tables
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;

-- ==============================================================================
-- 6. RLS POLICIES
-- ==============================================================================

-- 6.1 Profiles Policies
CREATE POLICY "profiles_select_own" ON public.profiles
    FOR SELECT TO authenticated
    USING (auth.uid() = id);

CREATE POLICY "profiles_insert_own" ON public.profiles
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = id);

CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- 6.2 Sources Policies
CREATE POLICY "sources_select_own" ON public.sources
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "sources_insert_own" ON public.sources
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "sources_update_own" ON public.sources
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "sources_delete_own" ON public.sources
    FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- 6.3 Analysis Jobs Policies (Prevent cross-owner source attachment)
CREATE POLICY "jobs_select_own" ON public.analysis_jobs
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "jobs_insert_own" ON public.analysis_jobs
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.sources s
            WHERE s.id = source_id AND s.user_id = auth.uid()
        )
    );

CREATE POLICY "jobs_update_own" ON public.analysis_jobs
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id AND
        status IN ('queued', 'cancelled')
    );

-- 6.4 Detections Policies (Read-only via owned jobs, writes strictly by service_role)
CREATE POLICY "detections_select_own_job" ON public.detections
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.analysis_jobs j
            WHERE j.id = detections.job_id AND j.user_id = auth.uid()
        )
    );

-- 6.5 Incidents Policies (Prevent cross-owner references)
CREATE POLICY "incidents_select_own" ON public.incidents
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "incidents_insert_own" ON public.incidents
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.sources s
            WHERE s.id = source_id AND s.user_id = auth.uid()
        )
    );

CREATE POLICY "incidents_update_own" ON public.incidents
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "incidents_delete_own" ON public.incidents
    FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- 6.6 Evidence Policies (Read-only via owned incidents, writes strictly by service_role)
CREATE POLICY "evidence_select_own" ON public.evidence
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

-- 6.7 Incident Detection Links Policies (Read-only via owned incidents)
CREATE POLICY "links_select_own" ON public.incident_detection_links
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.incidents i
            WHERE i.id = incident_id AND i.user_id = auth.uid()
        )
    );

-- 6.8 Dispatches Policies
CREATE POLICY "dispatches_select_own" ON public.dispatches
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "dispatches_insert_own" ON public.dispatches
    FOR INSERT TO authenticated
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM public.incidents i
            WHERE i.id = incident_id AND i.user_id = auth.uid()
        )
    );

CREATE POLICY "dispatches_update_own" ON public.dispatches
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 6.9 Audit Events Policies (Read own actions only, writes strictly server/service_role)
CREATE POLICY "audit_select_own" ON public.audit_events
    FOR SELECT TO authenticated
    USING (auth.uid() = actor_id);

-- 6.10 Operator Security Policies (No client access; service_role bypasses RLS)
-- (No policies created for authenticated or anon, guaranteeing denial)

-- ==============================================================================
-- 7. STORAGE POLICIES (FOR PRIVATE BUCKETS)
-- ==============================================================================

-- 7.1 Source Videos: Users can upload, read, and delete their own files
-- Path format: {user_id}/{source_id}/{filename}
CREATE POLICY "storage_source_videos_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'source-videos' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

CREATE POLICY "storage_source_videos_insert" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'source-videos' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

CREATE POLICY "storage_source_videos_delete" ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id = 'source-videos' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

-- 7.2 Evidence Frames: Read-only for authenticated owner; upload/manage by service_role
CREATE POLICY "storage_evidence_frames_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'evidence-frames' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

-- 7.3 Evidence Clips: Read-only for authenticated owner; upload/manage by service_role
CREATE POLICY "storage_evidence_clips_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'evidence-clips' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

-- ==============================================================================
-- 8. AUTOMATIC PROFILE CREATION TRIGGER
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, operator_identifier)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)),
        COALESCE(NEW.raw_user_meta_data->>'operator_identifier', 'OP-' || UPPER(SUBSTRING(NEW.id::text, 1, 6)))
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
