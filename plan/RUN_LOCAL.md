# Local run & test — capimax-propshare (FastAPI + Vite)

Updated after the pre-Phase-4 hardening pass (DB-backed tests + `/admin` panel).

## Port map (dedicated, both projects run together)
| Project | Backend | Frontend |
|---|---|---|
| **PropShare** (this repo) | **8001** | **8081** |
| **BRX** (separate project) | 8000 | 8080 |

PropShare is permanently pinned to **8001 / 8081** (Vite `strictPort: true`), so it never
collides with BRX on 8000/8080. Don't confuse them: if you opened 8080 you're looking at BRX.

## Already done on this machine (one-time)
- Postgres role/db: `capimax` / db `capimax` on **port 5433** (+ `pgcrypto`).
- `capimax` was granted **SUPERUSER** locally (migration `0001` creates the legacy
  Supabase stub roles). Local dev only — do NOT do this on the VPS.
- Migrations applied through `0004`; `scripts/seed_properties.py` loaded the 7 demo listings.
- Admin account for the panel: **admin@capimax.com / Admin123!secure** (granted `admin`).

## Backend (FastAPI) — cmd, from `E:\Work\capimax-propshare\backend`
```cmd
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8001
```
- API:        http://localhost:8001
- Docs:       http://localhost:8001/docs
- Health:     http://localhost:8001/healthz   (db: up, redis: up)
- Admin panel: http://localhost:8001/admin     → log in with admin@capimax.com / Admin123!secure

If you ever need to recreate things:
```cmd
alembic upgrade head
python scripts\seed_properties.py
python scripts\seed_admin.py <email>      REM grant admin to an already-registered user
```

## Frontend (Vite) — cmd, from `E:\Work\capimax-propshare`
```cmd
npm run dev
```
- App runs on **http://localhost:8081** (pinned in `vite.config.ts`, `strictPort: true`).
- `.env.local` set to `VITE_API_BASE_URL=http://localhost:8001`.
- Backend CORS `FRONTEND_ORIGIN=http://localhost:8081`, so cookies + API calls work from this origin.

## Admin panel — what you can do there
- **Properties**: select a row → **Approve (→ active)** / **Reject (→ draft)** / **Close**
  (these call the audited moderation service; approving makes a property show in the marketplace).
- **Users / User Roles**: inspect users, grant/revoke roles.
- **KYC Verification**: inspect / override provider-flagged cases.
- **Investments / Wallets / Transactions**: READ-ONLY (money tables never hand-edited).

## Run the tests (backend) — from `backend`
```cmd
.venv\Scripts\activate
python -m pytest -q
```
- **58 tests.** The DB-backed ones build a throwaway `capimax_test` database automatically
  from the migrations (needs Postgres on 5433 reachable). If Postgres is down they SKIP
  cleanly and the 46 DB-free unit tests still run.
- Static gates: `ruff check app`, `black --check app`, `mypy app`.

## Phase 4 — deposits (Stripe + NOWPayments), local testing
Wallet is at the investor dashboard → Wallet → **Add Funds**. Deposits are **KYC-gated**
(verify the user first), credited only by a signed provider webhook.

Add to `backend\.env` (deposits 503 until set):
```dotenv
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...        # from `stripe listen` for local
NOWPAYMENTS_API_KEY=...
NOWPAYMENTS_IPN_SECRET=...
NOWPAYMENTS_SANDBOX=true
WALLET_CURRENCY=USD
```
- **Stripe (fully local):** `stripe listen --forward-to localhost:8001/api/v1/payments/webhooks/stripe`
  → it prints the `whsec_...` to put in `.env`. Deposit with a Stripe test card; the
  `checkout.session.completed` webhook credits the wallet.
- **NOWPayments:** cannot POST to localhost — use a tunnel (ngrok/cloudflared) to
  `localhost:8001` for the IPN, or test on the VPS. Our DB-backed tests simulate signed
  IPNs, so the logic is proven without the network.
- Migration: run `alembic upgrade head` (applies `0005`) before testing.

## What's testable locally vs. needs a public domain / credentials
- **Testable now:** email/password auth, multi-role + server-enforced role switching,
  property create→submit→**admin approve (via /admin)**→marketplace + detail, KYC gate
  behaviour, the admin panel.
- **Email verify/reset:** link is printed to the backend console (EMAIL_PROVIDER=console).
- **Needs creds/public URL (honest 503 locally):** Sumsub KYC verification callback,
  Google/Apple OAuth, Stripe/OnePayments (Phase 4+), property image upload (storage seam).
