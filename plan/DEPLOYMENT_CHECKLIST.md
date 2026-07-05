# CapiMax PropShare — Deployment Checklist (owner-facing)

Everything you must set up externally to take the platform live. Work top to bottom.
Each item lists **what to create**, the **exact env var**, and (where relevant) the
**webhook URL** to register and any provider-side config.

Conventions used below:
- `API` = your backend base URL, e.g. `https://api.capimax.example`
- `APP` = your frontend base URL, e.g. `https://app.capimax.example`
- Backend env vars go in `backend/.env` (or the systemd/container env). Frontend vars
  (prefixed `VITE_`) are baked into the build at `npm run build` time.
- Everything is built to **degrade honestly** until its keys are set (clear 503 / disabled
  UI), so you can deploy first and add providers incrementally.

---

## §1. Provider accounts & credentials

### 1.1 Stripe — card deposits (REQUIRED for card funding)
1. Create a Stripe account; get the **Secret key** and **Publishable key** (live mode).
2. Add a **webhook endpoint** → `API/api/v1/payments/webhooks/stripe`
   - Events: `checkout.session.completed`, `payment_intent.succeeded` (+ `.payment_failed`).
   - Copy the endpoint's **Signing secret**.
3. Env (backend):
   - `STRIPE_SECRET_KEY=sk_live_...`
   - `STRIPE_WEBHOOK_SECRET=whsec_...`
   - `STRIPE_PUBLISHABLE_KEY=pk_live_...`
4. Env (frontend): `VITE_STRIPE_PUBLISHABLE_KEY=pk_live_...` (only if the SPA shows Stripe UI; hosted checkout works without it).

### 1.2 Stripe Connect — bank withdrawals (payouts)
1. In Stripe, **enable Connect** (Express accounts recommended).
2. Add a **payout/Connect webhook endpoint** → `API/api/v1/payments/webhooks/stripe-payouts`
   - Events: `account.updated`, `payout.paid`, `payout.failed`, `transfer.*`.
   - (Reuses `STRIPE_WEBHOOK_SECRET` — same signing scheme; if Stripe gives a separate secret for this endpoint, use the one configured.)
3. No new key beyond `STRIPE_SECRET_KEY` (+ Connect enabled on the account).
4. Verify Connect/payouts are available in your operating region (GCC) before relying on bank withdrawals.

### 1.3 NOWPayments — crypto deposits (IPN)
1. Create a NOWPayments account; get the **API key** and set an **IPN secret**.
2. Register the **IPN callback** → `API/api/v1/payments/webhooks/nowpayments`
3. Env (backend):
   - `NOWPAYMENTS_API_KEY=...`
   - `NOWPAYMENTS_IPN_SECRET=...`
   - `NOWPAYMENTS_SANDBOX=false`  (true while testing on the sandbox)

### 1.4 NOWPayments — crypto withdrawals (payouts)
1. Enable the **Payouts/Mass-payout** API (requires account **email + password** for the JWT, **2FA**, and **IP-whitelisting** your VPS IP, plus a **funded payout balance**).
2. Register the **payout IPN** → `API/api/v1/payments/webhooks/nowpayments-payouts`
3. Env (backend):
   - `NOWPAYMENTS_EMAIL=...`
   - `NOWPAYMENTS_PASSWORD=...`
   - (reuses `NOWPAYMENTS_API_KEY` + `NOWPAYMENTS_IPN_SECRET`)

### 1.5 Sumsub — KYC
1. Create a Sumsub account; create an **App Token** + **Secret Key**; note your **level name**.
2. Configure a **webhook** → `API/api/v1/kyc/webhook/sumsub`; copy the **webhook secret**.
3. Env (backend):
   - `SUMSUB_APP_TOKEN=...`
   - `SUMSUB_SECRET_KEY=...`
   - `SUMSUB_WEBHOOK_SECRET=...`
   - `SUMSUB_LEVEL_NAME=basic-kyc-level`  (match your Sumsub level)
   - `SUMSUB_BASE_URL=https://api.sumsub.com`

### 1.6 Transactional email — Hostinger SMTP (owner's choice)
The owner sends via **Hostinger SMTP** (a mailbox on their domain), not Resend. The owner has
the mailbox credentials; DevOps sets these env vars:
   - `EMAIL_PROVIDER=smtp`
   - `SMTP_HOST=smtp.hostinger.com`
   - `SMTP_PORT=587`  ← **use 587 (STARTTLS)**. The sender does `SMTP(...)` + `starttls()`
     (`app/services/integrations/email.py`), so it needs a STARTTLS port. **Port 465
     (implicit SSL) is NOT supported** by the current sender — do not use 465.
   - `SMTP_USER=<the Hostinger mailbox address>`  (e.g. `no-reply@yourdomain.com`)
   - `SMTP_PASSWORD=<the mailbox password>`  (owner-held)
   - `EMAIL_FROM=CapiMax <no-reply@yourdomain.com>`  (use the same mailbox address)
   - (Locally `EMAIL_PROVIDER=console` just logs emails. `resend` is also supported —
     `EMAIL_PROVIDER=resend` + `RESEND_API_KEY=re_...` — if you ever switch providers.)
2. In Hostinger, ensure the mailbox exists and SMTP is enabled; set SPF/DKIM on the domain so
   mail isn't spam-filtered. Send a test after wiring (§5.6).

### 1.7 Google OAuth
1. Google Cloud Console → OAuth client (Web). Authorized redirect URI:
   `APP/auth/callback/google`
2. Env (backend): `GOOGLE_CLIENT_ID=...`, `GOOGLE_CLIENT_SECRET=...`
3. Env (frontend): `VITE_GOOGLE_CLIENT_ID=...`

### 1.8 Apple OAuth (Sign in with Apple)
1. Apple Developer → Services ID + Sign in with Apple key (`.p8`). Redirect URI:
   `APP/auth/callback/apple`
2. Env (backend): `APPLE_CLIENT_ID=...` (Services ID), `APPLE_TEAM_ID=...`, `APPLE_KEY_ID=...`, `APPLE_PRIVATE_KEY=<contents of the .p8>`
3. Env (frontend): `VITE_APPLE_CLIENT_ID=...`

### 1.9 File storage — documents / certificates / property images / avatars (BUILT, Group 2)
Works with **no keys** on the default local-FS provider, but in production you should decide where files live:
- **Local-FS (default):** `STORAGE_PROVIDER=local`, files under `STORAGE_DIR` (default `var/storage`, relative to the backend cwd). Put this on a **persistent, backed-up volume** — a container/VPS rebuild without it loses uploaded files. Served by the app.
- **S3 (recommended for prod):** `STORAGE_PROVIDER=s3`, `S3_BUCKET=...`, `S3_REGION=...`, optionally `S3_ENDPOINT_URL=...` (MinIO/custom) and `S3_PUBLIC_BASE_URL=...` (CDN; otherwise presigned GET URLs). Uses boto3 (lazily imported).
- `STORAGE_MAX_UPLOAD_MB=25` caps upload size (default 25).

---

## §2. Infrastructure

1. **VPS (Hostinger, EU)** — provision Ubuntu; install Python 3.14, PostgreSQL 16, nginx.
2. **Database** — create the `capimax` DB + user; set `DATABASE_URL=postgresql+asyncpg://USER:PASS@localhost:5432/capimax`.
3. **App** — create the venv, `pip install -e backend`, then:
   - `alembic upgrade head` (brings the schema to **0020** — the current head). This creates ALL tables, including milestones (0015), investor updates (0016), saved payment methods (0017), estate/beneficiaries (0018), scheduled gifts (0019), and installment plans (0020). A fresh deploy MUST reach 0020 or those features' tables will be missing. Confirm with `alembic current` → `0020 (head)`.
   - `python backend/scripts/seed_admin.py` (creates the first admin — set its email/password).
   - (optional) `python backend/scripts/seed_properties.py` to load demo properties.
4. **Run** — gunicorn + uvicorn workers behind nginx (see `backend/Dockerfile` CMD for the gunicorn invocation). Put nginx in front for TLS + reverse proxy to the app port.
5. **Domain + TLS** — point `API` and `APP` DNS at the VPS; issue Let's Encrypt certs (certbot). Force HTTPS.
6. **Core env (backend):**
   - `ENVIRONMENT=production`
   - `JWT_SECRET=<64+ random chars>`  ← MUST change from the dev default
   - `COOKIE_SECURE=true`  (refresh cookie over HTTPS only)
   - `COOKIE_SAMESITE=lax`, `COOKIE_DOMAIN=<parent domain if API/APP share one>`
   - `CRON_SECRET=<long random>`  (authenticates the cron jobs — §4)
   - `FRONTEND_ORIGIN=https://app.capimax.example`  (CORS allow-list; comma-separate if multiple)
   - `APP_BASE_URL=https://app.capimax.example`  (used in email links + OAuth/redirect building)
   - `REDIS_URL=redis://localhost:6379/0`  (optional — see §2.7)
7. **Redis (optional)** — only needed for multi-worker rate-limiting storage / hot-row locks. Health does NOT require it (DB gates `/healthz`). If you run multiple gunicorn workers and want shared rate-limit counters, provision Redis and keep `REDIS_URL` set.

---

## §3. Frontend env (build-time)

Set before `npm run build`, then deploy `dist/`:
- `VITE_API_BASE_URL=https://api.capimax.example`
- `VITE_GOOGLE_CLIENT_ID=...`  (§1.7)
- `VITE_APPLE_CLIENT_ID=...`  (§1.8)
- `VITE_STRIPE_PUBLISHABLE_KEY=pk_live_...`  (only if used by the SPA)

---

## §4. Cron jobs (8) — system cron → admin endpoints

All are **idempotent** and authenticate with the `X-Cron-Secret: $CRON_SECRET` header.
Example crontab (adjust cadence to taste):

```cron
# m h  command   (API = your backend base URL; SECRET = $CRON_SECRET)
*/2  * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/withdrawals/execute
*/15 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/withdrawals/reconcile
*/5  * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/investments/maintenance/expire-reservations
*    * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/notifications/dispatch-emails
*/10 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/liquidity/expire-requests
*/30 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/gifts/run-due
0    * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" API/api/v1/admin/installments/run-due
30 2 * * *    curl -fsS      -H "X-Cron-Secret: SECRET" API/api/v1/admin/reconciliation
```

| Job | Endpoint | Purpose |
|---|---|---|
| Withdrawal executor | `POST …/admin/withdrawals/execute` | submit approved payouts to the provider |
| Withdrawal reconcile | `POST …/admin/withdrawals/reconcile` | re-query stuck `processing` payouts |
| Reservation-expiry sweep | `POST …/investments/maintenance/expire-reservations` | release lapsed unpaid direct-pay holds |
| Email outbox drainer | `POST …/admin/notifications/dispatch-emails` | send queued emails (Hostinger SMTP) |
| LP exit-request expiry | `POST …/admin/liquidity/expire-requests` | free units reserved by lapsed LP exit requests |
| Gift executor (Group 5) | `POST …/admin/gifts/run-due` | send 7-day gift reminders + execute due scheduled gifts (real transfer / wallet credit; recurring re-enqueue) |
| Installment executor (Group 6) | `POST …/admin/installments/run-due` | send installment reminders + charge due installments from the wallet (progressive vesting); a missed one → overdue + notify (grace, retried) |
| Reconciliation report | `GET …/admin/reconciliation` | nightly DB-wide drift check (alert on non-zero) |

(Scheduled rental distributions are **admin-triggered per property/period** in `/admin` — there is no auto-runner; run them when a period closes.)

---

## §5. Live-verification runbook (after keys are in)

Run each end-to-end once on production and confirm the expected result:

1. **Stripe deposit** — deposit from the Wallet → complete hosted checkout → wallet balance credits (via the `…/webhooks/stripe` event, NOT the redirect). Check `/admin → Transactions`.
2. **NOWPayments deposit** — start a crypto deposit → pay the invoice → IPN credits the wallet.
3. **Stripe Connect payout** — "Link your bank" onboarding completes → request a bank withdrawal ≤ the auto-approve limit → it executes and settles; over-limit lands in `/admin → Withdrawals` review.
4. **NOWPayments payout** — request a crypto withdrawal → it executes; confirm funds leave; a returned/failed payout credits back.
5. **Sumsub KYC** — start verification → complete in the Sumsub SDK → the webhook flips KYC to `verified` (no manual admin step).
6. **Email (Hostinger SMTP)** — trigger a financial/security event (e.g. investment confirmed) → the outbox drainer (§4) delivers a real email; check the mailbox + the app logs. (Locally `EMAIL_PROVIDER=console` just logs the message.)
7. **OAuth** — sign in with Google and with Apple → account provisions + logs in.
8. **Each cron** — fire all 8 (§4) manually once with the `X-Cron-Secret` header; confirm 200 + sensible counts.
9. **Gift executor** — schedule a gift due today (property-share units or wallet amount) → confirm the units are reserved / the cash is escrowed at schedule → fire `POST …/admin/gifts/run-due` → confirm the real ownership transfer (or wallet credit) executed, and that a gift scheduled within 7 days produces the one-time 7-day reminder notification.
10. **Installment executor** — start an installment plan on an under-construction property (down payment charged from the wallet at creation; allocation reserved; down-payment units vest) → for a due installment, fire `POST …/admin/installments/run-due` → confirm the installment charges from the wallet and vests more units; a due-soon installment produces the reminder notification; draining the wallet before the run marks the installment `overdue` (grace — no forfeiture, retried next run).
11. **Reconciliation** — `python backend/scripts/reconcile.py` (or `GET …/admin/reconciliation`) → **`ok: true`, zero drift** across every check.
12. **Compliance copy** — the homepage/footer figures ("$50M+ AUM", "15,000+ owners", "Regulated by Financial Services Authority") and the LiquiditySection "Up to 12% APY" teaser (PASSIVE is hard-locked) are presented as substantiated marketing per the owner's assertion. Confirm each is backed before public launch (owner's responsibility).

---

## Notes — built vs genuinely deferred

**Built and live (no longer deferred):**
- **Documents / file storage** — BUILT (Group 2): real owner-scoped upload, public list/download, live PDF ownership certificates, and the property-image + avatar upload seams. Uses the storage seam in §1.9 (local-FS by default; S3 for prod). No "not available" stub remains.
- **Estate / beneficiaries / inheritance** — BUILT (Group 4) as **CapiMax's own feature** (NOT BRX — that earlier note was wrong). Beneficiary register (free allocation, sum ≤ 100; REAL/PENDING) + **admin-verified-death** execution (death certificate via the storage seam + admin confirm; never client-asserted) + atomic ownership transfer reusing the family engine. Tables created by migration 0018.
- **Inter-vivos gifting** — BUILT (Group 5): real **scheduled + recurring** gifts — units reserved / cash escrowed at schedule, executed on the date by the **gift executor cron**, recurring re-enqueue, non-user recipient materializes on KYC. Tables created by migration 0019. Nothing here is deferred.
- **Installment plans** — BUILT (Group 6): **progressive-vesting** purchase of under-construction units (owner-confirmed licensed). Down payment + monthly installments charged from the wallet; ownership vests per payment; the **installment executor cron** (§4) charges due installments (missed → overdue + grace, retried); admin-configurable `installment_fee_pct` (default 4.0); pre-handover units are reserved + excluded from rental yield. Tables created by migration 0020. Missed-payment late-fee/forfeiture + plan cancellation-refund are intentionally NOT implemented (need an explicit owner rule).

**Genuinely deferred (still honest-disabled in the UI; no launch wiring needed):**
- **PASSIVE LP (fixed-yield) pool** — engine built but **hard-locked** (`lp_passive_enabled=false`); stays locked pending the owner's yield-source + reserve-buffer + ALM + capital-adequacy + FSA-licence decision (with counsel). No real deposit is possible; the fixed APY must never render as guaranteed.
- **Virtual cards** — not built; honest-disabled.

**Hardening item (flagged, not blocking launch):**
- **Beneficiary PII encryption-at-rest** — estate beneficiary `id_type`/`id_number` are stored as-provided in `estate_beneficiaries.meta` (owner-accepted). Encryption/tokenization-at-rest is the flagged hardening item in `plan/phase-estate-design.md`.
