"""0001 initial — build the baseline schema from scratch on self-hosted Postgres.

Supabase has been dropped entirely (Auth/Storage/RLS *and* its Postgres hosting);
the database now runs on the owner's VPS. This revision is the SOURCE OF TRUTH for
the schema — there is no live Supabase DB to diff against. It is translated from
the original ``supabase/migrations/*.sql`` (the 6 source migrations, collapsed in
order) and kept as the historical baseline:

  1) 20260113155950  enums, core tables, has_role(), handle_new_user(),
                     update_updated_at(), triggers, storage buckets + policies
  2) 20260113160025  update_updated_at() -> SECURITY INVOKER
  3) 20260113160512  property-images storage write policies
  4) 20260113174310  family_* tables + RLS + triggers
  5) 20260511081107  documents SELECT tighten; wallets drop client UPDATE +
                     non-negative CHECKs; has_role() self/admin; avatars bucket;
                     property-images listing restriction
  6) 20260511081145  drop avatars listing policy; REVOKE/GRANT function EXECUTE

Portability: a guarded preamble creates the legacy ``auth``/``storage`` schemas,
``auth.uid()``, ``storage.foldername()`` and the ``anon``/``authenticated``/
``service_role`` roles **only if they do not already exist**, so the original
RLS/storage DDL applies cleanly on a vanilla Postgres. These stubs are inert
(``auth.uid()`` returns NULL; the app enforces authz itself); Phase 1 (0002)
re-platforms identity off the ``auth.users`` stub onto an app-owned ``users``
table.

Run with ``alembic upgrade head`` on the (fresh) VPS/CI Postgres.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------- #
# Portability preamble — guarded stubs (safe on both vanilla PG and Supabase)
# --------------------------------------------------------------------------- #
PREAMBLE = r"""
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END $$;

-- Minimal auth.users so FKs + handle_new_user resolve on a fresh DB.
CREATE TABLE IF NOT EXISTS auth.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT,
  raw_user_meta_data JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'auth' AND p.proname = 'uid'
  ) THEN
    EXECUTE 'CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $f$ SELECT NULL::uuid $f$';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS storage.buckets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  public BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS storage.objects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket_id TEXT,
  name TEXT,
  owner UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'storage' AND p.proname = 'foldername'
  ) THEN
    EXECUTE 'CREATE FUNCTION storage.foldername(name text) RETURNS text[] LANGUAGE sql IMMUTABLE AS $f$ SELECT string_to_array($1, ''/'') $f$';
  END IF;
END $$;
"""


# --------------------------------------------------------------------------- #
# Migration 1 — enums, core tables, functions, triggers, storage
# --------------------------------------------------------------------------- #
M1 = r"""
CREATE TYPE public.app_role AS ENUM ('investor', 'owner', 'broker', 'liquidity_provider', 'admin');
CREATE TYPE public.kyc_status AS ENUM ('pending', 'submitted', 'verified', 'rejected');
CREATE TYPE public.property_status AS ENUM ('draft', 'under_review', 'active', 'funded', 'closed');
CREATE TYPE public.payment_method AS ENUM ('visa', 'mastercard', 'apple_pay', 'google_pay', 'crypto', 'pronova_token', 'nova_sukuk');
CREATE TYPE public.investment_status AS ENUM ('pending', 'confirmed', 'active', 'completed', 'cancelled');
CREATE TYPE public.transaction_type AS ENUM ('investment', 'withdrawal', 'return', 'fee', 'referral_commission');

CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT,
  full_name TEXT,
  phone TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own profile" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);

CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role app_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own roles" ON public.user_roles FOR SELECT USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role app_role)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$$;

CREATE TABLE public.kyc_verifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status kyc_status NOT NULL DEFAULT 'pending',
  id_type TEXT, id_number TEXT, id_document_url TEXT, address_document_url TEXT, selfie_url TEXT,
  submitted_at TIMESTAMPTZ, verified_at TIMESTAMPTZ, rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id)
);
ALTER TABLE public.kyc_verifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own KYC" ON public.kyc_verifications FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own KYC" ON public.kyc_verifications FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own KYC" ON public.kyc_verifications FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE public.properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  title TEXT NOT NULL, description TEXT, location TEXT NOT NULL, property_type TEXT NOT NULL,
  status property_status NOT NULL DEFAULT 'draft',
  total_value DECIMAL(15,2) NOT NULL,
  minimum_investment DECIMAL(15,2) NOT NULL DEFAULT 500,
  target_yield DECIMAL(5,2),
  funded_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
  total_units INTEGER NOT NULL DEFAULT 100,
  available_units INTEGER NOT NULL DEFAULT 100,
  unit_price DECIMAL(15,2) NOT NULL,
  spv_name TEXT, spv_registration TEXT, legal_structure TEXT, expected_completion DATE,
  images TEXT[] DEFAULT '{}',
  documents JSONB DEFAULT '[]',
  fees JSONB DEFAULT '{"platform_fee": 2.5, "management_fee": 1.0}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.properties ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can view active properties" ON public.properties FOR SELECT USING (status = 'active' OR status = 'funded');
CREATE POLICY "Owners can manage own properties" ON public.properties FOR ALL USING (auth.uid() = owner_id);

CREATE TABLE public.investments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  units INTEGER NOT NULL,
  amount DECIMAL(15,2) NOT NULL,
  status investment_status NOT NULL DEFAULT 'pending',
  payment_method payment_method, payment_reference TEXT,
  pronova_discount_applied BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.investments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own investments" ON public.investments FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create investments" ON public.investments FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own investments" ON public.investments FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE public.wallets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
  balance DECIMAL(15,2) NOT NULL DEFAULT 0,
  pending_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
  total_invested DECIMAL(15,2) NOT NULL DEFAULT 0,
  total_returns DECIMAL(15,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.wallets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own wallet" ON public.wallets FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update own wallet" ON public.wallets FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE public.transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type transaction_type NOT NULL,
  amount DECIMAL(15,2) NOT NULL,
  reference_id UUID, description TEXT, payment_method payment_method,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own transactions" ON public.transactions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create transactions" ON public.transactions FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE TABLE public.secondary_listings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  investment_id UUID NOT NULL REFERENCES public.investments(id) ON DELETE CASCADE,
  units_for_sale INTEGER NOT NULL,
  price_per_unit DECIMAL(15,2) NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sold_at TIMESTAMPTZ
);
ALTER TABLE public.secondary_listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can view active listings" ON public.secondary_listings FOR SELECT USING (status = 'active');
CREATE POLICY "Sellers can manage own listings" ON public.secondary_listings FOR ALL USING (auth.uid() = seller_id);

CREATE TABLE public.notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, message TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'info',
  read BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own notifications" ON public.notifications FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update own notifications" ON public.notifications FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE public.documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  property_id UUID REFERENCES public.properties(id) ON DELETE CASCADE,
  investment_id UUID REFERENCES public.investments(id) ON DELETE CASCADE,
  title TEXT NOT NULL, type TEXT NOT NULL, file_url TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own documents" ON public.documents FOR SELECT USING (auth.uid() = user_id OR property_id IS NOT NULL);
CREATE POLICY "Users can create own documents" ON public.documents FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data ->> 'full_name');
  INSERT INTO public.wallets (user_id) VALUES (NEW.id);
  INSERT INTO public.kyc_verifications (user_id) VALUES (NEW.id);
  RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON public.properties FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER update_investments_updated_at BEFORE UPDATE ON public.investments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER update_wallets_updated_at BEFORE UPDATE ON public.wallets FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER update_kyc_updated_at BEFORE UPDATE ON public.kyc_verifications FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

INSERT INTO storage.buckets (id, name, public) VALUES ('documents', 'documents', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO storage.buckets (id, name, public) VALUES ('kyc-documents', 'kyc-documents', false) ON CONFLICT (id) DO NOTHING;
INSERT INTO storage.buckets (id, name, public) VALUES ('property-images', 'property-images', true) ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Users can upload own documents" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can view own documents" ON storage.objects FOR SELECT USING (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can upload own KYC docs" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'kyc-documents' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can view own KYC docs" ON storage.objects FOR SELECT USING (bucket_id = 'kyc-documents' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Anyone can view property images" ON storage.objects FOR SELECT USING (bucket_id = 'property-images');
CREATE POLICY "Owners can upload property images" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'property-images' AND auth.uid() IS NOT NULL);
"""

# Migration 2 — update_updated_at SECURITY INVOKER + search_path
M2 = r"""
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
"""

# Migration 3 — property-images write policies
M3 = r"""
CREATE POLICY "Authenticated users can upload property images" ON storage.objects FOR INSERT TO authenticated WITH CHECK (bucket_id = 'property-images');
CREATE POLICY "Authenticated users can update their property images" ON storage.objects FOR UPDATE TO authenticated USING (bucket_id = 'property-images' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Authenticated users can delete their property images" ON storage.objects FOR DELETE TO authenticated USING (bucket_id = 'property-images' AND auth.uid()::text = (storage.foldername(name))[1]);
"""

# Migration 4 — family_* tables + RLS + triggers
M4 = r"""
CREATE TABLE public.family_groups (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id UUID NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  total_invested NUMERIC NOT NULL DEFAULT 0,
  total_returns NUMERIC NOT NULL DEFAULT 0,
  pronova_bonus_rate NUMERIC NOT NULL DEFAULT 2.5
);
CREATE TABLE public.family_members (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  family_group_id UUID NOT NULL REFERENCES public.family_groups(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  name TEXT NOT NULL, email TEXT, relationship TEXT NOT NULL,
  allocated_units INTEGER NOT NULL DEFAULT 0,
  allocated_returns NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  is_verified BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE public.family_transfers (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  family_group_id UUID NOT NULL REFERENCES public.family_groups(id) ON DELETE CASCADE,
  from_member_id UUID REFERENCES public.family_members(id) ON DELETE SET NULL,
  to_member_id UUID NOT NULL REFERENCES public.family_members(id) ON DELETE CASCADE,
  investment_id UUID REFERENCES public.investments(id) ON DELETE SET NULL,
  units INTEGER NOT NULL,
  transfer_fee NUMERIC NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'completed',
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TABLE public.family_return_allocations (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  family_group_id UUID NOT NULL REFERENCES public.family_groups(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES public.family_members(id) ON DELETE CASCADE,
  amount NUMERIC NOT NULL,
  source_investment_id UUID REFERENCES public.investments(id) ON DELETE SET NULL,
  reinvested BOOLEAN NOT NULL DEFAULT false,
  reinvest_discount NUMERIC DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
ALTER TABLE public.family_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_return_allocations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own family groups" ON public.family_groups FOR SELECT USING (auth.uid() = owner_id);
CREATE POLICY "Users can create family groups" ON public.family_groups FOR INSERT WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Users can update own family groups" ON public.family_groups FOR UPDATE USING (auth.uid() = owner_id);
CREATE POLICY "Users can delete own family groups" ON public.family_groups FOR DELETE USING (auth.uid() = owner_id);

CREATE POLICY "Users can view family members in their groups" ON public.family_members FOR SELECT USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can add family members to their groups" ON public.family_members FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can update family members in their groups" ON public.family_members FOR UPDATE USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can delete family members from their groups" ON public.family_members FOR DELETE USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));

CREATE POLICY "Users can view transfers in their family groups" ON public.family_transfers FOR SELECT USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can create transfers in their family groups" ON public.family_transfers FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));

CREATE POLICY "Users can view allocations in their family groups" ON public.family_return_allocations FOR SELECT USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can create allocations in their family groups" ON public.family_return_allocations FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));
CREATE POLICY "Users can update allocations in their family groups" ON public.family_return_allocations FOR UPDATE USING (EXISTS (SELECT 1 FROM public.family_groups WHERE id = family_group_id AND owner_id = auth.uid()));

CREATE TRIGGER update_family_groups_updated_at BEFORE UPDATE ON public.family_groups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER update_family_members_updated_at BEFORE UPDATE ON public.family_members FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
"""

# Migration 5 — documents tighten, wallets, has_role, avatars, property-images listing
M5 = r"""
DROP POLICY IF EXISTS "Users can view own documents" ON public.documents;
CREATE POLICY "Users can view authorized documents" ON public.documents FOR SELECT USING (
  auth.uid() = user_id
  OR (property_id IS NOT NULL AND (
        EXISTS (SELECT 1 FROM public.properties p WHERE p.id = documents.property_id AND p.owner_id = auth.uid())
        OR EXISTS (SELECT 1 FROM public.investments i WHERE i.property_id = documents.property_id AND i.user_id = auth.uid() AND i.status IN ('confirmed','active','completed'))
     ))
  OR (investment_id IS NOT NULL AND EXISTS (SELECT 1 FROM public.investments i WHERE i.id = documents.investment_id AND i.user_id = auth.uid()))
);

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

CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role public.app_role)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF auth.uid() IS NULL THEN RETURN FALSE; END IF;
  IF _user_id <> auth.uid() AND NOT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = auth.uid() AND role = 'admin') THEN
    RETURN FALSE;
  END IF;
  RETURN EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role);
END;
$$;

INSERT INTO storage.buckets (id, name, public) VALUES ('avatars', 'avatars', true) ON CONFLICT (id) DO UPDATE SET public = true;
DROP POLICY IF EXISTS "Avatars are publicly viewable" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload own avatar" ON storage.objects;
DROP POLICY IF EXISTS "Users can update own avatar" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete own avatar" ON storage.objects;
CREATE POLICY "Avatars are publicly viewable" ON storage.objects FOR SELECT USING (bucket_id = 'avatars');
CREATE POLICY "Users can upload own avatar" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'avatars' AND auth.uid() IS NOT NULL AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can update own avatar" ON storage.objects FOR UPDATE USING (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can delete own avatar" ON storage.objects FOR DELETE USING (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);

DO $$
DECLARE pol RECORD;
BEGIN
  FOR pol IN
    SELECT policyname FROM pg_policies
    WHERE schemaname='storage' AND tablename='objects' AND cmd='SELECT'
      AND (qual ILIKE '%property-images%' OR policyname ILIKE '%property-images%')
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', pol.policyname);
  END LOOP;
END $$;
CREATE POLICY "Property images viewable by owner" ON storage.objects FOR SELECT USING (bucket_id = 'property-images' AND auth.uid() IS NOT NULL AND auth.uid()::text = (storage.foldername(name))[1]);
"""

# Migration 6 — drop avatars listing policy; revoke/grant function EXECUTE
M6 = r"""
DROP POLICY IF EXISTS "Avatars are publicly viewable" ON storage.objects;
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.update_updated_at() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;
"""


def upgrade() -> None:
    for block in (PREAMBLE, M1, M2, M3, M4, M5, M6):
        op.execute(block)


def downgrade() -> None:
    # Drops the public objects this revision created (leaves the auth/storage
    # portability stubs in place — Phase 1 manages identity re-platforming).
    op.execute(r"""
        DROP TABLE IF EXISTS public.family_return_allocations CASCADE;
        DROP TABLE IF EXISTS public.family_transfers CASCADE;
        DROP TABLE IF EXISTS public.family_members CASCADE;
        DROP TABLE IF EXISTS public.family_groups CASCADE;
        DROP TABLE IF EXISTS public.documents CASCADE;
        DROP TABLE IF EXISTS public.notifications CASCADE;
        DROP TABLE IF EXISTS public.secondary_listings CASCADE;
        DROP TABLE IF EXISTS public.transactions CASCADE;
        DROP TABLE IF EXISTS public.wallets CASCADE;
        DROP TABLE IF EXISTS public.investments CASCADE;
        DROP TABLE IF EXISTS public.properties CASCADE;
        DROP TABLE IF EXISTS public.kyc_verifications CASCADE;
        DROP TABLE IF EXISTS public.user_roles CASCADE;
        DROP TABLE IF EXISTS public.profiles CASCADE;
        DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
        DROP FUNCTION IF EXISTS public.update_updated_at() CASCADE;
        DROP FUNCTION IF EXISTS public.has_role(uuid, public.app_role) CASCADE;
        DROP TYPE IF EXISTS public.transaction_type;
        DROP TYPE IF EXISTS public.investment_status;
        DROP TYPE IF EXISTS public.payment_method;
        DROP TYPE IF EXISTS public.property_status;
        DROP TYPE IF EXISTS public.kyc_status;
        DROP TYPE IF EXISTS public.app_role;
        """)
