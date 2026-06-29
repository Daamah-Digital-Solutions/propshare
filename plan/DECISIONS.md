# CapiMax PropShare — Decision Log

Locked product/engineering decisions, newest groups appended. Companion to `PROGRESS.md`
(state) — this file records *why*. Governing rules apply to every group below.

## Governing rules (all groups)
- **DELETE NOTHING** — never silent-remove; never ship a permanent honest-disabled stub. Build it real.
- **No fabricated numbers / no fake-success** — every figure has a real source or an honest empty state.
- **Reuse existing seams** — provider abstractions (email/storage/payments), `notify()`, ledger, OwnerDep.
- **Server-authoritative + owner-scoped** for anything money- or ownership-adjacent.
- **Verify-before-build**; on any contradiction with the live code, STOP and report.
- **Full gates green per commit** (ruff/black/mypy/pytest + tsc/eslint/vitest/build).

## Phase 15 / 15b / 15c (done earlier this arc)
- **15 — owner/dev stats:** pure aggregation, no migration; occupancy honest-empty; counts real.
- **15b — milestones:** `property_milestones` (mig 0015); NAV `value_index` nullable kept (no C/D regression);
  constructionProgress = current (in_progress) milestone %, else 0; fake 8-event PropertyTimeline deleted.
- **15c — investor communications:** `developer_updates` + `developer_update_recipients` (mig 0016);
  audience = per-property net-holders (Σ units>0); reuse Phase-12 `notify()`/outbox 1:1 (notify now returns
  the created Notification); metrics counts-only (recipients + in-app reads), NO open/click/delivered;
  manual 15b→15c bridge (pre-fill, never auto-send); idempotent on (update_id, user_id).

---

## Group 2 — Storage → Documents / Certificates (DONE 2026-06-28)
- **Storage seam** (`integrations/storage.py`, `STORAGE_PROVIDER`): "local" (default) writes
  REAL files under `storage_dir` (gitignored `backend/var/`), served by the app; "s3" (prod)
  lazy-imports boto3 + presigned URLs. No fake/placeholder files. Mirrors the email seam.
- **No migration** — the `documents` table (0001) + `profiles.avatar_url` + `properties.images`
  already exist (migrations stay at **0016**).
- **Documents:** owner-scoped upload (`POST /properties/{id}/documents`, 403 NOT_PROPERTY_OWNER);
  PUBLIC list + download (property docs are public on active/funded; draft → 404; user-scoped
  docs not served by the public route).
- **Certificates:** generated LIVE as a dependency-free PDF from the caller's net `ownership_ledger`
  holding (`GET /investments/certificate/{property_id}`; 404 NO_HOLDING). Not stored, always current.
  Wording is factual (ledger units; not a transferable security / SPV substitute).
- **Unblocked seams:** `POST /properties/{id}/images` (was 503) + `POST /profiles/me/avatar` now
  store real files; public assets served inline via `GET /files/{key}` (allow-listed prefixes only).
- **Frontend:** PropertyDocuments + InvestmentCertificates wired to real data (mock lists deleted);
  `apiRequest` now supports FormData; `fetchBlob` for authed PDF download.

## Group 3 — Saved Payment Methods (PCI-safe) (DONE 2026-06-28)
- **Tokens only, never card data.** Migration **0017**: `payment_customers` (one Stripe customer/user)
  + `saved_payment_methods` (TOKEN `provider_payment_method_id` + safe metadata brand/last4/exp,
  `is_default`; UNIQUE(provider, pm token) → idempotent re-add). No PAN/CVC ever stored.
- **Flow:** card collected client-side via a Stripe **SetupIntent** (Stripe.js/Elements) — raw card
  never hits our server; backend fetches brand/last4/exp **server-side** from Stripe (never trusts
  the client). Reuses the Phase-4 Stripe gateway seam (mockable; **503 when unconfigured**, like
  deposits/withdrawals).
- **Service/routes:** `payment_method_service` + `routes/payment_methods.py` under
  `/api/v1/wallet/payment-methods` (list/setup-intent/add/delete/set-default), PrincipalDep,
  user-scoped (cross-user add → 403, foreign delete → 404), first method = default, delete reassigns
  default. API response **never exposes the token**. Read-only SQLAdmin views.
- **Frontend:** `paymentMethodsApi`; InvestorWallet "Payment Methods" is a **real vault** (list +
  set-default + remove; Add starts the SetupIntent). DELETE NOTHING — honest empty-state kept.
- **Deferred (prod wiring, documented):** mounting Stripe **Elements** for the card-entry widget +
  setting `STRIPE_*` keys (the SetupIntent endpoint + vault management are real and tested now; the
  card-entry form is config-gated exactly like the deposit/withdrawal rails).

## Group 4 — Estate / Inheritance / Gifting — DESIGN ONLY (2026-06-28, NOTHING BUILT)
- Full design + **legal-questions checklist** in `plan/phase-estate-design.md`. **No code** (no
  migration/models/services/routes/tests/frontend) — this group is **gated on a real lawyer**.
- Key findings: the current `FamilyBeneficiaryGifting.tsx` is a 100% client-side mock with
  **false legal claims** ("reviewed by our legal partners / legally binding", "Legally
  acknowledged", "on verified death") and references **passive income** (PASSIVE is hard-locked).
- Hard blockers requiring counsel BEFORE build: forced-heirship / Sharia inheritance vs free
  allocation; **server-trusted** death/incapacity/inactivity verification (never client-asserted);
  securities-transfer + AML + heir-KYC; tax; minors/guardianship; data-protection for beneficiary PII.
- Provisional staged plan: E0 honesty (correct/disable copy) → E1 advisory beneficiary register →
  E2 verified-event atomic transfer (reuse Phase-10 family-transfer + `reserved_units` + KYC
  materialize; Group-2 storage for evidence) → E3 inter-vivos gifting. Each stage legal-gated.
- **Recommended interim (owner decision):** correct the mock's false legal claims to an honest
  "in development with our legal partners" state now (the one case where honest-disable is the
  correct *interim*, because building it real without counsel is itself the unsafe outcome).

### Group 4 — Estate BUILT (owner overrode the legal gate, 2026-06-28)
- **Owner explicitly waived fara'id (Sharia forced-heirship) compliance** and accepted the legal
  risk: allocation is **fully FREE** (holder-set %, sum ≤ 100), NOT enforced to statutory shares.
- **Owner confirmed the existing legal/"reviewed by legal partners" copy is substantiated** —
  frontend left **byte-for-byte unchanged** (no disclaimer added, no copy reworded). Only the
  **data layer** of `FamilyBeneficiaryGifting.tsx` was swapped from local mock → real `estateApi`
  (beneficiary half; UI extras round-trip via a `meta` JSONB). The **gifting** sub-section stays a
  local mock (inter-vivos gifting backend is pending — left untouched per scope).
- **Death verification = manual-admin ONLY** — no client-assert, no auto-inactivity. An admin
  uploads the death certificate (Group-2 storage) and confirms; transfers execute only then.
- **Migration 0018:** `estate_beneficiaries` (free %, REAL/PENDING like Phase-10, `meta` JSONB),
  `estate_events` (UNIQUE per deceased; status guards **idempotent** execution), `estate_transfers`.
- **Execution** reuses the Phase-8/10 atomic move: property `FOR UPDATE`, available = net − reserved
  (reserved_units respected), exact **Hamilton** split by free % (unallocated remainder stays with
  the estate), ledger −/+ with fee_rate stamp, audit. Non-user beneficiaries → PENDING, materialize
  on registration+KYC (same hook as family). Re-confirm = no-op (status guard).
- **Frontend NOT mounted** by this change (cleanup pass had unmounted it; re-mounting would be a
  markup change the owner forbade) — the component is wired + ready; mounting is the owner's call.
- **PII note:** beneficiary id_type/id_number stored as provided in `meta` (owner-accepted);
  encryption-at-rest remains the flagged hardening item in `phase-estate-design.md`.

---

## Group 5 — Inter-vivos Gifting (DONE 2026-06-29)
- **Owner: "follow the frontend and make it real."** The original mock was a SCHEDULED +
  recurring gift ("executes automatically on the date", "7-day reminder"). We built the REAL
  scheduling that backs every promise — NOT a redefinition to immediate-only, no fake
  auto-execute, no fake reminder. Design in `plan/phase-gifting-design.md`.
- **Migration 0019:** `scheduled_gifts` (giver, recipient user-or-pending-email, asset_type,
  property/units or amount, scheduled_for, recurring + optional `recurrence_end`, `series_id`,
  status [scheduled|pending|executed|cancelled|failed], failure_reason, reminder_sent_at,
  idempotency_key; UNIQUE(series_id, scheduled_for) + UNIQUE(idempotency_key)).
  `transaction_type += 'gift'`; `platform_settings += gift_fee_pct` (default 0).
- **Reserve-now (truthful):** property-share gifts reserve units via the shared
  `secondary_service.reserved_units` (a **4th term**: status ∈ {scheduled, pending}) — a gifted
  unit can't also be listed / LP-exited / family-allocated / double-gifted. Wallet gifts are
  **escrowed** at schedule via a real `wallet_service.debit`; refunded on cancel.
- **Executor cron** `POST /api/v1/admin/gifts/run-due` (`AdminOrCronDep`, `FOR UPDATE
  SKIP LOCKED`): pass 1 sends the **7-day reminder** (real Phase-12 `notify`, once via
  `reminder_sent_at`); pass 2 executes due gifts via the family atomic-transfer engine
  (ledger −N/+N, `fee_rate` stamped; wallet → credit recipient from escrow). REAL (KYC'd)
  recipient → immediate; non-user recipient → **pending**, materializes on KYC (reuse the
  Phase-10/Group-4 hook in `kyc_service`). Idempotent (no double move).
- **Recurrence:** re-enqueue the **next single occurrence only** (not every future year) —
  re-reserve units / re-escrow next year's cash then; skip + notify if the giver can no longer
  cover it. `UNIQUE(series_id, scheduled_for)` makes re-runs safe. End = until cancelled or
  optional `recurrence_end`.
- **Asset scope:** `property_shares` + `wallet` are REAL; `passive_income` (PASSIVE
  hard-locked), `rental_returns` (accrues to wallet, no separate stream), `tokenized`
  (tokenization is the separate **BRX** project — PropShare has no blockchain), `allocation`
  (no real backing) are **honest-disabled** in the UI (shown, not removed) and rejected by the
  schema. **Tokenized is NOT aliased to property_shares** (would mislead).
- **Zero-fee** via admin-editable `gift_fee_pct` (default 0 — a gift isn't a sale).
- **Frontend:** the gifting section of `FamilyBeneficiaryGifting.tsx` restored to the real
  compose flow (recipient name+email, occasion, asset [real enabled / others disabled],
  property+units or wallet amount, date, yearly recurring, message) + real gift cards with
  real statuses + Cancel; success toast only on a real 201. The reminder strip copy stays —
  it's now TRUE (the cron sends it). `giftsApi` added; beneficiary section untouched.
- **NEW cron** to add to the VPS crontab + DEPLOYMENT_CHECKLIST (now 7 jobs).
