# Verification record

Observed 19 October 2026 on macOS arm64, Python 3.12 clean environment and Node 24. Original checkpoint SHA-256 ends `...539dc0f8` and matches the full value in the README.

| Run | Observed result |
| --- | --- |
| `python -m pytest backend/tests independent_release_gates.py -q` in isolated working copy | **182 passed, 49 deprecation warnings, 10.44 seconds**: 173 backend + 9 independently retained attack/readiness gates |
| Public model-free pytest subset from the README, with absent configured checkpoint | **68 passed, 8 warnings** |
| TypeScript | Pass |
| Vite build | Pass using config runner; large-bundle warning remains |
| `qa/*_checks.cjs` | All 8 passed |
| Vercel preflight fixture checks | 14 invalid/missing configuration cases rejected; valid public settings accepted |
| Real-model process restart drill | Pass: isolated processing server killed, restart failed interrupted job and completed queued blank clip with no incident; readiness HTTP 200 |
| Private storage fixtures | Backup/restore, PIN/alias preservation, checksum corruption, symlink/path rejection, no overwrite and live-worker refusal passed |

The model-free CI subset uses the real security/database code with generated signing keys and isolated provider adapters. Provider mocks and synthetic fixtures are deliberate, labelled test tools; they are not evidence of live external delivery or two real users passing cloud RLS.

The full suite uses authorized local model/positive video/image fixtures. The curated GitHub package excludes those private assets, so a fresh public clone runs the documented model-free subset until assets are provisioned. Full-suite reproduction requires the original model and the exact authorized fixtures. Source/rendering checks are not a hosted browser test.

The first Vite config-bundling attempt in the temporary checkout was denied because its `node_modules` points to a read-only dependency directory. The config-runner build passed. This filesystem workaround is not needed by an ordinary writable `npm ci` checkout.

## Not established

Representative positive knife evaluation, a false-alert benchmark and actual notification-provider delivery remain unverified. See the cloud release record below for later deployment checks. There is no justified 50-FPS, sub-second end-to-end, zero-false-positive or production-readiness claim.

Historical phase reports in the working directory are retained for traceability. They do not override this current record. Timestamped raw local logs/results were saved separately from the curated public package; do not upload private raw browser/session/data artifacts.

## Curated-source reproduction

A fresh 163-file source export, without private model/footage/real environment files, passed the public 68-test backend subset, TypeScript, Vite build, all 8 frontend scripts and the Vercel preflight fixture checks. Dependencies were reused from the verified local environments; this was not a fresh Linux dependency download or a GitHub-hosted run. Export manifest hashes and excluded sensitive-file types were checked. The configured full-app build and unconfigured public CI build have different environment-dependent bundle contents; a public CI build alone does not verify connected login.

## Cloud migration checks · 19 October 2026

The private PostgreSQL schema migration passed a rolled-back dry run before installation. Against the configured cloud database, checks confirmed own-account reads, rejected cross-account reads and forged-owner writes, rejected anonymous reads, preserved idempotency and persisted cancellation.

With generated non-personal media, direct signed upload, actual container validation, retrying completion, a durable claim, original-model video analysis, private evidence persistence, fresh signed evidence access and cross-account evidence isolation passed. The database stores object references instead of base64 evidence. Worker heartbeat, lease expiry and rejection of a late completion after failure also passed. Test records and test media were removed.

Vercel built both Python 3.12 Linux amd64 container images from the declared requirements, using official CPU PyTorch wheels. These build and integration results do not establish representative detection accuracy or emergency-response reliability.

## Self-service accounts update · 19 October 2026

- Backend suite in a fresh isolated local store: **175 passed**, including the account service's anonymous/legacy-login rejection and a subprocess assertion that it never imports the neural stack.
- TypeScript and production frontend build passed. All **9 frontend scripts** passed, including signup validation, duplicate/error/no-session behavior through an isolated provider, exact password preservation, and a deliberately stalled optional username lookup that no longer blocks sign-in.
- A rolled-back connected PostgreSQL transaction verified new-account alias ownership, atomic rejection of a duplicate signup username, no username reassignment from editable metadata, email synchronization and alias cleanup. The additive migration was then installed.
- The project's public settings confirmed email signup enabled and email confirmation required. The change preserves email confirmation and existing credentials. No public-email-delivery claim follows from a provider mock.
- The former account menu/screen was removed. Every explicit sign-in now opens security setup immediately.

## Multi-user local app checks · 19 October 2026

The updated local interface and API were checked against the configured Supabase project, using temporary generated accounts and synthetic video. Both users signed in through the actual username endpoint with separate passwords (observed 2.31 and 2.45 seconds); the wrong user's password was rejected. Each saved separate contacts. Cross-owner contact reads, incident reads/reviews/deletes, video playback and job inspection were denied. A generated operator-reported incident appeared only in its owner's history. All generated account data was cleaned up.

The connected full workflow also passed contact editing, database rejection of an invalid PIN, a scoped video upload, actual video validation, real-model cloud-worker completion and no invented incident for an empty scene. The local API's readiness returned HTTP 200. No external notification was sent.

The final backend suite passed **176 tests** with 48 deprecation warnings in 10.76 seconds. TypeScript, production build and all **9 frontend scripts** passed. Added checks cover visible signup access, account-identity changes, removed shared-cache fallback and actionable unconfirmed-email errors. Rendering/source checks do not certify live browser interactions.

The login card now exposes Sign in and Create account at its top. Successful sign-in opens security setup. Changing the verified account clears transient capture state and remounts account screens; dashboard failures never fall back to unowned browser incidents.

Public signup with reserved example/test email domains was rejected by the real provider with `email_address_invalid`, as documented by Supabase. These rejected requests are not evidence that real-inbox delivery works. Email confirmation remains enabled; real-inbox signup and confirmation-link return still require owner verification. Browser control was disabled during this run. No new deployment or GitHub publication was performed.

The actual frontend `auth.ts` implementation was also bundled with the real Supabase JavaScript SDK and exercised through Node with temporary confirmed accounts and in-memory browser-storage substitutes. Both different usernames/passwords, email sign-in, verified UUIDs, empty private histories, logout cleanup and account switching passed against the local API and real provider. This checks the actual frontend authentication data flow, not pointer/keyboard interaction or email delivery. Test accounts were removed. After the backend restart, local frontend and readiness each returned HTTP 200.

## Username-format correction · 19 October 2026

The reported “starting with a letter” message came from client validation before signup was submitted. Frontend validation, API normalization and the Supabase registration trigger now consistently accept 3–32 ASCII letters/numbers, with internal spaces, dots, underscores and hyphens; names may start with a number. Names remain case-insensitive and unique. Email addresses belong in the email field, not the username field. Existing accounts and confirmation policy were preserved.

The additive `_flexible_usernames.sql` migration passed rolled-back trigger/ownership checks before installation. The actual frontend auth implementation with the real Supabase SDK successfully signed in two disposable confirmed accounts whose names contained spaces and leading numbers, then verified email sign-in, logout and account switching. Generated accounts were removed. Confirmation delivery is still not inferred from admin-created accounts.

After the correction: **177 backend tests passed** with 49 deprecation warnings in 10.46 seconds; all **9 frontend scripts**, TypeScript and production build passed. The local backend was restarted to load the new rule. No Vercel deployment or GitHub push was performed.

## Camera and evidence repair · 19 October 2026

The owner reported `Method Not Allowed` during live-camera frame analysis. Reproduction showed POST `/api/v1/api/v1/inference/image` returned 405, while the real `/api/v1/inference/image` correctly required authentication. The locally started preview had supplied an API-root value to a client that expected an origin. The client now normalizes both forms so it appends the prefix once. Six URL configurations are covered by a new frontend transport contract.

The owner then confirmed that live detections appeared again in their own browser. Browser-control tools continued to report disabled; this is owner-observed camera evidence, not an automated browser walkthrough.

A second report showed the review action stuck behind `Saving evidence…` and a timeout labelled as caller cancellation. The action now keeps its Review threat label, enables once the first evidence photo is persisted, and does not wait for extra background photos. Failure/status text stays separate. Synchronous automatic-evidence database/storage work runs in a thread pool with the verified owner context preserved, so it cannot block the camera's event loop. The client distinguishes timeouts from explicit cancellation and enforces the same deadline while waiting for a session token; a stalled token refresh cannot send a late stale frame. Initial automatic-evidence storage has a bounded 45-second timeout; no success is displayed before persistence.

Observed final checks:

| Check | Observed result |
| --- | --- |
| Backend suite | **178 passed**, 49 deprecation warnings, 10.87 seconds |
| Frontend | TypeScript, production build and **11 scripts passed** |
| Deployment configuration fixtures | 14 unsafe/missing cases rejected; valid public settings accepted |
| Actual frontend API + real Supabase SDK + local proxy + original model | Positive mask fixture detected at **89%**; negative scene had no mask/knife prediction |
| Concurrent camera/evidence | Private photo saved while 3 camera inference calls completed in **31, 21 and 21 ms** on this local run; these are individual fixture requests, not a camera FPS or public latency benchmark |
| Evidence and review | Signed private photo retrieved; history, explicit confirmation, response state and false-alarm clearing passed |
| Ownership | A second real account could not see or open the camera incident/history |
| User's live browser | Owner reported detections appearing after Retry Frame Analysis |

Disposable test users and their generated evidence/source records were removed. No external dispatch was sent. No new GitHub publication or Vercel deployment was performed. Historical positive-person/model integrity, strict token rejection, contact validation and job/storage checks remain in the retained test suite.

Public signup confirmation-email delivery, representative positive knife accuracy, hosted cold starts/load and real notification-provider delivery remain unverified. Dispatch stays explicitly simulated. These are release limits; the observed checks do not justify a blanket production or model-accuracy claim.

The final connected video regression also passed authenticated upload tickets, private video upload and decode validation, contact save/edit, stored PIN validation, background-worker completion and cross-account video/job denial. The final startup check verifies the local UI and API readiness separately. No hosted rollout was attempted.

## Username/password-only accounts · 19 October 2026

At the owner's explicit request, the email-confirmation UI/registration flow was replaced with unique username and password accounts. The app collects no signup email and sends no confirmation or password-reset email. A narrow server provisioning operation creates a real Supabase password account with an internal, non-deliverable identifier. The database trigger owns uniqueness/UUID binding; frontend sessions still come from Supabase rather than a local token. Server keys remain private. Global provider email settings were not weakened.

The connected test used the actual frontend registration/sign-in functions with the real SDK and local API to create two new accounts through the public app endpoint, without admin pre-creation for those accounts. Both received immediate real sessions, showed their usernames, saved separate contacts and private histories, signed out and signed back in using their own passwords. Wrong passwords, cross-account contact/incident access and case-insensitive duplicate registration were rejected. A third disposable account created in the earlier pending-email state migrated only after its correct existing password was verified; its UUID stayed the same. The migration replaces its unverified email with an internal identifier rather than claiming real-email ownership. Test users/records were removed.

Final backend suite: **183 passed**, 51 deprecation warnings, 10.62 seconds. Targeted account tests: **14 passed**. TypeScript, all **11 frontend checks** and production build passed; the final frontend build was repeated after the username wording change. Existing camera/model/storage tests remain in the retained suite. No actual owner's credentials were changed by the agent.

The earlier email-verification/recovery experiment is superseded by this username-only policy. No email-delivery requirement remains for registration. Forgotten-password assistance for username-only accounts requires deliberate owner help; there is no automatic shared reset. Full automated browser interaction remains unavailable. No GitHub push or Vercel deployment was made.

## Detection warning confirmation button · 19 October 2026

The warning action now reads **CONFIRM THREAT**. Its click awaits the existing authenticated incident-confirmation operation, checks that the returned incident ID/status match, then opens Threat Detail. Repeated clicks are guarded; a failed confirmation leaves the warning open with an error. Further evidence frames do not block confirming an already saved incident. Confirmation initiates no external call/message. Rendered warning-state checks, the mask/slider regression checks, TypeScript and production build passed. This is a local UI-flow update; no deployment or publication was performed.


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
