# Deployment preparation — 19 October 2026

Status: local reliability changes verified; Vercel release deferred at the owner’s request. No public site or infrastructure was created. The full backend is not ready to run on Vercel unchanged.

## Changes

- Replaced per-request detached analysis tasks with one application-owned worker consuming persisted jobs. SQLite admission is atomic, limited to 16 pending/processing jobs overall and 4 per account by default. Repeated idempotency keys still return their existing job, including when admission is full. Excess new requests return `429 QUEUE_FULL`.
- A process lock prevents two API processes from competing over this local worker store. Queued jobs resume after startup; jobs interrupted while processing become explicitly failed and can be retried by starting a new analysis. Shutdown asks the worker to stop between frames. The processing deadline is checked between frames; native inference/decoder calls cannot be forcibly interrupted in the middle of a frame. Use one API process on a single persistent disk.
- Claimed-worker ownership is required before processing. Cancelled/finished work cannot be resurrected by late finalization, failure or completion. Candidate evidence frames are bounded during processing as well as in the final selection.
- Readiness requires the worker thread to be alive, along with loaded inference, writable storage and database access. Protected API responses use `no-store`; basic security headers were added. Production health responses omit local storage and model paths.
- Added offline private storage snapshot/restore tooling. Both SQLite databases are copied with SQLite’s backup API; video/evidence files have a checksum manifest. Restores verify integrity and checksums and require a new directory. Existing storage is never overwritten. Files are mode 0600 and snapshot directories mode 0700. Server environment files, model weights and temporary media are excluded. Snapshots contain private account data and PIN hashes and must stay private. A checksum detects accidental corruption, not malicious tampering; keep snapshots in trusted storage.
- Added a frontend-only Vercel configuration and upload allowlist. Its preflight refuses missing/non-public backend origins, non-publishable Supabase keys and obvious server-only browser variables. The API refuses Vercel startup while it still depends on local SQLite/media. No temporary-directory fallback was introduced.

## Verification

- Clean Python 3.12 environment from the earlier dependency repair: **173 backend tests plus 9 independent security gates passed** (182 total). All model/pipeline tests used the original trained checkpoint. Unit recovery tests also use explicitly fake processing for isolated queue cases.
- **8 frontend source check scripts**, TypeScript and the Vite production build passed. The build used Vite’s config runner because the temporary checkout links to a read-only dependency directory. The default config-bundling attempt was blocked by that filesystem permission. The frontend still produces a bundle-size warning.
- New Vercel preflight checks accepted valid fixture settings and rejected 14 unsafe/missing configuration cases. These are local checks, not an actual Vercel build or deployment.
- An actual isolated process crash/restart drill uses generated black clips and the real model. See the timestamped evidence folder for the observed outcome. No owner incident, contact, PIN or credential is used in that drill.
- Backups/restores, corruption rejection, symlink/traversal rejection, refusal to overwrite and running-worker lock rejection passed using disposable fixture data.

## Vercel plan and release blockers

`vercel.json` currently prepares only the Vite frontend. Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` and `VITE_API_URL` in the correct Vercel environment. The backend origin must be an existing, verified HTTPS service; there is no such deployed backend configured by this change. Configure its CORS with the exact frontend origin and add the frontend URL to Supabase’s approved redirect URLs. Do not upload backend/.env, databases, footage, snapshots or weights to a frontend build.

Vercel Services and Container Runtime are currently beta and can package the Python model, but containers still scale down. Packaging alone does not give this app durable SQLite/media or a reliable distributed queue. For a complete Vercel deployment, migrate local incidents, jobs, evidence, PIN state and username aliases to durable account-scoped database/storage, use a durable queue/worker, verify RLS/private storage with two real users, then exercise cold starts, restart recovery, upload limits and concurrent jobs in the hosted environment. The current `DATABASE_URL` field is not wired to a Postgres repository; setting it alone does not migrate the app.

The Vercel connector was unavailable during this session; local browser automation was disabled. The connected Supabase connector account did not list the SightLine project, so no cloud schema or policy mutation was attempted. The owner subsequently chose to deploy later. No hosted security/header/load check, live two-account cloud isolation test or real notification delivery was performed. Notifications remain explicitly simulated unless a real provider and authorized test destination are configured. Calls and WhatsApp messages remain owner initiated. Representative positive knife/negative-scene accuracy testing remains a separate validation gap; passing functional tests does not certify detection accuracy.

Official platform references checked during this session:
- https://vercel.com/docs/services
- https://vercel.com/docs/functions/runtimes/container
- https://vercel.com/docs/functions/runtimes#file-system-support

## Offline backup and restore

Stop the API completely first. From the project root, using the installed Python environment:

```sh
qa/.venv/bin/python scripts/storage_snapshot.py backup --storage-root backend/storage --server-stopped --output backend/backups/snapshot-YYYYMMDD-HHMMSS
qa/.venv/bin/python scripts/storage_snapshot.py restore --snapshot backend/backups/snapshot-YYYYMMDD-HHMMSS --output backend/restored-storage-YYYYMMDD-HHMMSS
```

The output paths must not already exist. Verify restored data offline, then choose the restored root’s `media` directory via `MEDIA_DIR` while the server is stopped. Keep the original storage until the restored installation is verified. The tool does not change live configuration, schedule backups, delete old snapshots, restore Supabase contacts, or copy secrets. Supabase backup policy and off-device encrypted backup storage still need to be configured for the final hosting environment.
