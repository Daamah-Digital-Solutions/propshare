
-- 1. Documents: tighten SELECT policy
DROP POLICY IF EXISTS "Users can view own documents" ON public.documents;
CREATE POLICY "Users can view authorized documents"
ON public.documents
FOR SELECT
USING (
  auth.uid() = user_id
  OR (
    property_id IS NOT NULL AND (
      EXISTS (SELECT 1 FROM public.properties p WHERE p.id = documents.property_id AND p.owner_id = auth.uid())
      OR EXISTS (
        SELECT 1 FROM public.investments i
        WHERE i.property_id = documents.property_id
          AND i.user_id = auth.uid()
          AND i.status IN ('confirmed','active','completed')
      )
    )
  )
  OR (
    investment_id IS NOT NULL AND EXISTS (
      SELECT 1 FROM public.investments i
      WHERE i.id = documents.investment_id AND i.user_id = auth.uid()
    )
  )
);

-- 2. Wallets: remove direct UPDATE access, add non-negative constraints
DROP POLICY IF EXISTS "Users can update own wallet" ON public.wallets;

ALTER TABLE public.wallets
  DROP CONSTRAINT IF EXISTS wallets_balance_non_negative,
  DROP CONSTRAINT IF EXISTS wallets_pending_non_negative,
  DROP CONSTRAINT IF EXISTS wallets_total_invested_non_negative,
  DROP CONSTRAINT IF EXISTS wallets_total_returns_non_negative;

ALTER TABLE public.wallets
  ADD CONSTRAINT wallets_balance_non_negative CHECK (balance >= 0),
  ADD CONSTRAINT wallets_pending_non_negative CHECK (pending_balance >= 0),
  ADD CONSTRAINT wallets_total_invested_non_negative CHECK (total_invested >= 0),
  ADD CONSTRAINT wallets_total_returns_non_negative CHECK (total_returns >= 0);

-- 3. has_role: restrict to self / admin only
CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role public.app_role)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NULL THEN
    RETURN FALSE;
  END IF;
  IF _user_id <> auth.uid() AND NOT EXISTS (
    SELECT 1 FROM public.user_roles WHERE user_id = auth.uid() AND role = 'admin'
  ) THEN
    RETURN FALSE;
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role
  );
END;
$$;

-- 4. Avatars public bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO UPDATE SET public = true;

DROP POLICY IF EXISTS "Avatars are publicly viewable" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload own avatar" ON storage.objects;
DROP POLICY IF EXISTS "Users can update own avatar" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete own avatar" ON storage.objects;

CREATE POLICY "Avatars are publicly viewable"
ON storage.objects FOR SELECT
USING (bucket_id = 'avatars');

CREATE POLICY "Users can upload own avatar"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'avatars'
  AND auth.uid() IS NOT NULL
  AND auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can update own avatar"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'avatars'
  AND auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete own avatar"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'avatars'
  AND auth.uid()::text = (storage.foldername(name))[1]
);

-- 5. Restrict listing of property-images bucket — drop any broad SELECT policy that
-- enables listing. Public URLs continue to serve via the public CDN endpoint.
DO $$
DECLARE pol RECORD;
BEGIN
  FOR pol IN
    SELECT policyname FROM pg_policies
    WHERE schemaname='storage' AND tablename='objects'
      AND cmd='SELECT'
      AND (qual ILIKE '%property-images%' OR policyname ILIKE '%property-images%')
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', pol.policyname);
  END LOOP;
END $$;

-- Allow viewing only when accessing a specific object (not listing). Public CDN
-- access via getPublicUrl bypasses RLS for public buckets, so display is unaffected.
CREATE POLICY "Property images viewable by owner"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'property-images'
  AND auth.uid() IS NOT NULL
  AND auth.uid()::text = (storage.foldername(name))[1]
);
