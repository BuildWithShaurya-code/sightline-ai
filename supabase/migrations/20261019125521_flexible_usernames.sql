-- Accept human-readable names and number-leading usernames consistently.
-- Existing accounts, ownership, unique names and confirmation policy are unchanged.
BEGIN;
CREATE OR REPLACE FUNCTION sightline.account_alias_created() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  requested text;
  project text;
BEGIN
  requested := lower(btrim(NEW.raw_user_meta_data->>'username'));
  -- Preserve email-only/provider-created accounts and existing users.
  IF requested IS NULL THEN RETURN NEW; END IF;
  IF jsonb_typeof(NEW.raw_user_meta_data->'username') <> 'string'
     OR requested !~ '^[a-z0-9][a-z0-9_. -]{2,31}$'
     OR NEW.email IS NULL OR NEW.email='' THEN
    RAISE EXCEPTION 'Invalid signup details' USING ERRCODE='23514';
  END IF;
  SELECT project_url INTO project FROM sightline.account_config WHERE id=1;
  IF project IS NULL THEN RAISE EXCEPTION 'Account signup is not configured'; END IF;
  -- A conflicting username aborts the entire signup, not a half-created account.
  INSERT INTO sightline.aliases(project,user_id,username,email)
    VALUES(project,NEW.id::text,requested,NEW.email);
  RETURN NEW;
END;
$$;
COMMIT;
