# Phase 11 — Broker / Referrals / Commissions (DESIGN, for sign-off)

**Status:** DESIGN — awaiting owner sign-off. No code until approved.
**Type:** MONEY PHASE (credits broker wallets) — design-first discipline applies.
**Locked decisions:** broker→client only; commission = pct × **platform revenue attributable to the referred client** (NEVER investment amount); rate = admin-editable `broker_commission_pct` (no literals); accrues on revenue events while client holds; no clawback; payout to broker wallet (Phase-7 rails for cash-out); cards honest-disabled (D9); broker-scoped referral code UX; dead routes built-or-removed.

---

## 0. The one thing to confirm at sign-off — the revenue-event set

Commission base is **platform revenue attributable to the referred client**. The platform earns from a client at these points:

| Event | Phase | When | Recurring? | In v1 commission scope? |
|---|---|---|---|---|
| **Purchase platform fee** (buyer-side, default 2.5%) | 5 | investment confirmed | one-time per investment | **YES (recommended)** — matches "accrues when investment is confirmed" |
| **Rental management fee** (withheld per distribution) | 6 | each rental distribution while holding | recurring | **YES (recommended)** — matches "recurs on every revenue event while they hold" |
| Secondary resale fee (buyer-side) | 8 | client buys on secondary mkt | per trade | **NO in v1** (deliberate exclusion; trivially added later) |
| Liquidity fee (seller-side) | 9 | client exits via LP | per exit | **NO in v1** |

**Recommended v1 scope = purchase platform fee + rental mgmt fee.** The engine is generic over `revenue_event_type`, so adding resale/liquidity later is one hook each — no schema change. **Confirm or trim this set at sign-off.**

Why never investment amount: a 10% rate on a $50k investment = $5,000, but the platform only earns ~2.5% ($1,250) at purchase + ~1%/yr mgmt fee — paying 5% of investment loses money on every referral. Commission = pct × *actual platform revenue*, so the broker's payout **structurally cannot exceed what the client earned the platform** (enforced as a DB CHECK).

---

## 1. Schema (migration `0012_phase11_broker`)

No enum change — `transaction_type.referral_commission` already exists (0001). Three new tables + one settings seed.

### `broker_codes` — one shareable code per broker
```
id           uuid pk
broker_id    uuid  fk users(id)  UNIQUE        -- one code per broker
code         text  UNIQUE                       -- server-generated, human-friendly (e.g. 8-char base32)
created_at   timestamptz default now()
```
Generated server-side on first request (or on broker-role grant). Broker cannot choose arbitrary codes.

### `broker_referrals` — the broker↔client link (first-class, queryable, immutable)
```
id           uuid pk
broker_id    uuid  fk users(id)
client_id    uuid  fk users(id)  UNIQUE         -- a client is attributed to AT MOST one broker, set once at signup
code_id      uuid  fk broker_codes(id)
created_at   timestamptz default now()
CHECK (broker_id <> client_id)                  -- no self-referral link
```
This is the "this client came from broker Y" fact that gates which revenue events accrue commission.

### `broker_commissions` — append-only accrual + credit ledger
```
id                 uuid pk
broker_id          uuid  fk users(id)
client_id          uuid  fk users(id)
referral_id        uuid  fk broker_referrals(id)
revenue_event_type text                          -- 'investment_platform_fee' | 'distribution_mgmt_fee'
revenue_event_id   uuid                          -- investments.id  OR  distribution_items.id
revenue_amount     numeric(18,2)                 -- the platform revenue this commission is based on
commission_rate    numeric(6,3)                  -- broker_commission_pct SNAPSHOT at accrual (history immutable)
commission_amount  numeric(18,2)                 -- revenue_amount * rate/100, quantized to cents
transaction_id     uuid  fk transactions(id)     -- the broker-wallet credit
created_at         timestamptz default now()
UNIQUE (revenue_event_type, revenue_event_id)    -- ONE revenue event -> AT MOST one accrual (idempotency)
CHECK (commission_amount >= 0)
CHECK (commission_amount <= revenue_amount)      -- structural: broker never paid more than platform earned
```

### Settings
`platform_settings` seed `broker_commission_pct` (**proposed default 10.0** = % of platform revenue; admin to confirm number). Mirror in `settings_service.DEFAULTS`; add `get_broker_commission_pct()` helper (same pattern as `get_liquidity_settings`/`liquidity_fee_pct`).

---

## 2. The broker↔client link (referral-code UX, broker-scoped)

- **Broker gets a code/link:** `GET /api/v1/broker/referral-code` (broker-role gated) → creates-or-returns the broker's `broker_codes` row + a shareable link `${FRONTEND}/auth?ref=<code>`.
- **Signup captures it:** `Auth.tsx` reads `?ref=<code>` (and offers a manual "Referral code" field), passes it as `referral_code` to `authApi.register` (already plumbed end-to-end).
- **Register resolves it (atomic, in the provision tx):**
  1. If `referral_code` matches a `broker_codes.code` **and** `broker_id != new_user.id` → create `broker_referrals(broker_id, client_id=new_user, code_id)` **and** set `users.referred_by = broker_id` (attribution symmetry). Link is immutable (UNIQUE client_id).
  2. Else fall back to the existing `_resolve_referral` UUID path → sets `referred_by` only, **no `broker_referrals`, no commission** (generic user→user attribution stays commission-free — anti-self-referral-fraud).
- Self-referral / non-broker codes → no link → no commission. (Tested.)

---

## 3. Revenue-attribution engine (the core)

A single reusable helper makes accrual identical at every hook:

```
broker_service.accrue_commission(
    session, *, client_id, revenue_event_type, revenue_event_id, revenue_amount,
    locked_broker_wallets   # brokers whose wallets the caller has ALREADY locked in order
) -> None
```
1. Look up `broker_referrals` by `client_id`. **None → return** (covers non-referred, generic-attribution, and self-referral clients → no commission).
2. `rate = settings_service.get_broker_commission_pct()`; `commission = (revenue_amount * rate/100).quantize(cents)`. `commission <= 0 → return`.
3. Credit the **already-locked** broker wallet (`wallet_service.credit`, `tx_type=referral_commission`, `reference_id=<event_id>`, description names the client + event).
4. Insert `broker_commissions` row (snapshots `commission_rate`, links `transaction_id`). **UNIQUE(revenue_event_type, revenue_event_id)** guarantees one-event→one-accrual even under retries/refactors.

### Atomicity & lock order (priority-1)
The broker wallet is **another wallet** in the same atomic tx, so it must join the **global wallet lock order (sorted by `str(user_id)`)** — never locked ad-hoc after owner wallets, or two concurrent distributions sharing a broker could deadlock.

**Hook A — Phase-6 distribution** ([distribution_service.run_distribution](backend/app/services/distribution_service.py:143)):
- Before the credit loop, compute the **union** of wallets to lock = `{owners with net>0} ∪ {referring brokers of owners whose mgmt fee > 0}`, sort by `str(user_id)`, lock all FOR UPDATE up front (pre-lock helper). Then the existing credit loop runs against already-locked rows.
- Inside the loop, **after** writing each `DistributionItem` (now `flush()`ed to get its `.id`), if `fee > 0`: `accrue_commission(client_id=uid, type='distribution_mgmt_fee', event_id=distribution_item.id, revenue_amount=fee)`.
- Period-level idempotency already blocks re-runs (UNIQUE property_id+period_key → 409); the per-event UNIQUE is defense-in-depth.

**Hook B — Phase-5 confirm** (wallet-funded `confirm` + direct-pay webhook confirm):
- Fold the broker wallet into the buyer's wallet lock: lock `sorted([buyer_id, broker_id])` FOR UPDATE before booking money.
- After the buyer's platform fee is booked, `accrue_commission(client_id=buyer, type='investment_platform_fee', event_id=investment.id, revenue_amount=platform_fee)`.
- Phase-5 confirm is already idempotent (idempotency_key + status guard); per-event UNIQUE is defense-in-depth.

### Stops on exit / no clawback — structural, no special code
- Mgmt-fee commission only fires when a rental distribution withholds a fee on units the client **still holds** (fee base is ownership-derived). Full exit → 0 units → 0 fee → 0 commission. (Tested.)
- `broker_commissions` is append-only; nothing reverses a paid credit. No negative rows, no clawback. (Tested.)

---

## 4. `broker_commission_pct` flow — zero literals

`platform_settings.broker_commission_pct` → `settings_service.get_broker_commission_pct()` → (a) accrual calc, (b) `GET /broker/dashboard` payload so the UI shows the live rate, (c) reports. Each accrual **snapshots** the rate into `broker_commissions.commission_rate`, so an admin change applies to *future* accruals only; history is immutable. No `5` (or any rate) anywhere in code or JSX.

---

## 5. API (new `routes/broker.py`, all broker-role gated)

- `GET /api/v1/broker/referral-code` → `{ code, share_link }` (creates on first call)
- `GET /api/v1/broker/dashboard` → `{ commission_rate, total_referrals, total_commission, this_period, referrals_preview }`
- `GET /api/v1/broker/referrals` → referred clients + per-client commission-to-date (client identity masked for privacy)
- `GET /api/v1/broker/commissions?limit&offset` → the commission ledger (paginated)
- Register flow (existing route) extended to resolve broker codes (§2).

SQLAdmin: read-only **BrokerCode**, **BrokerReferral**, **BrokerCommission** views.

---

## 6. Frontend

- **`brokerApi`** in `api.ts`: `referralCode()`, `dashboard()`, `referrals()`, `commissions()`.
- **`BrokerDashboard.tsx` de-mocked:** retire `brokerStats` / `referrals` / `commissionData` hardcoded arrays + the "Premium Realty Partners" / "Ahmed Al-Farsi" mock names. Live: stats from `/broker/dashboard`; Referrals tab = real referred clients; Commissions tab = real `broker_commissions` ledger + live rate; Wallet tab = real `walletApi` + existing Phase-7 withdraw. A **shareable referral code/link** card (copy button). Dead buttons either wired or honest-disabled (no fake success).
- **Virtual Cards (D9) honest-disabled across ALL roles** (broker/owner/developer/LP): `VirtualCardRequest` degrades to a "Virtual cards — not yet available" empty state; "Request Virtual Card" disabled; no seeded fake cards, no fake issuance. (Same honest-degrade pattern as Pronova / PASSIVE.) Component kept, not deleted.
- **Dead broker sidebar routes** ([AppSidebar.tsx:241-257](src/components/layout/AppSidebar.tsx:241)) — no half-dead nav ships:
  - `/referrals`, `/commissions` → repoint to the real BrokerDashboard tabs (or build as thin pages).
  - `/broker-wallet` → repoint to the shared wallet surface (brokers use the same wallet).
  - `/broker-reports`, `/broker-documents` → **out of v1 scope → remove** these sidebar items.
  - `/exit-mechanisms` → verify; repoint to the real exit surface or remove.
  - (`/property-types`, `/secondary-market`, `/liquidity-market` already real — keep.)

---

## 7. Test plan (DB-backed, the acceptance bar)

1. **Commission = pct × actual platform revenue, NEVER investment amount** — referred client invests + a rental distribution runs → commission == rate% × `distribution_item.management_fee` (and == rate% × platform_fee for the purchase event); assert it is NOT rate% × investment amount.
2. **No accrual at signup** — register with broker code → `broker_referrals` row, **zero** `broker_commissions`, zero broker credit.
3. **Accrual on each revenue event** — two rental periods → two commission rows keyed to distinct `distribution_items.id`; purchase event → its own row.
4. **Stops on full exit** — client sells all units → next distribution withholds no fee on them → no new commission row.
5. **No clawback** — exit/sale never reverses prior commissions; broker balance never decreases from it.
6. **Idempotent (one revenue event → one accrual)** — re-run distribution → 409 (period dupe); direct attempt to accrue twice on the same `revenue_event_id` → UNIQUE violation, no double credit.
7. **Admin rate change reflected** — change `broker_commission_pct` → next period accrues at the new rate; prior rows keep their snapshotted rate.
8. **Self-referral / generic path carries no commission** — broker signs up with own code → no link; generic `referred_by` (user UUID) → no `broker_commissions`.
9. **Structural cap** — `commission_amount <= revenue_amount` holds (CHECK); rate ≥100 still can't overpay; rate input guarded.
10. **Atomicity** — broker credit + commission row + distribution all one tx; injected failure → full rollback, no orphan commission; `balance == SUM(ledger)` for the broker incl. `referral_commission` credits.
11. **Lock order / no deadlock** — concurrent distributions on two properties sharing one referring broker complete without deadlock (union-wallet pre-lock in sorted order).
12. **Auth/role gating** — all `/broker/*` endpoints 401/403 for non-brokers.
13. **Referral code** — deterministic, unique, one-per-broker; signup links client; link immutable (already-linked client can't be re-linked).

Frontend: `BrokerDashboard.test.tsx` (live API, mock arrays retired, referral code visible); cards honest-disabled guard.

---

## 8. Invariants (NEVER break)

- `commission_amount <= revenue_amount` (DB CHECK) — broker never paid more than the platform earned from that client.
- One revenue event → ≤1 accrual (`UNIQUE(revenue_event_type, revenue_event_id)`).
- `balance == SUM(ledger)` including `referral_commission` credits.
- `broker_referrals.client_id` UNIQUE + immutable — a client attributed to exactly one broker, set once.
- Generic `referred_by` (user→user) path is commission-free; only `broker_referrals` accrues.
- Commission rate flows from `platform_settings` to every surface; zero inline literals; history immutable via per-row snapshot.

---

## 9. Build order (after sign-off)

migration 0012 → models + settings helper → `broker_service` (link + accrue) → register-flow link resolution → Hook A (Phase-6) + Hook B (Phase-5) with union-wallet pre-lock → routes + schemas + SQLAdmin → DB tests → frontend (brokerApi, BrokerDashboard de-mock, cards honest-disable, route cleanup) → gates green → PROGRESS.md.
