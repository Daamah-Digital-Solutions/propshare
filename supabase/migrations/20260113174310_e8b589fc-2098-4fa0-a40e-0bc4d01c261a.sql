
-- Create family_groups table to manage family investment groups
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

-- Create family_members table for sub-accounts
CREATE TABLE public.family_members (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  family_group_id UUID NOT NULL REFERENCES public.family_groups(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  email TEXT,
  relationship TEXT NOT NULL,
  allocated_units INTEGER NOT NULL DEFAULT 0,
  allocated_returns NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  is_verified BOOLEAN NOT NULL DEFAULT false
);

-- Create family_transfers table to track internal transfers
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

-- Create family_return_allocations table
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

-- Enable RLS on all family tables
ALTER TABLE public.family_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.family_return_allocations ENABLE ROW LEVEL SECURITY;

-- RLS policies for family_groups
CREATE POLICY "Users can view own family groups"
ON public.family_groups FOR SELECT
USING (auth.uid() = owner_id);

CREATE POLICY "Users can create family groups"
ON public.family_groups FOR INSERT
WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update own family groups"
ON public.family_groups FOR UPDATE
USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete own family groups"
ON public.family_groups FOR DELETE
USING (auth.uid() = owner_id);

-- RLS policies for family_members
CREATE POLICY "Users can view family members in their groups"
ON public.family_members FOR SELECT
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can add family members to their groups"
ON public.family_members FOR INSERT
WITH CHECK (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can update family members in their groups"
ON public.family_members FOR UPDATE
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can delete family members from their groups"
ON public.family_members FOR DELETE
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

-- RLS policies for family_transfers
CREATE POLICY "Users can view transfers in their family groups"
ON public.family_transfers FOR SELECT
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can create transfers in their family groups"
ON public.family_transfers FOR INSERT
WITH CHECK (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

-- RLS policies for family_return_allocations
CREATE POLICY "Users can view allocations in their family groups"
ON public.family_return_allocations FOR SELECT
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can create allocations in their family groups"
ON public.family_return_allocations FOR INSERT
WITH CHECK (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

CREATE POLICY "Users can update allocations in their family groups"
ON public.family_return_allocations FOR UPDATE
USING (EXISTS (
  SELECT 1 FROM public.family_groups 
  WHERE id = family_group_id AND owner_id = auth.uid()
));

-- Add trigger for updated_at
CREATE TRIGGER update_family_groups_updated_at
BEFORE UPDATE ON public.family_groups
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER update_family_members_updated_at
BEFORE UPDATE ON public.family_members
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at();
