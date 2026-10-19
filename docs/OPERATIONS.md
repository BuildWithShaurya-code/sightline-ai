# Operations

For the deployed cloud edition, follow [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md). Database backups and private object retention are separate; a database backup alone does not back up media. Keep prior Vercel deployments for code rollback and preserve compatible additive database changes. API readiness requires a loaded model, private storage, PostgreSQL and a current daemon heartbeat. Provider dispatch remains simulated unless deliberately configured.

The procedure below applies to **local mode only**; never run the SQLite snapshot utility as a cloud backup.

# Operations

Run one API process on a persistent local filesystem. Start from the project root with `./scripts/start_demo.sh`; the script builds the frontend and starts Uvicorn on `127.0.0.1:8000`. Supabase sign-in/contact saving still requires internet connectivity.

## Health and jobs

- `/api/v1/health/live`: HTTP process liveness.
- `/api/v1/health/ready`: loaded original model, writable storage, database access and live job-worker thread. Unavailable components yield 503.
- `/api/v1/model/capabilities`: actual supported model classes and compatibility.

Pending admission defaults to 16 jobs overall and 4 per owner. A full queue returns 429, not a false success. Use normal user cancellation or wait. After restart, queued jobs resume and interrupted processing jobs become failed; submit a new analysis to retry. Cancellation and deadlines are checked between frames, not halfway through a native model/decoder call.

Stop with Ctrl+C or terminate the known server process gracefully. Do not use broad process-kill patterns or remove a lock while another API process is alive. A second process on the same local store intentionally fails to start its worker.

## Private data and snapshots

The media root is `MEDIA_DIR`; its sibling `data` directory contains the main and alias SQLite databases. Keep that entire storage root together on a durable disk. Keep environment secrets separately. A backup of only `.db` while its WAL is live is not an adequate restore plan.

Stop the backend first, then use new output paths:

```sh
qa/.venv/bin/python scripts/storage_snapshot.py backup --storage-root backend/storage --server-stopped --output backend/backups/snapshot-YYYYMMDD-HHMMSS
qa/.venv/bin/python scripts/storage_snapshot.py restore --snapshot backend/backups/snapshot-YYYYMMDD-HHMMSS --output backend/restored-storage-YYYYMMDD-HHMMSS
```

The snapshot excludes environment files, weights and temporary media, verifies SQLite integrity, and records media checksums. Restore never overwrites an existing directory. It contains private footage, account data and PIN hashes: keep it private and encrypt off-device copies. Checksums detect corruption, not an attacker replacing both a file and its manifest.

Verify a restored store offline before changing `MEDIA_DIR` to its `media` child, then restart and test with the correct account. Retain the original store until recovery is accepted. The script does not schedule backups, delete snapshots, transfer data off-device or restore Supabase contact settings. Configure those separately for the actual host. Do not reset/delete owner data as a troubleshooting shortcut.

## Release and rollback

Before changing code, keep a reviewed previous release and an offline storage snapshot. Record the model hash and configuration version without logging secrets. For rollback, stop the service, restore the known-good code, verify storage compatibility, then start and check readiness. Restore data only when needed and only into a new directory. Never blindly delete databases or use a schema reset for rollback.

For demo day, rehearse the entire flow on the actual device, retain a consented screen recording, and keep private fixtures available locally. Local hosting avoids a cloud cold start but does not eliminate Supabase/network dependency. Do not promise offline authentication.
