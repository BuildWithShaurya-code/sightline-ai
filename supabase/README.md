# Supabase persistence

Supabase Auth is the sole identity provider. The browser uses a publishable key; FastAPI verifies user tokens against the project's public signing keys. Secret keys and database credentials remain server-only.

The current cloud implementation uses the private `sightline` PostgreSQL schema and private `source-videos`, `evidence-frames` and `sightline-models` buckets. Owner contact settings use `public.security_settings` with explicit grants and RLS. See [the complete cloud runbook](../docs/CLOUD_DEPLOYMENT.md).

Apply the security-settings migration on a new project, then the migration ending `_sightline_private_cloud.sql`. Inspect existing state first; never reset a remote project. The older Phase 2 SQL and `SCHEMA_PLAN.md` are historical design references, not the runtime schema used by this implementation. Do not apply legacy SQL as a prerequisite for the current cloud app.

The public API/worker schema is not exposed to the Data API. The server takes ownership only from verified user identity, never client-supplied owner fields. Use the opt-in integration check and two distinct real test accounts to verify changes. Privileged-key-only reads cannot prove owner isolation.

Official references: [JWT verification](https://supabase.com/docs/guides/auth/jwts), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [Storage access](https://supabase.com/docs/guides/storage/security/access-control).
