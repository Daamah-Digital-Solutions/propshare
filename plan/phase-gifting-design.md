# Inter-vivos Gifting — Design (Group 5) — DESIGN ONLY, awaiting sign-off

**Owner decision:** *follow the frontend and make it real.* The original mock
(`git show c804e90:src/.../FamilyBeneficiaryGifting.tsx`) was a **scheduled + recurring**
gift (recipient, occasion, asset, amount/units, scheduled date, yearly recurrence,
personal message, "executes automatically", "7-day reminder"). We build the REAL
scheduling that backs every one of those promises — no redefinition to immediate-only, no
fake auto-execute, no fake reminder. Immediate zero-price moves already exist as the
Phase-10 family Transfers; this group adds the **time-deferred** layer they never had.

Governing rules apply (DELETE NOTHING; no fabricated data/claims; reuse seams;
server-authoritative; atomic; idempotent; owner/user-scoped; full gates green).

---

## 0. Verified reuse map (all confirmed against live code)

| Promise in the UI | Real seam it binds to |
|---|---|
| Move property shares on the date | `family_service.create_transfer` pattern — property `FOR UPDATE`, `free = holding − reserved_units`, ledger −N/+N (`reason=gift_transfer_out/in`), `fee_rate` stamped (Decision-2), Σ/property conserved. (`family_service.py:230-296`) |
| Reserve so units can't be double-spent | `secondary_service.reserved_units` (`secondary_service.py:71-102`) — currently sums active listings + open LP exits + pending family transfers. **We add a 4th term: scheduled gifts OUT.** |
| Recipient not yet a user → still works | estate/family REAL/PENDING + `materialize_for_user` on KYC, wired through `kyc_service._materialize_family` (`kyc_service.py:196-203`). |
| "executes automatically" on the date | Phase-13 cron seam: `AdminOrCronDep` (admin OR `X-Cron-Secret`, constant-time, unset⇒disabled — `deps.py:119-139`) + the `FOR UPDATE SKIP LOCKED` drainer pattern (`liquidity_service.expire_open_requests`, `liquidity_service.py:465-504`). |
| "notify you 7 days before" | `notification_service.notify` (in-app always; email only if `email_category` + pref on — `notification_service.py:49-90`) + the existing outbox drainer. |
| Wallet-balance gift | `wallet_service.debit` / `credit` (the only balance-mutating code; `FOR UPDATE`, balance≥0 backstop — `wallet_service.py:43-141`). |
| Zero fee ("a gift isn't a sale") | `settings_service` `family_transfer_fee_pct` default `0`, admin-editable (`settings_service.py:105,116-130`). We add `gift_fee_pct` default `0` (same pattern) so it's its own knob. |
| Owner-scoped + idempotent endpoints | `PrincipalDep`; `Idempotency-Key` header (`family.py:_idem`). |

---

## 1. The six open decisions — resolved (per owner) + the one new sub-decision

1. **Real scheduling — BUILD IT.** New `scheduled_gifts` table + a cron that executes due
   gifts via the atomic transfer. This is what makes "executes automatically" truthful.
2. **Reserve now.** Property-share gifts reserve units at schedule time (extend
   `reserved_units`); released on cancel. **Sub-decision A (NEW — needs your nod):** wallet
   has no unit-reservation primitive, so "reserve now" for a **wallet** gift means
   **debit-to-hold at schedule** (a withdrawal-style escrow: `wallet_service.debit` now,
   `credit` recipient at execution, `credit` refund on cancel). Recommended, because it's
   the only way "reserved / can't be double-spent" is *true* for cash. Alternative =
   validate-at-execution (no hold) — but then the promise isn't real. **I recommend the hold.**
3. **Recurring yearly — KEEP.** On execution of a recurring gift, enqueue the next
   occurrence (same month/day, +1 year) as a new `scheduled` row linked by `series_id`;
   end condition = **until cancelled** + optional `recurrence_end` date. Cancel stops the
   series. Idempotent via `UNIQUE(series_id, scheduled_for)`.
4. **Asset scope — follow the UI, honest-disable what has no backing:**
   - **`property_shares` → REAL** (unit transfer).
   - **`wallet` → REAL** (balance move, per sub-decision A).
   - **`passive_income` → HONEST-DISABLED** — PASSIVE is hard-locked (`lp_passive_enabled=false`); a gift of passive income can't be real. Shown disabled exactly as PASSIVE is everywhere else.
   - **`rental_returns` → HONEST-DISABLED** — returns accrue into the wallet (Phase 6/7); there's no separate "future rental stream" asset to gift. Gift the wallet instead.
   - **`tokenized` / `allocation` → HONEST-DISABLED** — no distinct on-chain/allocation product exists; "tokenized ownership" *is* property shares. Faking a separate asset would be a fabricated claim. (If you'd rather alias `tokenized → property_shares`, say so — I'll alias instead of disabling.)
5. **Zero fee** — `gift_fee_pct` default `0`, admin-configurable (same setting pattern). A gift isn't a sale.
6. **Recipient resolution** — KYC'd user → REAL; non-user / not-yet-KYC'd → PENDING, materializes on register+KYC (reuse the hook). **Necessary UI deviation (flagged):** the mock's recipient was a free-text *name* from a hardcoded list — a name can't be a real transfer target. The compose form will pick the recipient from the caller's **existing family members / estate beneficiaries (which already carry an email)** or a typed **email**, resolving to user-or-pending. Minimal markup change, and the only honest way to target a real ledger move.

---

## 2. Schema + migration (`0019_group5_gifting`)

`scheduled_gifts`
| column | type | notes |
|---|---|---|
| `id` | uuid pk | `gen_random_uuid()` |
| `giver_id` | uuid fk users CASCADE | owner-scoped |
| `recipient_user_id` | uuid fk users SET NULL, null | resolved KYC'd user, else null |
| `recipient_email` | text, null | for pending recipients (materialize key) |
| `recipient_name` | text | display only |
| `asset_type` | text | `property_shares` \| `wallet` (CHECK) — disabled types never reach the API |
| `property_id` | uuid fk properties SET NULL, null | required iff `asset_type='property_shares'` |
| `units` | int, null | property gifts |
| `amount` | numeric(18,2), null | wallet gifts |
| `occasion` | text, null | display only (birthday/graduation/…) |
| `message` | text, null | personal note |
| `scheduled_for` | date, not null | execution date |
| `recurring` | bool, default false | yearly |
| `recurrence_end` | date, null | optional series end |
| `series_id` | uuid, not null | groups a recurring chain; first row = own id |
| `status` | text, default `scheduled` | `scheduled` \| `executed` \| `cancelled` \| `failed` |
| `failure_reason` | text, null | real reason on `failed` (never silently dropped) |
| `reminder_sent_at` | timestamptz, null | 7-day reminder idempotency |
| `hold_tx_ref` | uuid, null | wallet-hold linkage (sub-decision A) |
| `executed_at` / `materialized_at` / `created_at` / `updated_at` | timestamptz | |

Constraints: `CHECK (asset_type IN ('property_shares','wallet'))`;
`CHECK (units > 0 OR amount > 0)`; `UNIQUE(series_id, scheduled_for)` (recurrence
idempotency). New setting `gift_fee_pct` default `0` (validated `pct`).

Migrations move **0018 → 0019**. Models in new `app/models/gifting.py`; export via `app/models/__init__.py`.

---

## 3. Reservation invariant extension

Add a 4th term to `secondary_service.reserved_units` (the single shared rule): sum of
`scheduled_gifts.units` where `giver_id = user`, `property_id = property`,
`asset_type='property_shares'`, `status='scheduled'`. Result: a unit promised to a future
gift can't simultaneously be listed (Phase 8), LP-exited (Phase 9), family-allocated
(Phase 10), or estate-allocated availability (Group 4) — checked under the property
`FOR UPDATE`. Cancel/fail flips status out of `scheduled`, releasing it with no ledger move
(same release semantics as LP-expiry). **One regression test per existing reserving feature**
confirms scheduled gifts now count.

---

## 4. Service — `app/services/gift_service.py`

- `schedule_gift(session, giver_id, data, idempotency_key)`:
  validate asset_type ∈ {property_shares, wallet}; resolve recipient (`_resolve_user`
  pattern); for `property_shares` lock property `FOR UPDATE`, require
  `units ≤ holding − reserved_units` (reserve-now); for `wallet` require
  `amount > 0` and **debit-to-hold now** (sub-decision A), store `hold_tx_ref`;
  insert `scheduled` row (`series_id = id`); audit; idempotent on `Idempotency-Key`.
- `cancel_gift(session, giver_id, gift_id)`: owner-scoped; only `scheduled` cancellable;
  flip to `cancelled`; **wallet → refund credit**; property → reservation auto-released by
  status; stop recurrence; audit.
- `list_gifts(session, giver_id)`: owner's own, real statuses (no fabricated cards).
- `run_due(session, now=None)` — the cron body, two idempotent passes, `FOR UPDATE SKIP LOCKED`:
  1. **Reminders:** `scheduled` gifts with `scheduled_for − 7d ≤ now`, `reminder_sent_at IS NULL`
     → `notify()` the giver (in-app; email if pref on), stamp `reminder_sent_at`.
  2. **Executions:** `scheduled` gifts with `scheduled_for ≤ now`:
     - property: re-check `units ≤ holding` under property `FOR UPDATE`; if recipient REAL
       → ledger −N/+N (`gift_transfer_out/in`, `fee_rate` stamped); if PENDING → leave units
       in giver's ledger, record a pending gift transfer (materializes on KYC).
     - wallet: credit recipient from the hold (`hold_tx_ref`); pending recipient → keep hold,
       materialize on KYC.
     - insufficient funds/units or recipient never KYC'd by date → `status='failed'` +
       `failure_reason` + giver notification + **refund wallet hold**; never silent-drop.
     - flip `executed`, stamp `executed_at`; if `recurring` and (`recurrence_end` null or
       next ≤ end) insert the next-year `scheduled` row (`series_id` carried;
       `UNIQUE(series_id, scheduled_for)` makes re-runs safe). Re-reserve for the next cycle
       happens at that insert (property) / next debit-to-hold (wallet) — **sub-decision B
       (NEW): for recurring wallet gifts, do we hold each year's cash at each enqueue
       (truthful "reserved") or debit at execution? Recommend hold-at-enqueue for parity
       with the one-shot path; flagging because it ties up cash a year ahead.**
- `materialize_for_user(session, user_id)`: link pending gifts by email, convert pending
  property/wallet gifts to real moves (mirrors `estate_service.materialize_for_user`).
  Wired into `kyc_service._materialize_family`.

---

## 5. Routes

- `app/api/routes/gifts.py` (`PrincipalDep`, owner-scoped):
  `GET /api/v1/gifts`, `POST /api/v1/gifts` (Idempotency-Key), `POST /api/v1/gifts/{id}/cancel`.
- `app/api/routes/admin/gifts.py` (`AdminOrCronDep`):
  `POST /api/v1/admin/gifts/run-due` → `{reminders_sent, executed, failed}`. Cron target.
- Read-only SQLAdmin view for `scheduled_gifts` (consistent with estate/payments).

---

## 6. Frontend wiring (`FamilyBeneficiaryGifting.tsx` gifting section only)

Restore the original compose flow (recipient, occasion, asset, amount/units, date,
recurring, message) + the scheduled-gift cards + the reminder strip — **now backed by real
data**:
- Recipient selector = caller's family members / beneficiaries (carry email) or typed email.
- Asset `<Select>`: `property_shares` + `wallet` enabled; `passive_income`, `rental_returns`,
  `tokenized`, `allocation` rendered **disabled** with a short "not available" hint (honest,
  same posture as PASSIVE) — not removed.
- Cards render real `scheduled_gifts` with real statuses (`scheduled`/`executed`/`cancelled`/
  `failed` + reason); Cancel calls the real endpoint. No fabricated gifts, no fake-success
  toast — the success toast fires on a real 201.
- Reminder strip copy stays (it's now true — the cron sends it). `giftsApi` added to `src/lib/api.ts`.

The **beneficiary** section is untouched (already real, Group 4). The "Transfers" honest
placeholder is replaced by this real flow.

---

## 7. Test plan

Backend (`test_gifting_db.py`): schedule reserves units (and a concurrent list/LP-exit/
family-transfer now sees them reserved); wallet schedule debits-to-hold; executor on the
date moves real ownership atomically + conserves Σ/property; wallet execution credits
recipient from hold; recurrence re-enqueues exactly one next-year row (UNIQUE blocks dupes);
pending recipient materializes on KYC (property + wallet); cancel releases reservation /
refunds hold + stops recurrence; idempotent execution (double `run-due` = no double move);
`passive_income`/`rental_returns`/`tokenized`/`allocation` rejected (422); zero-fee
(`gift_fee_pct=0`); insufficient units/funds → `failed` + reason + refund (never dropped);
owner-scoping (foreign gift cancel → 404); cron-secret gate (missing/wrong/unset → 401);
reminder sent once (`reminder_sent_at` idempotency).
Frontend: compose posts real payload; disabled assets not selectable; cards reflect API
statuses; cancel calls API; no fabricated cards; success toast only on real success.

Full gates green per commit (ruff/black/mypy/pytest + tsc/eslint/vitest/build).

---

## 8. Open items needing your sign-off
- **Sub-decision A** — wallet gift "reserve now" = debit-to-hold at schedule (recommended) vs validate-at-execution.
- **Sub-decision B** — recurring **wallet** gifts: hold each year's cash at enqueue (recommended, truthful) vs debit at execution.
- **`tokenized`** — honest-disable (recommended) vs alias to `property_shares`.
- Everything else is locked by your decision text above.
