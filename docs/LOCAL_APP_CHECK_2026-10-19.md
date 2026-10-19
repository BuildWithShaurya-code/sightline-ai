# Updated local app check — 19 October 2026

Open http://127.0.0.1:3000/#/detection-studio while the local server is running. If an old request failed during restart, press Retry Frame Analysis once. New users choose Create account on the login page, set a unique username and password, then complete private security contacts and location. No email or confirmation is required.

## Fixed

- Camera requests contained the API prefix twice. The API client now accepts either an origin or an API-root configuration.
- Review threat keeps its label and opens as soon as the first saved photo is available; extra automatic photos do not block review.
- Evidence storage runs away from the camera event loop. Timeouts are reported correctly.
- API outages are labelled as a connection problem, rather than a standalone demo.

## Verified

178 backend tests, 11 frontend checks, TypeScript and production build passed. The owner confirmed live detections in the web app. The actual frontend API code, real Supabase SDK, local proxy and original model detected the positive mask fixture at 89%, saved private evidence while other frame requests completed, opened review/confirmation, cleared a false alarm and rejected cross-user incident access. Account/contact/video/job checks and deployment configuration checks are recorded in VERIFICATION.md.

The model checksum matches the original trained checkpoint. Auth, private storage and PostgreSQL use the configured Supabase project. Public keys stay in the browser; server credentials stay private. Saving details makes no call or sends any message.

## Before public launch

Rehearse username registration and sign-in on the intended host. Representative model accuracy (including positive knife cases), hosted cold starts/concurrent load and actual external notification delivery remain unmeasured. Dispatch is simulated. Full browser automation was unavailable, so the browser camera result is the owner's observation. See VERIFICATION.md for exact scope.

No new deployment or GitHub upload was performed. The downloadable source excludes secrets, owner data, footage and private model weights; use the setup guide to reproduce it with authorized assets.

## Latest account update

Registration now requires only a unique username, password and password confirmation. No email field or confirmation is used. Two fresh accounts were created through the real frontend/API, immediately signed in and verified to have separate contacts and histories. Duplicate usernames and incorrect passwords were rejected. An older pending account migrated safely using its own correct password, retaining the same account ID. Latest backend suite: 183 passed; frontend: 11 checks, TypeScript and production build passed. The app is still running locally at http://127.0.0.1:3000/#/operator-login.


## Loading and dismissal update · 19 October 2026 (latest)

Scope: local React app → verified API → private Supabase database/storage → incident view and false-alarm journal. No GitHub publication or Vercel deployment was performed.

- The green hold control now responds when a reason is missing: it explains the requirement, focuses the reason field and scrolls it into view. Selecting a reason unlocks the uninterrupted three-second hold. Early release cancels; duplicate input while a save is pending cannot submit twice. The reason remains compulsory.
- Dashboard readiness, capabilities and latest-incident requests start independently. Readiness and synchronous incident routes run in the API thread pool, so cloud I/O does not block camera inference. Checking is distinct from offline; a pending history fetch no longer displays an empty-history claim.
- PostgreSQL identity/role/timeout setup is pipelined and must succeed before application SQL. Related reads share a transaction-local verified owner. History signs all visible evidence in one storage request after releasing its database transaction. Response actions read only owned incident status, rather than downloading/signing evidence metadata they do not need.
- Recent successful incident responses are held in memory for at most 30 seconds (20 entries), scoped to the current account. They are never written to browser persistence, expire before signed evidence links, and clear on account changes. Mutations invalidate the relevant entry; an earlier response cannot repopulate it after invalidation. Backend verification/RLS still governs every real action. Other-device changes may take up to 30 seconds to appear in a cached detail view.
- Contact reads/saves no longer call the remote account-verification endpoint twice per action. The local SDK session binds the form to its owner before/after the request; Supabase verifies the actual token and enforces RLS on each SELECT/UPSERT. Session restoration still verifies the provider identity.

Observed single-run timings on this laptop against the same cloud project, using generated disposable accounts (milliseconds; not a load test, percentile or guarantee):

| Operation | Before | Final |
| --- | ---: | ---: |
| Registration | 5800 | 2403 |
| Save operator-reported alert | 12517 | 4329 |
| Uncached incident detail | 5918 | 1332 |
| History with one incident | 8830 | 1638 |
| Confirm review | 7430 | 4132 |
| Save false-alarm response | 11833 | 2711 |
| Three parallel dashboard API requests, all complete | 12825 | 1931 |

A separate connected run through the actual frontend API reopened a just-saved incident in 0 ms at the timer's rounded resolution, without a network read. This excludes React rendering and is not a browser latency benchmark. Cloud mutations still await real acknowledgements; the three-second safety hold is additional to saving time.

Verification: **187 backend tests**, **12 frontend check scripts**, TypeScript and production build passed. New tests cover identity setup failure/rollback, nested reads, batched history signing, cache expiry/account switching/stale results, missing-reason feedback and continuous-hold input. Actual connected tests passed two-account username registration/password login, private contact save/reload through the updated store, separate histories, incorrect password/duplicate denial and cross-account incident denial. The original model detected the positive mask fixture at 89%; a negative scene produced no mask/knife. During evidence saving, three other frame requests completed in 23/20/20 ms on this laptop; these are not camera FPS or hosted performance figures. Signed private evidence, review and false-alarm clearing passed. All generated accounts/records/objects were removed.

Browser control was available for this run. In the owner's local web app, pressing the control with no reason focused the required select and displayed its explanation; choosing a reason enabled the green button. Navigating back left the real incident open. Full uninterrupted hold/save was exercised by the isolated input/timer harness and connected API tests, not by automatically dismissing the owner's incident. An earlier console timeout from the backend restart was historical; the updated controls and dashboard loaded afterward.

The current checkpoint still needs hosted compute for inference and private managed services for accounts/storage. The existing Vercel service/container/daemon configuration is intended to host that compute later; a static frontend upload alone cannot execute this Python model. No browser-only inference migration or new deployment was made. Cold starts, representative hosted concurrency/accuracy, positive knife evaluation and real notification delivery remain separate release gates.


## Immediate evidence navigation and History refresh · 19 October 2026 (latest follow-up)

- Confirm Threat now opens the already-persisted evidence view immediately. A scoped pending task carries the saved incident/photo while the existing review API completes. The view says Saving confirmation, retains the unreviewed state, and disables response actions until the real acknowledgement. Failures leave the photo visible with retry; account changes discard the task. No local prediction is represented as a successful saved/confirmed incident.
- History stores a maximum of 10 query/page results for 30 seconds in account-scoped memory. A return visit renders those recent records and refreshes in the background. Query/date/status/page keys are separate; mutations and account changes invalidate the cache. A refresh error is shown explicitly. Full browser reloads clear memory and still require authentication/network reads.
- Cloud History no longer calls get_incident for each record. It loads the owned incident page, all evidence, linked detections and response events in five data queries independent of page size; the three related queries are pipelined. A shared pure serializer preserves the existing detail/list contract. RLS and explicit owner predicates remain active; evidence URLs are signed in one call after releasing the database transaction.
- Slide/tap to dismiss has no dwell timer or network action before navigation. Its reset animation was shortened from 260 to 160 ms. The separate required reason and three-second hold remain unchanged.

Observed connected run: a four-incident page loaded in **1297 ms**; its cached copy reopened in **0 ms** at rounded timer resolution. The captured evidence snapshot was available in **1 ms** before awaiting the real confirmation. These are single local measurements against cloud persistence, not hosted latency guarantees. First-time reads and writes remain subject to network time.

Verification: **189 backend tests** with 51 dependency deprecation warnings passed in 11.28 seconds. **13 frontend checks**, TypeScript and production build passed. Batch-history tests cover empty, one-record and ten-record pages, fixed query count, owner/filter parameters and post-transaction signing. Connected tests exercised real provider auth, original-model mask detection at 89%, a negative scene, private signed evidence, four-record pagination/search/status/date filters, confirmation, dismissal and cross-owner denial. Generated test accounts/data/objects were removed.

Browser verification: returning Dashboard → History showed all six owner records with Refreshing your history and no blocking loader. A full page reload also restored all six records; all 11 visible evidence images loaded at their actual 1280-pixel width, with no page alerts. An isolated browser fixture deliberately stalled confirmation, then rejected it: the saved-photo view stayed visible, the failure appeared and retry was available. Retry followed by a success response marked the test incident confirmed. The cancel control opened dismissal immediately. The fixture had no real-account API access, and was removed afterward; the owner's real incidents were not modified by these checks.

Changes and downloadable source remain local. No GitHub upload or Vercel deployment was performed. This improves screen responsiveness; it does not eliminate cloud acknowledgements or the deliberate three-second safety hold.


## Production release verified — 19 October 2026

- Public app: https://sightline-ai-eight.vercel.app
- Production deployment: `dpl_HYKP2t9UsZE6t8EDUeorhP94WvNf` (READY, React/Vite frontend plus FastAPI identity/inference containers, Tokyo `hnd1`). Staged with production configuration, tested, then promoted without rebuilding. Vercel reported 6m 36s build time plus 12s post-build.
- Deployed source manifest SHA-256: `53a25ea4483fa8ee8e87605840fca8797bed6567fbc87484a2064897a6422f96`. The public package may additionally contain this release record and updated documentation; runtime source is the tested build.
- Full local backend suite: **189 passed**. Public model-free subset: **81 passed**. **14 frontend scripts**, TypeScript, Vite build and deployment preflight passed.
- Controlled browser click-to-decoded-photo: **29.4 ms** with the upload deliberately pending. A real-backend first-capture test produced the local preview in **0.7 ms**, before cloud acknowledgement. This tests the immediate preview, not instantaneous network persistence.
- Staged and public-host checks used disposable accounts. Unique username/password registration and re-login, wrong passwords, duplicate usernames, private contact/location records, separate histories, signed evidence retrieval, confirmation, false-alarm clearing and cross-owner denial passed. Anonymous and forged-token requests returned 401; legacy `/auth/login` returned 404.
- Hosted original checkpoint was actually loaded with SHA-256 `0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8`. The consented private positive mask fixture returned **89%**; the empty scene returned no mask/knife detections. One production frame request took **662 ms** end to end; evidence save took **1541 ms**. These are individual samples, not percentile or SLA claims.
- A new post-promotion daemon reported a loaded model and completed a generated blank-video job using direct private storage upload and the durable PostgreSQL queue. The job ran on that new worker, not merely a previous heartbeat. Generated test accounts and objects were cleaned afterward.
- The public login was opened in the browser, a disposable existing account signed in, and the required security-contact/location screen opened. Dummy details saved successfully and navigated to Dashboard. No real security recipient was contacted.
- Initial and post-test deployment error-log queries returned no error records within the checked windows. Health/readiness endpoints and platform logs are available; external alerting/drain-based monitoring and load testing were not verified.

### Boundaries for this release

Actual stored confirmation and response availability wait for server acknowledgement. Do not close a local-preview tab while its save is pending. Browser camera/notification permissions and audio restrictions apply. Dispatch remains simulation by default; no real emergency delivery was tested. Positive knife coverage, representative accuracy, concurrency/resource limits and a disaster-restore drill on the final host remain separate validation work. The existing baseline and AI-assisted pre-event work must be disclosed to HYPNEXIS organizers.
