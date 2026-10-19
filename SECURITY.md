# Security

Do not put exploitable details, tokens, passwords, footage or private contact information in a public issue. Until the repository owner provides a dedicated security contact, use the private reporting option on the final GitHub repository if it has been enabled, or contact the owner through an established private channel. No address is invented by this file.

Supabase is the identity provider. The backend validates signed user tokens against the project’s public signing keys and requires expiry, issuer, audience and an authenticated user. Project API keys are not user sessions. The retired local login endpoint returns 404.

Keep publishable configuration in browser settings; secret/service-role keys and provider tokens belong only in protected server environments. PIN state uses salted PBKDF2 and persistent attempt limits; a new user must set their own PIN.

Local mode uses SQLite and private files. Cloud mode uses an unexposed PostgreSQL schema with transaction-local verified identity and row ownership, private Supabase objects, and an independent Vercel daemon. The API and worker roles cannot log in directly. Server credentials never enter browser configuration or Docker source. Contacts retain their separate owner-scoped Supabase table. Connected checks are recorded in `docs/VERIFICATION.md`; load and representative accuracy require further evaluation.

The current local backend refuses Vercel startup to prevent silently storing private state on an ephemeral function filesystem. See the deployment guide before hosting it.
