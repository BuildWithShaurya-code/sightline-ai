-- Reserve a signup username in the same transaction as the provider account.
-- Metadata supplies only the requested label; ownership is always auth.users.id.
-- Before enabling signup, the operator must set the private singleton config to
-- this project's HTTPS URL; the deployment installer supplies it as a parameter.
BEGIN;
CREATE TABLE sightline.account_config (
  id integer PRIMARY KEY CHECK(id=1),
  project_url text NOT NULL CHECK(project_url ~ '^https://[a-z0-9]+\.supabase\.co$')
);
ALTER TABLE sightline.account_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE sightline.account_config FORCE ROW LEVEL SECURITY;
REVOKE ALL ON sightline.account_config FROM PUBLIC, anon, authenticated, sightline_api, sightline_worker;

CREATE FUNCTION sightline.account_alias_created() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  requested text;
  project text;
BEGIN
  requested := lower(btrim(NEW.raw_user_meta_data->>'username'));
  -- Preserve email-only/provider-created accounts and existing users.
  IF requested IS NULL THEN RETURN NEW; END IF;
  IF jsonb_typeof(NEW.raw_user_meta_data->'username') <> 'string'
     OR requested !~ '^[a-z][a-z0-9_.-]{2,31}$'
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
CREATE FUNCTION sightline.account_alias_email_updated() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF NEW.email IS DISTINCT FROM OLD.email AND NEW.email IS NOT NULL THEN
    UPDATE sightline.aliases SET email=NEW.email WHERE user_id=NEW.id::text;
  END IF;
  RETURN NEW;
END;
$$;
CREATE FUNCTION sightline.account_alias_deleted() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  DELETE FROM sightline.aliases WHERE user_id=OLD.id::text;
  RETURN OLD;
END;
$$;
REVOKE ALL ON FUNCTION sightline.account_alias_created(), sightline.account_alias_email_updated(), sightline.account_alias_deleted() FROM PUBLIC, anon, authenticated, sightline_api, sightline_worker;
CREATE TRIGGER sightline_account_created AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION sightline.account_alias_created();
CREATE TRIGGER sightline_account_email_updated AFTER UPDATE OF email ON auth.users
  FOR EACH ROW EXECUTE FUNCTION sightline.account_alias_email_updated();
CREATE TRIGGER sightline_account_deleted AFTER DELETE ON auth.users
  FOR EACH ROW EXECUTE FUNCTION sightline.account_alias_deleted();
COMMIT;
