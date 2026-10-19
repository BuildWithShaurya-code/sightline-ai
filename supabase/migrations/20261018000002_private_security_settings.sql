-- Private owner settings. Apply in the connected Supabase project; never with client-side secret keys.
BEGIN;
CREATE TABLE public.security_settings (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  details jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT security_settings_valid CHECK ((
    jsonb_typeof(details) = 'object'
    AND details ?& ARRAY['propertyName','fullAddress','city','state','pinCode','landmark','contactName','phone','usePhoneForWhatsapp','whatsappPhone']
    AND jsonb_typeof(details->'propertyName')='string'
    AND jsonb_typeof(details->'fullAddress')='string'
    AND jsonb_typeof(details->'city')='string'
    AND jsonb_typeof(details->'state')='string'
    AND jsonb_typeof(details->'pinCode')='string'
    AND jsonb_typeof(details->'landmark')='string'
    AND jsonb_typeof(details->'contactName')='string'
    AND jsonb_typeof(details->'phone')='string'
    AND jsonb_typeof(details->'whatsappPhone')='string'
    AND length(btrim(details->>'propertyName')) BETWEEN 1 AND 100
    AND length(btrim(details->>'fullAddress')) BETWEEN 1 AND 500
    AND length(btrim(details->>'city')) BETWEEN 1 AND 100
    AND length(btrim(details->>'state')) BETWEEN 1 AND 100
    AND length(details->>'landmark') <= 200
    AND length(btrim(details->>'contactName')) BETWEEN 1 AND 100
    AND details->>'pinCode' ~ '^[1-9][0-9]{5}$'
    AND details->>'phone' ~ '^\+91[1-9][0-9]{9}$'
    AND jsonb_typeof(details->'usePhoneForWhatsapp') = 'boolean'
    AND details->>'whatsappPhone' ~ '^\+91[1-9][0-9]{9}$'
    AND ((details->>'usePhoneForWhatsapp')::boolean = false OR details->>'phone' = details->>'whatsappPhone')
  ) IS TRUE)
);
ALTER TABLE public.security_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_settings FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.security_settings FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.security_settings TO authenticated;
CREATE POLICY security_settings_read_own ON public.security_settings FOR SELECT TO authenticated USING ((select auth.uid())=user_id);
CREATE POLICY security_settings_insert_own ON public.security_settings FOR INSERT TO authenticated WITH CHECK ((select auth.uid())=user_id);
CREATE POLICY security_settings_update_own ON public.security_settings FOR UPDATE TO authenticated USING ((select auth.uid())=user_id) WITH CHECK ((select auth.uid())=user_id);
CREATE FUNCTION public.security_settings_touch_updated_at() RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN NEW.updated_at=now(); RETURN NEW; END;
$$;
CREATE TRIGGER security_settings_updated_at BEFORE UPDATE ON public.security_settings FOR EACH ROW EXECUTE FUNCTION public.security_settings_touch_updated_at();
COMMIT;
