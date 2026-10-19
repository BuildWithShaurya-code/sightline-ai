> **19 October 2026 — username-only accounts:** POST `/auth/register` accepts `{username,password}` (no email), validates a unique 3–32 character case-insensitive username and a password of at least 8 characters/at most 72 UTF-8 bytes, and returns `{access_token,refresh_token}` with 201 only after provider creation and real password authentication. A duplicate name returns 409. The provider user uses a server-generated, non-deliverable identifier; the administrative key/response never reaches the browser. The private registration trigger reserves the alias atomically. `/auth/username-login` retains its real provider session contract; pending accounts from the retired email flow require matching the existing provider password before migration to an internal identifier. Owner UUID/data remain intact, and wrong passwords cannot activate an account. No confirmation or recovery email is sent. Local SQLite mode refuses self-service creation with 503; configured private cloud persistence is required. This update remains local.

> **19 October 2026 — persistent local queue:** POST `/analysis/start` returns `429 QUEUE_FULL` when the atomic global/account admission limit is reached, and `503 SERVICE_UNAVAILABLE` if the worker is unavailable. Default limits are 16 overall and 4 per owner (queued + processing). Existing idempotency keys keep their original job. Queued work resumes after restart; interrupted processing fails explicitly. Readiness now includes worker liveness. The API remains a single-node SQLite/media implementation and refuses Vercel startup until durable persistence and workers are implemented. See `VERCEL_PREPARATION_2026-10-19.md`.

> **19 October 2026 — release security fixes:** POST /auth/login always returns 404 and is absent from OpenAPI. Protected operations require signature-verified Supabase ES256/RS256 user tokens, exact issuer/audience and mandatory lifetime/UUID claims; there is no unsigned, HMAC or local-session fallback. JWKS outages fail closed. GET /dispatches/security/pin returns {configured:boolean}; POST accepts write-only {pin,currentPin?}, requiring the existing PIN for changes and optionally X-Expected-Owner for race protection. No default or legacy SHA-256 PIN is accepted. Readiness requires inference is_loaded=true. Supabase legacy API keys were disabled by the owner and a new server-only secret verified. See RELEASE_FIXES_2026-10-19.md for the verified contracts and limits. Earlier login, PIN and deployment statements below are historical.

> **19 October 2026 — mask threshold and dismiss repair:** Local mask notifications and siren require confidence >=60% (inclusive), for live/playback and completed-video paths. Prediction/evidence thresholds remain 25%. Tap or >=85% swipe opens dismissal confirmation; reason selection and three-second hold remain mandatory. The owner saved the username larpers and a fresh authenticated profile view verified it. No API payload, credential submission by the agent, or backend change. See `MASK_THRESHOLD_DISMISS_FIX_2026-10-19.md`. Earlier threshold and pending-username notes below are historical.

> **19 October 2026 — demo UI and account settings:** Dashboard always exposes Security contacts & location. False-alarm reason must be selected before the green three-second hold. Additive GET/PUT `/auth/username` verifies owner identity directly with Supabase; POST `/auth/username-login` authenticates a private server alias with Supabase and returns its session for SDK initialization. No demo fallback or password storage is added. Credential mutation awaits the owner’s manual submission. See `DEMO_UI_ACCOUNT_SETTINGS_2026-10-19.md` for contracts, storage scope, tests and browser verification limits.

> **18 October 2026 — account/session repair and autosave:** configured Supabase sign-in and token lookup no longer fall through to demo identity; startup restores verified account state and synchronizes provider auth events. Security setup automatically saves valid changed drafts with serialized, owner-bound writes and honest status; explicit Save details retains validation and return navigation. No backend payload, RLS policy, or notification behavior changed. See `ACCOUNT_UI_AUTOSAVE_2026-10-18.md` for evidence and remaining migration limits.

> 18 October 2026 private contact setup: the frontend now uses the Supabase security_settings table and authenticated-user RLS for new security/location details, with no legacy contact or browser-storage fallback. Existing response-contacts endpoints remain legacy and are no longer read/written by the UI. No backend payloads changed. See SECURITY_SETUP_2026-10-18.md for configuration limitations and migration.

> 18 October 2026 UI update: Studio warnings open an unconfirmed incident for review. Threat Detail requires explicit confirmation on the current visit before Notify opens Security Response, including an acknowledgement for previously confirmed records; historical review status is preserved. No API payload changes. See CONFIRMATION_UI_2026-10-18.md.

> 2026-10-17 confirmation gate: security-response contact/open/share/confirmation/resolution events require a confirmed incident (422 otherwise). False-alarm dismissal retains the existing API payload and now uses a separate three-second hold confirmation screen. See DISMISS_HOLD_FLOW_2026-10-17.md.

> **17 October 2026 — automatic evidence and confirmation:** uploads automatically analyze; live mask detections save up to three exact frames through authenticated multipart `POST /incidents/auto-evidence`. Popup Confirm Threat persists review then opens its incident. Security Response has generated summaries and persisted contact-checkbox state (`confirmedContacts`); repeated confirmations are deduplicated. See `AUTOMATIC_EVIDENCE_FLOW_2026-10-17.md`.

> **17 October 2026 — owner mask warnings:** live/playback model mask predictions and completed video results now trigger a local on-screen notification and siren at the displayed >=25% threshold, with episode/cooldown suppression. Desktop notification permission is optional. No automatic police/security dispatch or camera evidence capture occurs. See `MASK_ALERT_FIX_2026-10-17.md` for current browser/audio verification; login remains unchanged.

> **17 October 2026 — Security Response:** the receipt screen is replaced by owner call/share actions and an authenticated response journal. Additive contact and incident response endpoints, event validation, responseStatus, false-alarm reasons and honest link-opening semantics are documented in `SECURITY_RESPONSE_2026-10-17.md`. No automatic police/security transmission occurs in this UI.

> **17 October 2026 — operator alerts and false-alarm reset:** authenticated `POST /incidents/manual-camera` (optional `Idempotency-Key`, 201 Incident) creates an unreviewed operator-reported camera alert with empty frames/detections when no photo was explicitly captured. It stores no frame and makes no inference claim. Captured photos still use `/incidents/from-frame`. `POST /incidents/{id}/false-alarm` returns the owned incident marked dismissed with frames/detections/thumbnail cleared from operator views. An additive local database flag retains raw evidence for recovery; no files are deleted. This action does not retract external notifications or bypass dispatch PIN cancellation. UI clears the current source/capture and returns to Dashboard only after success. The false-alarm slider lives below Notify Police and Security on Threat Detail.

> **Alert/history repair, 16 October 2026:** `POST /api/v1/incidents/from-frame` accepts authenticated multipart `image` and optional comma-separated `targets`, with optional `Idempotency-Key` (128 characters maximum). The server runs the model, saves a `camera_snapshot` source, completed job, unreviewed incident, linked evidence and detections atomically, and returns the existing `Incident` shape (201). No selected detections returns 422 without a saved incident. Same-owner retries with the same key return the same incident. Owner/review/detections cannot be supplied by the client. Camera previews remain unsaved until the operator selects **SAVE CAMERA ALERT**. Video **ANALYZE VIDEO & SAVE ALERT** waits for a completed job before opening its incident.
>
> `GET /incidents` additionally accepts timezone-aware ISO `created_after` (inclusive, applied before pagination). `q` now searches source IDs and original filenames as well as title/channel/zone/incident ID. Dispatch requires confirmed review; simulation is labelled explicitly and provider acceptance does not set `deliveredAt`. The sound-test button plays a short local tone and does not save an incident or send a notification. Current persistence remains SQLite/local files, not Supabase.

> **Live frame integration, 16 October 2026:** Studio now calls the existing authenticated `/inference/image` route for sampled camera/playback frames and renders original-coordinate boxes. Frame previews are unsaved and never dispatch automatically. Full-video jobs retain class coverage in bounded evidence selection. See `LIVE_DETECTION_FIX_2026-10-16.md` for observed camera/video tests and model accuracy limits. No transport shape was removed or renamed.

> **16 October 2026 repair audit:** The runtime currently uses SQLite and local media storage. The Supabase authentication/ownership claims below are intended requirements, not verified completion: arbitrary-password login, unsigned-verification fallback, and incomplete issuer checking remain blockers. See `CAMERA_REPAIR_AND_SYSTEM_CHECK_2026-10-16.md`. Camera preview uses browser `getUserMedia` only; it has no continuous inference API. Cancellation remains a request until the returned/polled job state is terminal. No API response schema changed in this repair.

# API contract — observed baseline and planned extensions

This is the active human-readable contract. It is aligned with the copied actual TypeScript/Pydantic source, not the obsolete flattened ZIP. Machine-readable expectations: contracts/frontend_contract.json. Actual implemented routes: contracts/openapi.implemented.json. Current backend schema exports: contracts/backend_schemas.json.

## Common conventions

- Prefix `/api/v1`; JSON except multipart `video` uploads.
- `classId` is string `person | mask | knife` in frontend responses. Internal numeric IDs are 0/1/2 and require an adapter.
- `confidence` numeric 0–1. `box` is pixel `[x1,y1,x2,y2]`, not an object. Include original frame dimensions and detection-to-frame linkage before relying on overlays (additive gap below).
- Jobs use queued/processing/completed/failed/cancelled; progress is numeric percentage 0–100, currently optional.
- Incident review states: unreviewed/confirmed/dismissed.
- Current dispatch states: not_sent/pending/sent/failed/cancelled. Simulation needs an additive `simulated` state plus provider field before implementing it; do not encode it as sent.
- Timezone-aware UTC timestamps at API boundaries. Current createdAt validator only checks parsing; harden timezone requirements.
- Flat error `{error: "CODE", message: "description", details: {}}`, optionally request_id/timestamp. Do not use the old nested `{error:{...}}` shape.
- Supabase user bearer token on protected routes from Phase 2 onward. Cross-owner resources may return 404; missing/invalid credentials return 401. Validation 422, file too large 413, conflicts 409, lockout 423, unavailable dependency 503. Never log PINs/tokens.

## Actually implemented now

| Route | Result | Status |
|---|---|---|
| GET /health/live | status=live, service, version, timestamp | 200 |
| GET /health/ready | phase=4, phase_description, timestamp, component readiness (API, storage, checkpoint, inference service, database, video worker) | 200 or 503 |
| GET /model/capabilities | model_id, supported_classes, class_map, thresholds, readiness metadata | 200 |
| POST /inference/image | Authenticated single-frame YOLOv11n detection; returns original coordinates [x1, y1, x2, y2], confidence, classId, latency timings | 200 (Protected, Bearer token required) |
| POST /videos/upload | Authenticated multipart video upload; spools, decodes via OpenCV, persists source record; returns `{sourceId, videoUrl}` | 201 (Protected, Bearer token required) |
| GET /videos/{source_id}/playback | Authorized owner video playback stream | 200 (Protected, Bearer token required) |
| POST /analysis/start | Idempotent analysis job submission with targets, threshold, and sample_rate_sec; returns `{jobId}` | 202 (Protected, Bearer token required) |
| GET /analysis/jobs/{id} | Poll job lifecycle (`queued`, `processing`, `completed`, `failed`, `cancelled`), progress (0-100), incidentId | 200 (Protected, Bearer token required) |
| POST /analysis/jobs/{id}/cancel | Job cancellation request; immediately cancels queued jobs or signals worker | 200 (Protected, Bearer token required) |
| GET /incidents | Paginated, searchable incident history with review status filtering | 200 (Protected, Bearer token required) |
| GET /incidents/{id} | Full incident detail with bounded keyframe evidence and model detection coordinates | 200 (Protected, Bearer token required) |
| PATCH /incidents/{id} | Operator threat review transition (`confirmed` / `dismissed`) with badge ID and notes | 200 (Protected, Bearer token required) |
| DELETE /incidents/{id} | Soft-delete incident from operator views while preserving raw media references | 200 (Protected, Bearer token required) |

Health and capabilities routes are public. All operational and media endpoints strictly require an authenticated Supabase operator Bearer token (rejects missing/expired/wrong-project tokens and server secret keys). Model-compatibility reflects real loaded checkpoint state. Tenant isolation ensures User B cannot view, modify, or delete User A's data.

## Existing planned frontend client calls (Phase 5–6 remaining)

| Route | Request | Required response baseline | Implementation phase |
|---|---|---|---|
| POST /dispatches/send | `{incidentId}` | Dispatch record | 6 |
| POST /dispatches/{id}/cancel | `{pin}` over HTTPS | `{success: boolean, dispatch: Dispatch}` | 6; PIN primitives in 2 |
| Webcam session lifecycle | Session start/frame/stop | Real-time session monitoring | 6 |


An API key does not authenticate an operator. Reject source/incident IDs belonging to another user. Support idempotency for analysis start and dispatch send. A completed no-detection job has no incident; document null/omission consistently and adapt current client validation.

## Current shared frontend shapes

`Detection`: classId string (`person | mask | knife`); confidence numeric (0-1); box `[x1, y1, x2, y2]` in pixel coordinates. Additive metadata fields verified in Phase 5: `evidence_id?: string` (links detection to evidence keyframe), `frame_index?: number` (source video frame sequence number), and `video_offset_seconds?: number` (timestamp in seconds).

`Frame`: id, timeSeconds, imageDataUrl string. Preserve this field name for compatibility; current backend schema describes data or storage URLs. A signed URL can be presented through an explicitly documented adapter. Add imageUrl separately if choosing clearer semantics and update runtime validators together. Database stores an object key, not base64 or signed URL.

`Incident`: id, sourceId, createdAt, status (`unreviewed | confirmed | dismissed`), frames[], detections[]; optional dispatchId/title/channel/zone/durationSeconds/thumbnail. Overlays map detections to evidence keyframes via `evidence_id` and timestamp proximity, scaled dynamically to viewport accounting for letterboxing.

`Dispatch`: id, incidentId, status; optional error/createdAt/cancelledAt. Current backend also exposes channel/provider_reference/callSign/etaMinutes/failure_details, which must never be invented. A later provider adapter must not claim emergency dispatch. Add explicit provider/simulation/acceptance fields and update source validators.

## Required planned extensions

| Route or service | Contract | Phase |
|---|---|---|
| Supabase Auth SDK sign-in/sign-out/recovery | External identity/session flow; not a duplicate FastAPI password system | 2 |
| GET /auth/me | Verified user ID plus profile; no tokens/hashes | 2 |
| PATCH /auth/me | Only permitted display/profile fields; no role/owner assignment | 2 |
| POST /security/pin | Authenticated setup/change, reauthentication for change | 2 |
| POST /security/pin/verify | Action-specific primitives/testing; not a reusable cancellation authorization flag | 2 |
| POST /analysis/jobs/{id}/cancel | Cancel request and current job state; do not report final cancellation before worker acknowledgement | 4 |
| GET /incidents | q/status/page/page_size; `{items, pagination:{page,page_size,total_items,total_pages}}` per existing backend pagination schema | 4–5 |
| PATCH /incidents/{id} | Review status and optional reason; record reviewer/timestamp | 4–5 |
| DELETE /incidents/{id} | Define server soft-delete or delayed UI send; do not advertise server undo without a contract | 4–5 |
| GET /evidence/{id}/access | Authorize owner then issue short-lived URL/expiry | 2 helper, 4–5 route |
| Webcam session lifecycle | Optional phase 6 authenticated start/frame/stop; frame sequence/time required | 6 |

No business endpoint in this document is an implemented promise until its source route and tests exist. This is not a fake live OpenAPI service. Example JSON in fixtures is labelled synthetic and never used as real results.


### Local client response reuse (19 October 2026)

GET incident details can reuse a validated response for 30 seconds in account-scoped memory. No response cache is used as an authorization decision or durable store. Account changes clear it; incident review/delete/false-alarm and response-journal writes invalidate it. Successful saves/reviews populate the current owner's entry. An in-flight response predating invalidation cannot write back. Every network request retains its bearer token and the server's verified ownership/RLS checks.


### Confirmation navigation and History pages

A client may display an existing saved incident while PATCH review is pending. It must keep the persisted status, label the pending write, and wait for successful confirmation before enabling response actions. A failed write retains evidence and permits retry. History pages can render a 30-second owner/query-scoped in-memory response while fetching fresh data; background failures must be visible. Neither cache nor pending navigation changes server authorization or response schemas.
