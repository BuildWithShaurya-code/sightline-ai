# Migration handoff

No executable migration has been applied or represented as ready in this pack. Phase 2 must inspect the target schema, generate versioned migrations using current Supabase tooling, validate locally, and apply non-destructive changes with authorized project access.

Use SCHEMA_PLAN.md and the actual API contract. Include schema constraints/indexes, explicit grants, RLS, ownership-safe relationships, restricted PIN state and private Storage policies. Do not copy the obsolete 0001_init.sql instruction blindly. Never reset the remote project. Record applied migration identifiers and verification output.
