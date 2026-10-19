# Database and bucket implementation plan — not applied SQL

Use Supabase auth.users as identity; do not create another password table. Recommended owner column is user_id (UUID). API camelCase names are serialized from SQL snake_case fields.

| Entity | Required data and constraints | Ordinary browser permissions |
|---|---|---|
| profiles | id FK auth.users, display_name, optional operator_identifier unique, UTC timestamps | Read own; change safe display fields only |
| sources | id, user_id, source_type, private bucket/key, original name, dimensions/duration/size, timestamps | Read own; controlled upload/create through authorized flow |
| analysis_jobs | owner/source, targets, model_version/settings, enum status, progress 0–100, cancellation flag, timestamps/error | Read own; creation/cancel via authorized API; no completion/result forgery |
| incidents | owner/source/job, review status, title/channel/zone, severity/reason/reviewer, original dimensions, timestamps | Read own; review through authorized API; defined delete/undo |
| evidence | owner/incident/source, type, bucket/key, media offset/dimensions, timestamps | Read own; generated evidence written by worker only |
| detections | job/source/frame, class numeric 0–2 plus canonical name, confidence 0–1, xyxy, frame index/offset/dimensions/model | Read only when owner authorized; server generated |
| incident_detection_links | validated related IDs where grouping requires it | Read through authorized parents; server generated |
| dispatches | owner/incident, provider/channel, idempotency key, status, provider ref, accepted/delivery/failure/cancellation timestamps | Read own; send/cancel through authorized API, no provider-state writes |
| audit_events | actor/action/resource/time/request_id/non-sensitive metadata | Restricted read if needed; append server only; no client edits |
| operator_security | per-user PIN hash, failed_count, locked_until, updated_at | No ordinary client access; server-only setup/verify |

Define FKs, unique keys and transactions so a user cannot attach a source/job/incident/evidence belonging to someone else. UUIDs alone do not authorize relationships. Use consistent parent ownership or composite FK constraints where needed. Prevent ownership transfer on update. Index owner+created_at, foreign keys and actual search/filter columns. Avoid indexing blindly; use bounded pagination and deterministic ordering.

All timestamps timezone-aware; confidence finite 0–1; coordinates finite/nonnegative/ordered/in bounds; dimensions positive. Numeric model IDs and names must agree. Do not write CSS classes, formatted confidence or literal Today into records. The API classId stays a string.

Dispatch simulation must use explicit status/provider and cannot be sent. The frontend/backend enum needs an additive update before that route is built. Decide soft-delete versus delayed UI deletion and retention before creating irreversible cleanup behaviour.

Private buckets: source-videos, evidence-frames, evidence-clips. Object keys: `{user_id}/{source_id}/{generated_uuid}.ext`. Policy must validate the intended relationship, not just trust a submitted owner prefix. Browser users cannot upload generated evidence or overwrite others' objects. Signed URL creation authorizes access and uses bounded expiry; save bucket/key in SQL, not URLs. Storage upsert needs only the grants intentionally allowed; prefer unique object names and no accidental overwrite.

Enable RLS on each exposed table and explicit minimum grants. Ordinary user tokens are the test context; administrative keys bypass RLS. Avoid security-definer helpers; if necessary keep scope/search_path/execute rights tight. Test with user A, user B and anonymous client before considering migration complete. Server-only PIN state and logs never expose hashes/PINs.
