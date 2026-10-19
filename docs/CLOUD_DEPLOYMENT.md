# Full Vercel deployment

SightLine has two explicit storage modes. `local` retains the original SQLite and private filesystem implementation. `supabase` uses the private PostgreSQL `sightline` schema and private object buckets. A cloud installation fails configuration validation if durable storage settings are missing; it never falls back to browser storage or SQLite in `/tmp`.

## Components

| Component | Hosting | Durable state |
| --- | --- | --- |
| React / Vite interface | Vercel frontend service | None in the bundle |
| Lightweight username/sign-in API | Vercel identity container | Private account aliases; no model loading |
| Authenticated FastAPI API | Vercel container service | Supabase PostgreSQL |
| Video analysis | Vercel analysis daemon | PostgreSQL queue and expiring worker leases |
| Source video and evidence | Private Supabase Storage buckets | `source-videos`, `evidence-frames` |
| Original checkpoint | Private Supabase Storage | `sightline-models/checkpoints/best.pt` |
| Account contacts | Existing Supabase `security_settings` table | Owner-scoped RLS |

Vercel Services, Container Runtime and Daemons are beta platform features. Daemons currently run in production only. A preview without a live worker must report degraded readiness. See [Services](https://vercel.com/docs/services), [Container Runtime](https://vercel.com/docs/functions/runtimes/container), and [Daemons](https://vercel.com/docs/daemons).

## Provisioning

1. Create a Supabase project. Apply the private security-settings migration described in `SETUP.md`, then the migration ending in `_sightline_private_cloud.sql`. Review it before applying. It creates an unexposed schema, non-login API/worker roles, owner policies and narrowly scoped internal aggregate/alias functions. It does not replace existing public tables.
2. Download the database root CA from the project's Database Settings. The included public CA was obtained from Supabase's dashboard download link. Use `sslmode=verify-full`; never disable certificate validation to fix a connection problem. Transaction pooling requires prepared statements to be disabled, as this implementation does.
3. Create **private** buckets named `source-videos`, `evidence-frames`, and `sightline-models`. Restrict MIME types and set a file-size cap. This deployment uses a **50 MiB video limit**, compatible with its configured storage cap. Do not make a bucket public to fix an access error.
4. Upload the authorized original checkpoint privately at `checkpoints/best.pt`. Its required checksum is in `MODEL_CARD.md`. Model weights and real footage are excluded from GitHub and deployment source.
5. Link the correct Vercel team and project. Set the following **Production** variables. Store the database URL, server key and session secret as Vercel **Secrets**, supplied through standard input or the dashboard. Never pass them in CLI arguments or `VITE_` variables.

| Variable | Value |
| --- | --- |
| `STORAGE_BACKEND` | `supabase` |
| `ENVIRONMENT` | `production` |
| `CLOUD_DATABASE_URL` | Your project's transaction-pooler PostgreSQL URL, password percent-encoded |
| `SUPABASE_URL` | Your project HTTPS origin |
| `SUPABASE_PUBLISHABLE_KEY` | Public project key |
| `SUPABASE_SECRET_KEY` | Server-only rotated secret key |
| `SESSION_SECRET` | Independently generated random server secret |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` |
| `DISPATCH_PROVIDER` | `simulation` unless an authorized real provider is deliberately configured |
| `CORS_ORIGINS` | `[]` for the same-origin Vercel app |
| `VITE_SUPABASE_URL` | Same project's HTTPS origin |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Same public project key |
| `VITE_CLOUD_UPLOADS` | `1` |
| `VITE_API_URL` | Leave unset; the API is served on the same origin |

The API and worker Dockerfiles set their own `CLOUD_WORKER` values. Do not set a project-wide worker-role override. Credentials are runtime environment variables; Dockerfiles do not copy `.env` files or declare secret build arguments.

6. Build a staged production deployment, inspect its logs, and verify it before promotion. The daemon rolls out when the deployment becomes production; verify its own healthy heartbeat after promotion. Keep prior deployments available for rollback.

```sh
vercel link --project YOUR_PROJECT --scope YOUR_TEAM
vercel deploy --prod --skip-domain
# Inspect the actual deployment URL and test authenticated flows.
vercel promote YOUR_STAGED_DEPLOYMENT_URL
```

## What survives a restart

The queue, ownership, aliases, PIN hashes, attempts, incidents and response events live in PostgreSQL. Every request uses transaction-local verified identity; the API role cannot read other owners' rows. The daemon claims persisted work, renews a 90-second lease, and reports a loaded-model heartbeat. Expired processing jobs become explicit failures; a late worker cannot publish them as completed. Queued jobs remain available after API or worker restarts.

Videos upload directly through a scoped, non-overwriting storage ticket. Completion re-downloads bounded bytes and validates the actual container before a source becomes ready. Playback and evidence use short-lived signed URLs after ownership checks. `/tmp` contains only disposable caches and processing files. API responses do not inline evidence as large base64 database blobs.

## Release checks

- Anonymous and forged/expired bearer requests are rejected; cross-account records stay inaccessible.
- A new owner can save, edit and reload private contacts; invalid forms retain their values.
- A synthetic video can upload, validate, queue, finish real inference and be polled after refresh.
- A private evidence object is retrievable through an authorized fresh URL, not a public bucket URL.
- Stopping a worker expires its lease and produces an honest terminal state.
- `/api/v1/health/ready` verifies storage, database, loaded model and a current daemon heartbeat.
- Saving contacts initiates no call or notification; WhatsApp remains an owner-reviewed draft.

For a demo, rehearse cold starts, browser camera/audio permission, storage quotas and CPU processing time. This is a human-review prototype, not an emergency-response service or an independently validated threat detector.

## Self-service username accounts

Users register a unique username and password, with no email field or confirmation. The backend's narrowly scoped `/auth/register` endpoint uses the server-only provider secret to create a real Supabase user with a random non-deliverable identifier and authenticates that user's password through the normal provider grant. It does not issue its own tokens or store plaintext passwords. The registration trigger atomically reserves the username against `auth.users.id`; mutable metadata is never an ownership authority.

Apply the self-service-account and later flexible-username migrations, and provision the private `sightline.account_config` project URL before registration. Names are case-insensitive and unique. The backend validates lengths, limits repeated requests, rejects duplicate names and returns no administrative response to the browser. Both regular API and lightweight identity containers need the existing server-only account configuration. The identity requirements include bcrypt for password-verified migration of old pending accounts; neural libraries remain absent.

Legacy pending email accounts migrate only when username sign-in proves their existing provider password. Their unverified email is replaced by an internal identifier before activation, avoiding any claim that a real email address was verified. Their UUID and data remain intact. Confirmed accounts remain compatible. Global Supabase email-provider settings are unchanged; the app no longer depends on SMTP. Owner-assisted recovery is required for forgotten passwords in username-only accounts.

Every explicit sign-in/registration opens private Security contacts & location. Owner policies continue to separate contacts, incidents, sources, jobs and response records. The former Sign-in & security screen remains retired. No public rollout was made for this local update.
