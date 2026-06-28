# Phase 13 — Admin / Scheduled Jobs / Reconciliation / Hardening (DESIGN, for sign-off)

**Status:** DESIGN — awaiting sign-off. No code until approved.
**Type:** operational + money-adjacent (reconciliation + LP-expiry read/scan ledgers; LP-expiry mutates request status). Design-first.
**Strict rule:** DELETE NOTHING — every mock is honest-disabled (stays, shows truthful state) or wired to real data; nothing silently removed.

---

## Schema / migration plan

**No new tables; migration `0014` is OPTIONAL and minimal.**
- **LP-expiry** reuses the existing `lp_exit_requests.status` Text column — it simply introduces a new value `'expired'` (no enum, no DDL). Statuses today: `open | cancelled | filled` → add `expired`.
- **Cron auth** = a config/env secret (`CRON_SECRET`), no DB.
- **Settings validation** = code only, no DB.
- **Reconciliation / portfolio** = read-only aggregation, no DB.
- Optional `0014`: an index `lp_exit_requests(status, expires_at)` to make the sweep cheap. Low priority; include only if we want it. **Recommendation: no migration** (or a one-line index-only `0014`).

---

## 1. Cron-auth seam + scheduling

**New dependency `require_admin_or_cron`** (in `deps.py`): passes if the caller is an authenticated admin (existing `AdminDep` path) **OR** presents a valid `X-Cron-Secret` header equal to `settings.cron_secret` (constant-time compare; rejected if the secret is unset). This keeps the SQLAdmin/admin-UI path working AND lets system cron call the endpoints with no admin password.

**Apply it to the cron-target endpoints (replacing `AdminDep` there):**
- `POST /api/v1/admin/withdrawals/execute` (Phase 7)
- `POST /api/v1/admin/withdrawals/reconcile` (Phase 7)
- `POST /api/v1/investments/maintenance/expire-reservations` (Phase 5)
- `POST /api/v1/admin/notifications/dispatch-emails` (Phase 12)
- `POST /api/v1/admin/liquidity/expire-requests` (NEW, §2)
- `GET  /api/v1/admin/reconciliation` (NEW, §3 — admin or cron)

Approve/reject and other admin actions keep `AdminDep` (human-only).

**Config:** add `cron_secret: str = ""` to `config.py`. **Buildable + testable locally** (header present/absent/wrong → 200/401). **VPS-gated:** the actual crontab entries + setting `CRON_SECRET` in prod env. Cadence table goes into `RUN_LOCAL.md` / a deploy note (execute ~1–5m, reconcile ~15m, reservation sweep ~5m, email drainer ~1m, lp-expiry ~10m, reconciliation nightly).

---

## 2. LP exit-request expiry sweep (real bug fix)

**The bug:** a lapsed exit request keeps `status='open'` forever, so `secondary_service.reserved_units` (which counts `LpExitRequest.status == "open"`) keeps the seller's units reserved across BOTH markets — they can't re-list or secondary-sell until they manually cancel.

**The fix:** `liquidity_service.expire_open_requests(session, *, now=None)` —
- `SELECT … FROM lp_exit_requests WHERE status='open' AND expires_at < now FOR UPDATE SKIP LOCKED` (batched).
- For each: set `status='expired'`, write an `audit_log` row. No money moves, no ledger rows — the units were never debited (a reservation is purely the `reserved_units` count), so flipping status releases them automatically.
- Idempotent (already-expired rows aren't reselected); safe to re-run.
- Endpoint `POST /api/v1/admin/liquidity/expire-requests` (`require_admin_or_cron`) → `{ expired: n }`.

**Buildable + fully testable locally.**

---

## 3. Reconciliation report (read-only, DB-wide)

**`reconciliation_service.run(session)`** — pure read, returns a structured report of **drift rows (ideally empty)** across:

| Invariant | Check |
|---|---|
| Wallet balance | `wallets.balance == Σ transactions.amount` per user |
| Pending balance | `wallets.pending_balance == Σ withdrawals.amount` where status ∈ {pending_review, approved, processing} |
| Property units | `available_units + Σ(pending-reservation units) + Σ(ownership_ledger units) == total_units` |
| Ownership conservation | `Σ ownership_ledger.units` per property == issued (`total − available − reserved`) |
| Family pending ≤ holding | per (holder, property): `Σ pending family_transfers.units ≤ net ownership_ledger` |
| Distribution split | per distribution: `Σ items.net_amount + Σ items.management_fee == gross_pool` |

- Endpoint `GET /api/v1/admin/reconciliation` (`require_admin_or_cron`) → `{ ok: bool, checks: [{name, drift_count, samples[]}] }` (`ok=true` ⇒ zero drift everywhere).
- `scripts/reconcile.py` — CLI wrapper printing the same report (cron-able nightly; non-zero exit on drift so cron can alert).
- **Read-only** — never mutates; it's a detector, not a repairer.

**Buildable + fully testable locally** (seed clean DB → `ok=true`; inject an inconsistency via raw SQL → that check flags it).

---

## 4. Settings validation

**`settings_service.validate_setting(key, value)`** — a per-key spec map:
- percentages (`*_pct`) → numeric, **0–100**; limits (`withdrawal_auto_approve_limit`) → numeric, **≥ 0**; days/minutes (`*_days`, `*_minutes`) → int ≥ 0; price-bound `*_pct` allow empty string (open); booleans (`lp_passive_enabled`) → "true"/"false".
- **`lp_passive_enabled` hard-locked:** any attempt to set it `true` is rejected ("PASSIVE economics undecided") — it can only be `false`.
- Unknown keys allowed (free settings) but typed ones enforced.
- Wired into **SQLAdmin** `PlatformSettingAdmin.on_model_change` (reject the save with a clean error) so a garbage value never reaches the store (no more silent fallback). Also callable from any future settings API.

**Buildable + fully testable locally** (validate good/bad values; passive-true rejected).

---

## 5. Dashboard mocks (DELETE NOTHING)

**Wire to real data:**
- **`PortfolioOverview`** → a new read endpoint **`GET /api/v1/investments/portfolio`** (`reconciliation`-style aggregate from `ownership_ledger` + `wallet`): `{ invested, current_value, total_returns, properties, units }`. Replaces the hardcoded `$125,000`. (current_value = Σ units × property.unit_price; invested = wallet.total_invested; returns = wallet.total_returns.)
- **`ActiveInvestments`** → live `investApi.list()` (already exists) — real investments, honest empty state.
- **`SecondaryMarketTab`** → keep the component but route its CTA to the live `/secondary-market` page (DELETE NOTHING; no duplicate mock order book). (Or wire to `secondaryApi` — routing is simpler and avoids a second implementation.)

**Honest-disable (component stays, "not available yet"):**
- **`ProShareCards`** → the D9 card honest-disable that was missed in Phase 11 (cards disabled across ALL roles). Same pattern as `VirtualCardRequest`.
- **`InstallmentSchedule`** → installments deferred to their own phase; show a "not available yet" state (keep mock in tree).

**InvestorDashboard chrome:**
- Greeting → real user name from `useAuth()` (retire "Welcome back, Ahmed").
- The dashboard's own header **Bell** (unwired) → remove the duplicate (the live bell lives in MainLayout) OR wire to `/notifications`. Recommendation: route it to `/notifications` for consistency (keeps the control, makes it real). The unwired Settings icon similarly → route to `/settings` or leave (minor).

**Buildable + testable locally.** The portfolio endpoint is a small money-read.

---

## 6. Public marketing claims — NO CHANGE

Footer "Regulated by Financial Services Authority", Hero "$50M+ AUM / 15,000+ owners / $125k ticker" — **owner asserts substantiation exists; LEFT AS-IS by owner decision.** Recorded in PROGRESS as the owner's call/responsibility. (No code touches these.)

---

## 7. Rate-limiting

Add **slowapi** (in-memory limiter keyed by client IP; default store is per-process — fine locally and acceptable on a single VPS worker; Redis store is the prod upgrade if multi-worker).
- Limits on abuse-prone unauthenticated endpoints: `POST /auth/login`, `/auth/register`, `/auth/password/forgot` (e.g. 5–10/min/IP), and the public webhooks `/payments/webhooks/*` (DoS protection — they're already signature-verified). Sane defaults, configurable via env.
- Over-limit → **429** with a clean JSON error (via the existing error envelope).

**Buildable + testable locally** (hammer login N+1 times → 429). **VPS note:** for multi-worker, point slowapi at Redis.

---

## 8. Health / infra

- **`/healthz`** → Redis becomes **optional-healthy**: overall status `ok` (200) when the **database is up**, regardless of Redis; Redis status still reported in the payload (`"redis": "down"` is informational, not a failure). Money paths use Postgres `FOR UPDATE`, not Redis.
- **VPS note:** if we keep Redis (rate-limit store / hot-row locks), provision it; otherwise it stays optional.

**Buildable + testable locally** (healthz returns 200 with redis down).

---

## Test plan (acceptance bar)

DB-backed `test_phase13_db.py` (+ unit tests):
1. **Cron auth** — each cron endpoint: valid `X-Cron-Secret` → 200; missing/wrong → 401; admin JWT still → 200; unset secret never authorizes.
2. **LP-expiry sweep** — a lapsed `open` request → `expired`; `reserved_units` drops by its units; the seller can now create a secondary listing / new exit for those units (was blocked); idempotent (second run = 0); a still-valid open request is untouched.
3. **Reconciliation** — clean seeded DB → `ok=true`, all checks zero drift; inject each inconsistency (raw SQL: bump a wallet balance; orphan a pending withdrawal; skew available_units; over-allocate family pending) → exactly that check flags it, with sample rows; report never mutates.
4. **Settings validation** — `platform_fee_pct=150` rejected; `=-1` rejected; `=abc` rejected; `=2.5` accepted; `withdrawal_auto_approve_limit=-5` rejected; **`lp_passive_enabled=true` rejected**, `=false` accepted.
5. **Portfolio endpoint** — returns real invested/current_value/returns/units from ledger+wallet; zero-state for a fresh user; auth required.
6. **Rate-limiting** — N logins within the window pass, N+1 → 429; a normal single login unaffected.
7. **Health** — DB up + Redis down → 200 `ok` with redis reported down.

Frontend: `PortfolioOverview` renders live values (mock `$125,000` retired); `ActiveInvestments` reads investApi; `ProShareCards` + `InstallmentSchedule` show honest-disabled state; greeting uses the real name; `SecondaryMarketTab` routes to the live page. Vitest guards for the wired/disabled surfaces.

---

## Local vs VPS-gated

**Buildable + fully testable locally now:** cron-auth seam + endpoint wrappers, LP-expiry sweep, reconciliation report + `scripts/reconcile.py`, settings validation, portfolio endpoint + dashboard wiring/honest-disables, rate-limiting, health optional-Redis.

**VPS-gated (verify live at the end):** the actual **crontab** entries firing all six jobs on schedule with `CRON_SECRET`; **Redis** provisioning (if kept) + non-degraded `/healthz`; multi-worker slowapi→Redis store (only if we run multiple workers); and the broader provider live-verification (Resend, NOWPayments, Stripe Connect, OAuth, Sumsub) already tracked in the VPS stack.

---

## Build order (after sign-off)

(optional `0014` index) → config `cron_secret` + `require_admin_or_cron` + apply to cron endpoints → LP-expiry sweep + endpoint → reconciliation_service + endpoint + `scripts/reconcile.py` → settings validation + SQLAdmin hook → portfolio endpoint → rate-limiting middleware → health optional-Redis → DB tests → frontend (PortfolioOverview/ActiveInvestments wire, SecondaryMarketTab route, ProShareCards/InstallmentSchedule honest-disable, greeting/bell) + vitest → gates green → PROGRESS.md.
