# Phase 3 — Property Catalog & Live Marketplace

**Size:** Medium-Large (≈2–2.5 weeks). Larger than [BACKEND_SPEC.md](../BACKEND_SPEC.md) implies because the mock surface is spread across ~20 files, not one `sampleProperties.ts` (see [00-overview.md](00-overview.md) divergence #2), and the 7 ownership models carry model-specific fields the DB doesn't yet hold.

## Goal
Make every property screen read **live DB data**, give owners a working create→submit flow, give admins an approve→go-live flow, and **retire all hardcoded property arrays**. This fixes the audit's single most important disconnect: created properties are real but invisible because the marketplace is mock and drafts have no promotion path ([audit/04-role-flows.md](../audit/04-role-flows.md)).

## Testable outcome ("done when…")
- An owner creates a property → submits it → an admin approves it → it appears in the Marketplace list **and** on its detail page, sourced from the DB.
- The Marketplace's hardcoded `allProperties` array and `sampleProperties` import are **removed**; the page renders `/properties` results.
- PropertyDetails renders the real record for `:id` (no more "every id shows the same object").
- The Developer dashboard "Projects" tab shows the **owner's real properties**; the Owner dashboard's listing path works (no dead form).

## Dependencies
Phase 1 (auth/roles/owner gating). (KYC not required to *browse*; only to invest.)

## Backend work
- Endpoints:
  - `GET /properties` — **Public.** Lists `status IN ('active','funded')`. Filters mirroring the current UI: `model`, `property_type`, `country`, `city`, `status`, `min_yield`, `price` range, `sort`, pagination. Replaces mock ([Marketplace.tsx:368-427](../src/pages/Marketplace.tsx:368) filtering logic moves server-side or stays client-side over real data).
  - `GET /properties/{id}` — **Public.** Full detail incl. milestones, scenarios, exit mechanisms, risks, model-specific terms, public documents.
  - `POST /properties` — **Role:owner.** Create (status `draft`). Replaces [PropertyCreationForm.tsx:167](../src/components/developer/PropertyCreationForm.tsx:167) direct insert.
  - `PATCH /properties/{id}` — **Owner**, only while `draft`/`under_review`.
  - `POST /properties/{id}/submit` — **Owner** → `under_review`.
  - `POST /properties/{id}/images` — **Owner** → app storage.
  - `GET /owner/properties` — **Role:owner**, all statuses + funding stats.
  - `POST /admin/properties/{id}/approve` → `active`; `/reject` → `draft`+reason; `/close` → `closed`. Audit-logged.
- **Schema extension for the 7 ownership models:** add `model` (enum/text) + JSONB `option_terms`/`future_terms`/`installment_terms` + `expected_yield`, `capital_appreciation`, `total_return`, `investors_count`; and `property_milestones` (child table or JSONB). Field reference is the frontend `SampleProperty` type in [sampleProperties.ts](../src/data/sampleProperties.ts) (mirror it 1:1).
- **Data seeding:** migrate the demo content currently in mock files into real `properties` rows (status `active`) so the marketplace isn't empty at launch and existing detail pages keep working.

## DB tables/columns touched / new migrations
- `properties`: add model + term columns + metrics columns (migration).
- New `property_milestones` (or JSONB column).
- `documents`: read public subset per property.
- Reads/writes governed by owner/admin checks (replacing RLS `auth.uid()=owner_id`).

## Frontend wiring (retire mock — the big sweep)
- [Marketplace.tsx](../src/pages/Marketplace.tsx): delete inline `allProperties` ([:44-297](../src/pages/Marketplace.tsx:44)) and the `sampleProperties` import ([:8](../src/pages/Marketplace.tsx:8)); fetch `/properties` via TanStack Query.
- [PropertyDetails.tsx](../src/pages/PropertyDetails.tsx): delete the two hardcoded objects ([:38-188](../src/pages/PropertyDetails.tsx:38)); fetch `/properties/{id}`.
- [SamplePropertyDetails.tsx](../src/pages/SamplePropertyDetails.tsx), [AdvancedPropertyPage.tsx](../src/pages/AdvancedPropertyPage.tsx), [ConstructionModelPage.tsx](../src/pages/ConstructionModelPage.tsx): point at real model-filtered data (these render the 7 models).
- Home [FeaturedProperties.tsx:20](../src/components/home/FeaturedProperties.tsx:20) and home [SecondaryMarket.tsx:21](../src/components/home/SecondaryMarket.tsx:21): fetch a "featured" slice from `/properties`.
- [DeveloperDashboard.tsx:63](../src/pages/DeveloperDashboard.tsx:63) "Projects": fetch `/owner/properties`.
- **Reconcile owner vs developer listing UX** (divergence #4; **D6 resolved: `developer` = alias of `owner`**): the Owner dashboard's dead "List Property" form ([OwnerDashboard.tsx:704-769](../src/pages/OwnerDashboard.tsx:704)) and the working Developer-dashboard `PropertyCreationForm` ([PropertyCreationForm.tsx:167](../src/components/developer/PropertyCreationForm.tsx:167)) both point at the **same** `POST /properties` endpoint (one role, two presentation surfaces). No `developer` enum value is added; both surfaces require the `owner` role.
- Wire the previously-dead "Submit for Review"/"Save as Draft"/"View Details" owner buttons.

## External integrations
- App storage for property images (continues from Phase 1's storage seam).

## Test plan
- **Success:** create→submit→approve makes a property visible publicly; filters/sort/pagination return correct subsets; detail page shows the right record and model-specific terms.
- **Failure / authz:** non-owner cannot create/edit; owner cannot edit once `active`; public `GET /properties` never returns `draft`/`under_review` (replicating the old RLS rule); approving requires admin.
- **Mock retirement:** grep confirms `sampleProperties`/`allProperties` no longer feed any rendered screen.

## Risks / watch-outs
- **Model fidelity:** the 7 models have distinct fields; under-modeling here forces rework in Phase 5 (installment/option/future investing differs). Mirror `SampleProperty` carefully.
- **Empty-marketplace risk:** seed real rows or the live site looks broken at cutover.
- **Owner/developer (D6 — resolved):** one `owner` role, two UI surfaces sharing one endpoint; no enum change.
