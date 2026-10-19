# Setup

## Local requirements

Use Node 24 and Python 3.12. The full local environment was verified on macOS arm64; a Linux hosted image is still a release check. The original YOLO checkpoint and consented positive video/image fixtures are private and are not included in the GitHub review package.

From the project root:

```sh
npm ci
python3.12 -m venv qa/.venv
qa/.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env.local
cp backend/.env.example backend/.env
```

Both destination files are gitignored. Fill values in an editor; do not paste credentials into chat, command-line arguments or GitHub issues.

## Configuration

| Setting | Where | Value and purpose |
| --- | --- | --- |
| `VITE_SUPABASE_URL` | `.env.local` / Vercel | Your intended Supabase HTTPS project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | `.env.local` / Vercel | Public publishable key; never a privileged key |
| `VITE_API_URL` | `.env.local` / Vercel | Blank for local same-origin; public backend HTTPS origin for a split deployment |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | `backend/.env` | Same project; used for verified account operations and token verification |
| `SUPABASE_SECRET_KEY` | Protected server environment only | Required server-only account provisioning; never needed in the browser or public CI |
| `MEDIA_DIR` | `backend/.env` | Local private media directory; its sibling `data` contains SQLite databases |
| `MODEL_PATH` | `backend/.env` | Original private checkpoint path |
| `DISPATCH_PROVIDER` | `backend/.env` | `simulation` until a real provider and test destination are explicitly configured |
| `SESSION_SECRET` | `backend/.env` | Replace the example before `ENVIRONMENT=production`; not the Supabase signing secret |
| `CORS_ORIGINS` | `backend/.env` | Exact allowed frontend origins; avoid wildcards |

Paths in `backend/.env` are interpreted from the backend working directory. The startup script uses that directory. Leave `MEDIA_DIR=./storage/media`; use `MODEL_PATH=./models/best.pt` there. Do not point it to a model from a different project.

## Supabase

Create/use your own project. The current account flow asks users for a unique username and password only. Configure the private cloud schema and server secret before using Create account. Configure the frontend and backend to that same project. The new security-contact form uses `public.security_settings` with owner-scoped RLS. Review and apply `supabase/migrations/20261018000002_private_security_settings.sql` in your own project after checking existing schema/migration history. Do not blindly replay the older broad phase-two schema migration into an existing database.

Local mode uses SQLite; setting the older `DATABASE_URL` alone does not change that. For durable cloud mode, follow `CLOUD_DEPLOYMENT.md` and explicitly set `STORAGE_BACKEND=supabase` with `CLOUD_DATABASE_URL` and private Storage configuration. Aliases must be saved by their verified owner or migrated only after verifying that same account; no password is copied.

Add the exact local/hosted site origins to Supabase’s redirect settings. Verify user A save/edit/reload and user B isolation, denied anonymous access, and denied attempts to reassign ownership before declaring the hosted setup ready. Auth/contact saving need internet access.

## Model and startup

Place the authorized original checkpoint at `backend/models/best.pt`. Verify SHA-256 against the README and preserve the bytes. The weights and training materials are not available through a public download in this package.

```sh
./scripts/start_demo.sh
```

Open `http://127.0.0.1:8000`, create/sign in with your username account, complete contacts/location, and choose your own security PIN under Security contacts & location when needed. Run one API process; the local worker lock intentionally rejects a second process sharing its store. A missing/unloaded model leaves readiness unavailable.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named cv2` | Reinstall `backend/requirements.txt` in the Python environment used to start the API |
| Sign-in/storage unavailable | Confirm project URL, public key, real account session and security-settings migration; never replace account persistence with browser storage |
| `QUEUE_FULL` | Wait or cancel one of your pending jobs; defaults are 16 overall and 4 per owner |
| Worker lock error | Stop the other API process gracefully; do not delete a live lock to run multiple workers |
| `PIN_SETUP_REQUIRED` | Set your own PIN under Security contacts & location; there is no seeded PIN |
| Vercel preflight fails | Configure a real durable HTTPS backend and public Supabase settings first |

See [operations](OPERATIONS.md) before any restore. Use separate disposable stores for tests. Never run cleanup against owner data just to obtain a green test result.

### Username-only account setup

The Create account API requires `STORAGE_BACKEND=supabase`, `CLOUD_DATABASE_URL` with verified TLS, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and server-only `SUPABASE_SECRET_KEY`, plus the private cloud/self-service/flexible-username migrations. These migrations reserve unique aliases atomically. Local SQLite mode can still authenticate provisioned accounts but refuses self-service creation rather than losing account aliases on an ephemeral filesystem. The running local app uses configured Supabase persistence.

No SMTP configuration or confirmation link is needed for current app registration. Supabase's normal email-provider policy is not globally weakened. The server creates a real provider user with a random, non-deliverable internal identifier and returns a real password-authenticated session. The trusted provider UUID owns all data. The browser never receives an administrative key. Passwords are never stored in the application database.

Earlier pending email accounts can migrate on username sign-in only after their existing provider password hash matches. Their unverified email is replaced by an internal identifier; the UUID, private username, saved contacts and history stay unchanged. Existing confirmed accounts are not migrated. With no recovery email, forgotten-password recovery requires deliberate owner assistance; no shared password or automatic reset is supplied.
