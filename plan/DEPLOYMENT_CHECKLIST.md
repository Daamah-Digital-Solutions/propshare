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

### 1.6 Resend — transactional email
1. Create a Resend account; **verify your sending domain**; create an **API key**.
2. Env (backend):
   - `EMAIL_PROVIDER=resend`
   - `RESEND_API_KEY=re_...`
   - `EMAIL_FROM=CapiMax <no-reply@yourdomain.com>`  (must be on the verified domain)
   - (Locally `EMAIL_PROVIDER=console` just logs emails; `smtp` is also supported via `SMTP_HOST/PORT/USER/PASSWORD`.)

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

---

## §2. Infrastructure

1. **VPS (Hostinger, EU)** — provision Ubuntu; install Python 3.14, PostgreSQL 16, nginx.
2. **Database** — create the `capimax` DB + user; set `DATABASE_URL=postgresql+asyncpg://USER:PASS@localhost:5432/capimax`.
3. **App** — create the venv, `pip install -e backend`, then:
   - `alembic upgrade head` (brings the schema to **0014**).
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

## §4. Cron jobs (7) — system cron → admin endpoints

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
30 2 * * *    curl -fsS      -H "X-Cron-Secret: SECRET" API/api/v1/admin/reconciliation
```

| Job | Endpoint | Purpose |
|---|---|---|
| Withdrawal executor | `POST …/admin/withdrawals/execute` | submit approved payouts to the provider |
| Withdrawal reconcile | `POST …/admin/withdrawals/reconcile` | re-query stuck `processing` payouts |
| Reservation-expiry sweep | `POST …/investments/maintenance/expire-reservations` | release lapsed unpaid direct-pay holds |
| Email outbox drainer | `POST …/admin/notifications/dispatch-emails` | send queued emails (Resend) |
| LP exit-request expiry | `POST …/admin/liquidity/expire-requests` | free units reserved by lapsed LP exit requests |
| Gift executor (Group 5) | `POST …/admin/gifts/run-due` | send 7-day gift reminders + execute due scheduled gifts (real transfer / wallet credit; recurring re-enqueue) |
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
6. **Resend email** — trigger a financial/security event (e.g. investment confirmed) → the outbox drainer (§4) delivers a real email; check Resend logs + the inbox.
7. **OAuth** — sign in with Google and with Apple → account provisions + logs in.
8. **Each cron** — fire all 6 manually once with the `X-Cron-Secret` header; confirm 200 + sensible counts.
9. **Reconciliation** — `python backend/scripts/reconcile.py` (or `GET …/admin/reconciliation`) → **`ok: true`, zero drift** across every check.
10. **Compliance copy** — the homepage/footer figures ("$50M+ AUM", "15,000+ owners", "Regulated by Financial Services Authority") are presented as substantiated marketing per the owner's assertion. Confirm each is backed before public launch (owner's responsibility).

---

## Notes / deferred (not part of launch wiring)
- **PASSIVE LP pool**, **installment plans**, **virtual cards**, and **documents/file storage** (incl. avatar + property image upload) are intentionally deferred and degrade honestly in the UI ("not yet available"). No keys are needed; they ship in their own later phases.
- The estate/beneficiary feature is handled by the separate **BRX** project, not CapiMax.
