# Phase 10 — Family Groups, Transfers, Allocations & Gifting

**Size:** Medium (≈1.5–2 weeks). The tables already exist ([audit/01-schema.md](../audit/01-schema.md)); the business logic does not.

## Goal
Make family/beneficiary investing real: groups, members (sub-accounts), unit transfers between members, return allocations, reinvest-with-discount, and scheduled gifting. Replaces the entirely in-memory mock ([FamilyInvestment.tsx](../src/components/dashboard/FamilyInvestment.tsx), [FamilyBeneficiaryGifting.tsx](../src/components/dashboard/FamilyBeneficiaryGifting.tsx)) where transfers don't move balances and "scheduled gifts" never execute.

## Testable outcome ("done when…")
- Creating a group, adding members, and transferring units between members **actually moves `allocated_units`** and records a `family_transfers` row (with `transfer_fee`).
- A return allocation persists to `family_return_allocations` and credits the member; **reinvest** creates a real investment with the `reinvest_discount` + Pronova bonus applied.
- A scheduled gift persists and **executes on its date** via a job (not a fake toast).

## Dependencies
Phase 5 (units/ownership + investment creation for reinvest), Phase 6 (returns to allocate). Pronova bonus depends on **D5**.

## Backend work
- **`family_service`** implementing transfer/allocation/reinvest with correct balance movements (these are the [BACKEND_SPEC.md](../BACKEND_SPEC.md) §6.7 flows).
- Endpoints:
  - `GET/POST /family/groups`, `POST /family/groups/{id}/members`, `PATCH/DELETE /family/groups/{id}/members/{mid}`.
  - `POST /family/groups/{id}/transfers` — move units between members (validate source holds them; apply `transfer_fee`; update `allocated_units`; record `family_transfers`; update group totals). Replaces fake [FamilyInvestment.tsx:119](../src/components/dashboard/FamilyInvestment.tsx:119).
  - `POST /family/groups/{id}/allocations` — allocate/reinvest returns (apply `reinvest_discount` + `pronova_bonus_rate`; if reinvested, create a real investment). Replaces fake [FamilyInvestment.tsx:149](../src/components/dashboard/FamilyInvestment.tsx:149).
  - Gifting: `POST /family/gifts` + `GET /family/gifts` + scheduled execution job. Replaces fake [FamilyBeneficiaryGifting.tsx:299](../src/components/dashboard/FamilyBeneficiaryGifting.tsx:299).
- Member invitation email (real, via Phase 12 comms) — replaces the "invitation email has been sent" claim ([FamilyInvestment.tsx:89](../src/components/dashboard/FamilyInvestment.tsx:89)) that sends nothing.

## DB tables/columns touched / new migrations
- `family_groups`, `family_members`, `family_transfers`, `family_return_allocations` (all exist — wire logic). New `family_gifts` table for scheduled gifts. `investments` (reinvest creates one). `ownership_ledger` (unit moves).

## Frontend wiring
- [FamilyInvestment.tsx](../src/components/dashboard/FamilyInvestment.tsx): wire Add Member / Transfer / Allocate / Reinvest to real endpoints; retire mock arrays ([:53-63](../src/components/dashboard/FamilyInvestment.tsx:53)).
- [FamilyBeneficiaryGifting.tsx](../src/components/dashboard/FamilyBeneficiaryGifting.tsx): wire Save Beneficiary / Schedule Gift to real persistence; remove false "encrypted/reviewed by legal partners/auto-executed" claims unless actually implemented; wire dead "Edit"/"Manage Reminders" or disable.
- Reinvest context flow ([ReinvestContext.tsx](../src/contexts/ReinvestContext.tsx)) re-points to real allocation/reinvest; resolve the discount-sign inconsistency flagged in [audit/03-buttons.md](../audit/03-buttons.md) ([ReinvestContext.tsx:42 vs 87](../src/contexts/ReinvestContext.tsx:42)).

## External integrations
- Email (Phase 12) for member invitations and gift notifications.

## Test plan
- **Success:** transfer moves units between members and reconciles; allocation credits a member; reinvest creates an investment with discount/bonus correct; scheduled gift executes on date.
- **Failure/authz:** only the group owner can manage it; transfer of more units than held rejected; allocation beyond available returns rejected.
- **Reconciliation:** family unit movements preserve total units; reinvested investments appear in `ownership_ledger`.

## Risks / watch-outs
- **Pronova bonus (D5)** must be specified or reinvest math is guesswork — don't fake it.
- **Legal/estate claims** in the gifting UI must be removed or actually backed (compliance) — no "legally binding/auto-executed" copy without the mechanism.
