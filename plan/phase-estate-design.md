# Group 4 — Estate / Inheritance / Beneficiaries / Gifting — DESIGN ONLY

**Status: DESIGN + legal-questions checklist. NOTHING BUILT.** This is the last and most
legally fraught group. Per the governing direction it is gated on a **dedicated legal-design
step with a real lawyer BEFORE any code**. This document is that step's engineering input:
current-state truth, the hard problems, a proposed (provisional) architecture, and the
legal-questions checklist that must be answered before implementation.

---

## 1. Current state (read-only inventory — what exists today)

| Surface | File:line | What it is |
|---|---|---|
| Beneficiary/heir manager | `src/components/dashboard/FamilyBeneficiaryGifting.tsx` | **100% client-side mock** — `initialBeneficiaries` (Fatima/Omar/Karim Lawyers), local `useState`, no API. |
| Gifting scheduler | same file (§ Gifting) | Mock `initialGifts`, local state; toast claims "the transfer will execute automatically on the chosen date". |
| Estate/Gifting tabs | `src/components/dashboard/FamilyInvestment.tsx` | Honest-disabled wrapper around the above (cleanup pass); component kept (DELETE NOTHING). |

**False/again-dangerous claims in the mock that MUST be removed or made real:**
- "Information is encrypted and **reviewed by our legal partners**" (dialog desc, ~L356).
- "All beneficiary changes are encrypted, logged, and **reviewed by our legal partners before
  becoming legally binding**" (~L473).
- "**Legally acknowledged**" status badge (~L557).
- Transfer triggers "**On verified death**" / "**After 12 months inactivity**" imply a
  verification engine that does not exist.
- Coverage/gift scopes include **`passive_income`** — but **PASSIVE is hard-locked**
  (`lp_passive_enabled=false`); estate must not imply a live passive product.
- Gifting implies **real automated transfer** of "property shares / tokenized ownership /
  passive income / wallet" — i.e. moving securities-like assets between people.

**Recommended INTERIM (pending the legal gate — not built in this group):** the estate/gifting
UI stays **honest-disabled with corrected copy** (no "legally acknowledged / reviewed by legal
partners / on verified death" claims; no fabricated beneficiaries). This is the one place where
honest-disable is the correct *interim* end-state, because the feature **cannot** be built
correctly without counsel — building it "real" without legal sign-off would itself be the
unsafe outcome. Flag for owner: apply this copy correction now, or leave as-is until build.

---

## 2. Why this needs a lawyer BEFORE code (the hard problems)

1. **Forced heirship / Sharia inheritance vs free % allocation.** The mock lets a user freely
   allocate 0–100% to anyone. In many target jurisdictions (UAE, GCC, much of the EU)
   **forced-heirship / Islamic inheritance (mirath)** mandates fixed shares to specific heirs
   and **overrides** a free allocation. A platform that "executes" a user's free split could be
   distributing assets unlawfully. **Core unresolved question:** advisory-only, enforced, or
   jurisdiction-aware?
2. **Death/incapacity verification must be server-trusted, never client-asserted.** A transfer
   of ownership on death is irreversible and adversarial (fraud incentive). Requires a verified
   death certificate + independent/multi-party review (executor, legal rep, possibly a registry),
   not a button. "12 months inactivity" similarly needs a server-measured, multi-step,
   grace-period process — never a self-serve flip.
3. **It moves securities-like assets.** Fractional ownership units are the asset. Transferring
   them on death or as a gift is a **change of beneficial ownership** → securities-transfer,
   **AML/CTF**, **sanctions screening**, and **KYC of the heir/recipient** (an unregistered heir
   can't legally hold units until verified — mirrors the Phase-10 REAL/PENDING model).
4. **Tax.** Inheritance/estate/gift tax varies by jurisdiction and residency; the platform may
   have withholding/reporting duties. Out of scope to compute, but must not be ignored.
5. **Minors / guardianship.** Gifting to a child ("turning 21") needs guardianship/custodian
   handling and age-gating.
6. **The "legal partners / legally binding" claims** are representations of professional legal
   service — they must be **true** (a real engaged firm + a real review workflow) or **removed**.
7. **PASSIVE interaction.** Estate scopes referencing passive income conflict with the
   hard-locked PASSIVE rail; estate must not reintroduce a passive promise.
8. **Cross-border + data protection.** Beneficiary PII (IDs, relationships) is highly sensitive;
   storage/residency/retention rules apply.

---

## 3. Proposed provisional architecture (PENDING legal sign-off — do not build yet)

Staged so each stage is independently legal-gated:

**Stage E0 — Honesty (no engine).** Correct the UI copy; remove false legal claims; keep an
honest "estate planning — in development with our legal partners" state. (This is the interim in §1.)

**Stage E1 — Beneficiary register (record of wishes, advisory-only).** Real persisted
beneficiaries (no automated transfer): name, relationship, role, contact, **declared** allocation,
scope, notes, status. Explicitly labelled **"a record of your wishes, not a legal will; subject to
applicable inheritance law"**. KYC-of-beneficiary optional at this stage. No trigger executes
anything. This is the most that can be built without resolving forced-heirship.

**Stage E2 — Verified-event execution (the real engine).** Only after legal sign-off on the
verification + heirship model: an executor/admin/legal-rep–driven, multi-party **estate event**
(death/incapacity) with uploaded evidence (reuse Group-2 document storage), review workflow,
and — on approval — an **atomic ownership transfer reusing the Phase-10 family-transfer
machinery** (ledger −/+ under the property `FOR UPDATE`, `reserved_units` invariant, fee_rate
stamp, KYC-gated materialization for unregistered heirs). Append-only `audit_log`. Reversible
holds before finalization.

**Stage E3 — Gifting.** Reframe as an explicit **inter-vivos transfer** (= a Phase-10 family
transfer / secondary-style move) with recipient KYC, AML screening, tax acknowledgement, and
(for minors) guardianship — NOT a "scheduled auto-gift" until the recurring/transfer-authority
questions are answered. Recurring gifts likely need per-occurrence confirmation.

**Reuse (no new money primitives):** ownership moves reuse `family_service` / `secondary_service`
atomic transfer + `reserved_units`; evidence reuses Group-2 storage; notifications reuse Phase-12;
beneficiary→heir KYC reuses Phase-2 + the Phase-10 PENDING/materialize-on-KYC pattern.

---

## 4. Data-model SKETCH (provisional — NOT a migration)

```
estate_plans            (user_id PK, status, jurisdiction, acknowledgement_version, updated_at)
estate_beneficiaries    (id, user_id FK, full_name, relationship, role, contact (encrypted),
                         id_type, id_ref (encrypted/tokenized), declared_allocation_pct, scope[],
                         beneficiary_user_id (nullable, set after KYC), status, notes, created_at)
estate_events           (id, subject_user_id FK, kind[death|incapacity|inactivity], status
                         [reported|under_review|verified|rejected|executed], reported_by,
                         evidence_document_ids[], reviewed_by, reviewed_at, created_at)   -- server-trusted
estate_transfers        (id, estate_event_id FK, beneficiary_id FK, property_id, units,
                         status[pending|kyc_wait|completed], ownership_ledger refs, created_at)
gift_transfers          (id, from_user, to_beneficiary/user, asset_kind, amount/units,
                         scheduled_for, recurring, status, confirmation refs)   -- inter-vivos
```
PII (`id_ref`, contact) **encrypted/tokenized at rest**; never store raw national-ID numbers in
the clear. All allocations stored as **declared wishes** with a jurisdiction + heirship flag, so
execution can apply the legally-correct model decided in §2.1.

---

## 5. Legal-questions checklist (the deliverable — for counsel, BEFORE build)

**A. Jurisdiction & governing law**
1. Which jurisdiction(s)/legal systems govern users' estates (residency vs nationality vs asset
   situs — the SPV/asset location)? Single or multi-jurisdiction at launch?
2. Which law governs the units themselves (DIFC/SPV jurisdiction) vs the user's personal estate?

**B. Forced heirship / Sharia**
3. Where forced-heirship / Islamic inheritance applies, can a user's platform allocation be
   **advisory only**, or must execution follow statutory shares? May we ever auto-execute a free split?
4. Do we need a **registered will** (e.g. DIFC Wills) for non-Muslims, and how does our record relate to it?
5. How do we handle conflicts between the user's declared allocation and mandatory shares?

**C. Death / incapacity / inactivity verification (server-trusted)**
6. What evidence legally suffices to act on death (death certificate? court grant of probate?
   government registry?) and **who** must verify (executor, court, our legal partner)?
7. Is "inactivity" ever a lawful trigger to move assets, or only to flag/freeze? Required grace +
   outreach steps?
8. Required multi-party approval before an irreversible transfer; reversal/clawback window if a
   verification is later disputed?

**D. Securities / AML / KYC**
9. Is transferring fractional units on death/gift a regulated securities transfer? Licensing impact?
10. AML/CTF + sanctions obligations on heirs/recipients; mandatory KYC before an heir can hold units?
11. Can units sit "pending" for an unregistered heir (Phase-10 model), and for how long?

**E. Tax**
12. Inheritance/estate/gift tax exposure; any platform withholding/reporting duty?

**F. Minors & capacity**
13. Rules for gifting/inheriting to minors (guardian/custodian, age release); incapacity handling?

**G. Representations & liability**
14. Can we say a record is "legally binding" / "reviewed by legal partners"? Only if we engage a
    firm + real review workflow — confirm exact permissible wording and required disclaimers.
15. Platform liability for executing (or failing to execute) an estate transfer; insurance needs?

**H. Data protection**
16. Storage/residency/retention/encryption rules for beneficiary PII (IDs, relationships, health/death data)?

**I. Product interactions**
17. Estate references to "passive income" — must be removed while PASSIVE is hard-locked; confirm.
18. Recurring gifts: per-occurrence authorization required, or standing mandate permitted?
19. Cross-border transfers (heir in a different country than the asset/SPV) — permitted? constraints?

---

## 6. What is explicitly NOT built in this group
No migration, models, services, routes, schemas, tests, or frontend changes. The estate/gifting
UI remains as-is (honest-disabled wrapper) until the checklist is answered and a build is scoped.
When built, the test plan will mirror prior groups: server-trusted event verification (no
client-asserted death/inactivity), owner/heir-scoped access, atomic ledger transfer reusing
`reserved_units` + KYC-gated materialization, audit-log assertions, and **zero false legal claims**.
