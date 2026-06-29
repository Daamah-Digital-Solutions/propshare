# CapiMax PropShare — VPS Deployment Runbook (DevOps, over SSH)

A top-to-bottom runbook for a **fresh Ubuntu VPS**. Execute **one stage at a time** and
confirm each stage's **✅ Verify** gate before moving on — this is a financial production
server; do **not** run everything at once.

**Secrets policy:** every secret (DB password, `JWT_SECRET`, `CRON_SECRET`, all provider
keys) is generated/typed **by you directly on the server** into `backend/.env`. Never paste
a real secret into chat or send it to anyone. This runbook only ever shows **placeholders**.

**Provider keys + live-verification details:** see `plan/DEPLOYMENT_CHECKLIST.md` (§1 for
every provider's exact env-var names + webhook URLs, §5 for the live-verification steps).
This runbook does not duplicate them.

---

## Conventions

- `example.com` → the owner's real domain. `<VPS_IP>` → the server's public IP.
- API base = `https://api.example.com`; SPA base = `https://app.example.com` (see Decision B).
- Lines marked `>>> EDIT <<<` need a real value before you run them.
- Assumes **Ubuntu 24.04 LTS** (ships Python 3.12 + PostgreSQL 16 natively, matching the app's
  pinned runtime). On 22.04 you'd add the deadsnakes PPA for 3.12 and the PGDG repo for PG16 —
  prefer 24.04 to avoid that.

---

## Stage 0 — Decisions & prerequisites (read before touching the server)

Three things must be settled first. **A and B block the deploy.**

### Decision A — How does the code get onto the server? (REQUIRED — no remote exists yet)
The repository currently has **no git remote configured** and the canonical branch is **`master`**
(there is no `main`). You cannot `git clone` until the owner publishes it. Pick one:

1. **Publish to a private Git host (recommended).** Owner creates a private repo on
   GitHub/GitLab, adds it as `origin`, and pushes. You then clone over SSH with a deploy key.
   This makes future deploys a simple `git pull`.
2. **`git bundle` transfer (no host).** Owner runs locally:
   `git bundle create capimax.bundle --all`, copies it up with `scp`, and you
   `git clone capimax.bundle capimax`. Re-bundle for each future deploy.
3. **`rsync` the working tree (last resort).** Loses git history; harder to update. Not advised.

### Decision B — Branch to deploy + subdomain scheme
- **Branch:** all the "build-everything-real" work (groups 2–5: storage, payment methods,
  estate, gifting) lives on **`build/storage-payments-estate`** — **8 commits ahead of
  `master`**, in a **linear (fast-forward) line**. `master` is still at the pre-build baseline
  `c804e90` and is **NOT deployable** (missing those features + migrations 0015–0019).
  **Recommended:** fast-forward `master` to the build branch, tag a release, deploy `master`
  (clean canonical default). The owner runs this **once**, locally or wherever `origin` lives,
  before you clone:
  ```bash
  git checkout master
  git merge --ff-only build/storage-payments-estate   # linear FF — no merge commit
  git tag -a v1.0.0 -m "CapiMax PropShare v1.0.0 (groups 0–5 complete)"
  git push origin master --tags                        # if using Decision A.1
  ```
  *(Alternative: deploy `build/storage-payments-estate` directly — same code, just a
  non-default branch name. Either way the deployed tip must be commit `d3d0250` or later.)*
- **Subdomains:** this runbook uses `api.example.com` (backend) + `app.example.com` (SPA),
  sharing the parent `example.com`. That lets the refresh-token cookie work across both via
  `COOKIE_DOMAIN=.example.com`. If you instead serve the SPA at the apex `example.com`, adjust
  `FRONTEND_ORIGIN`, `APP_BASE_URL`, `COOKIE_DOMAIN`, and the nginx `server_name`s accordingly.

### Decision C — Provider rollout is LATER (Stage 7)
Deploy the core app with **no provider keys** first; everything degrades honestly (clear 503 /
disabled UI). Add providers **one at a time** afterwards (Stage 7), starting with Stripe.

### Prerequisites
- Root or sudo SSH access to the fresh VPS.
- DNS control for `example.com` (you'll add A records in Stage 4).
- The code reachable per Decision A; the deploy point chosen per Decision B.

---

## Stage 1 — Server hardening (do this FIRST)

> ⚠️ **Do not lock yourself out.** Create the user + install the SSH key and **verify login in
> a second terminal** *before* disabling password/root login.

```bash
# --- 1.1 As root: system update + a non-root sudo user ---
apt update && apt -y upgrade
adduser deploy                      # >>> EDIT <<< set a strong password when prompted
usermod -aG sudo deploy

# --- 1.2 Install the SSH public key for 'deploy' ---
# From YOUR laptop (not the server), copy your PUBLIC key up:
#   ssh-copy-id deploy@<VPS_IP>
# (or paste the key into /home/deploy/.ssh/authorized_keys on the server)
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
# verify the key file once it's there:
ls -l /home/deploy/.ssh/authorized_keys
```

**🔑 In a SECOND terminal, confirm key login works BEFORE continuing:**
`ssh deploy@<VPS_IP>` → you get a shell **without** a password prompt. Keep that session open.

```bash
# --- 1.3 Harden sshd: key-only, no root login (run as root/sudo) ---
sudo sed -i \
  -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
  -e 's/^#\?PermitRootLogin.*/PermitRootLogin no/' \
  -e 's/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' \
  /etc/ssh/sshd_config
# Ubuntu 24.04 may carry a cloud-init drop-in that re-enables passwords — neutralize it:
sudo find /etc/ssh/sshd_config.d -name '*.conf' -exec \
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' {} +
sudo systemctl restart ssh

# --- 1.4 Firewall: SSH + HTTP + HTTPS only ---
sudo apt -y install ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# --- 1.5 fail2ban (brute-force protection for sshd) ---
sudo apt -y install fail2ban
sudo systemctl enable --now fail2ban

# --- 1.6 Unattended security upgrades ---
sudo apt -y install unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades
```

**✅ Verify before continuing:**
```bash
sudo sshd -T | grep -Ei 'passwordauthentication|permitrootlogin'  # both = no
sudo ufw status verbose            # active; 22/OpenSSH, 80, 443 allowed; default deny incoming
sudo systemctl is-active fail2ban  # active
sudo fail2ban-client status sshd   # the sshd jail is running
systemctl is-enabled unattended-upgrades  # enabled
```
From a **fresh** terminal, confirm `ssh root@<VPS_IP>` is refused and `ssh deploy@<VPS_IP>`
works by key only. Do the rest of this runbook as `deploy`.

---

## Stage 2 — Base stack (Python 3.12, PostgreSQL 16, nginx, certbot, Node, build deps)

```bash
# --- 2.1 Packages ---
sudo apt update
sudo apt -y install \
  python3.12 python3.12-venv python3.12-dev \
  postgresql postgresql-contrib \
  nginx certbot python3-certbot-nginx \
  git build-essential libpq-dev curl

# --- 2.2 Node 20 LTS (for the frontend build) via NodeSource ---
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt -y install nodejs

# --- 2.3 PostgreSQL: dedicated DB + app user ---
# Generate a strong DB password and KEEP IT (you'll paste it into DATABASE_URL in Stage 3):
openssl rand -base64 24            # >>> EDIT <<< copy this value somewhere safe (server only)
sudo -u postgres psql <<'SQL'
CREATE USER capimax_app WITH PASSWORD 'PASTE_THE_GENERATED_PASSWORD_HERE';  -- >>> EDIT <<<
CREATE DATABASE capimax OWNER capimax_app;
SQL
```
> If the password contains URL-reserved characters (`@ : / ? # %`), URL-encode them in
> `DATABASE_URL`, or just regenerate one without them (`openssl rand -hex 24`).

**✅ Verify before continuing:**
```bash
python3.12 --version            # Python 3.12.x
node --version                  # v20.x
psql --version                  # psql ... 16.x
systemctl is-active postgresql nginx   # both active
# DB connectivity with the app user (enter the password):
psql "postgresql://capimax_app@localhost/capimax" -c '\conninfo'
```

---

## Stage 3 — App deploy (code, venv, dependencies, .env, migrations)

```bash
# --- 3.1 Lay out /opt/capimax and get the code (per Decision A) ---
sudo mkdir -p /opt/capimax
sudo chown deploy:deploy /opt/capimax
cd /opt/capimax
# Decision A.1 (git host):   git clone <REPO_SSH_URL> app
# Decision A.2 (bundle):     git clone /home/deploy/capimax.bundle app
cd /opt/capimax/app
# Deploy the chosen branch (Decision B). If you fast-forwarded master:
git checkout master
git log --oneline -1            # MUST be d3d0250 (or later) — the gifting/docs tip

# --- 3.2 Virtualenv + install the backend package ---
python3.12 -m venv /opt/capimax/venv
source /opt/capimax/venv/bin/activate
pip install --upgrade pip
pip install -e ./backend        # installs capimax-backend + gunicorn/uvicorn/alembic/psycopg/...
```

### 3.3 Create `backend/.env` (you fill in the real values)
Create `/opt/capimax/app/backend/.env`. **You (DevOps) set every value below.** The CORE block
is required for a production boot; the PROVIDERS block can stay blank for now — each unset
provider degrades to an honest 503 / disabled UI and is wired later in Stage 7
(`plan/DEPLOYMENT_CHECKLIST.md` §1 has each provider's exact keys).

```ini
# ===================== CORE (required for production) =====================
ENVIRONMENT=production
LOG_LEVEL=INFO

# 64+ random chars — generate on the server: `openssl rand -hex 48`
JWT_SECRET=>>> EDIT: paste a fresh `openssl rand -hex 48` <<<

# DB (Stage 2.3). asyncpg driver; URL-encode any reserved chars in the password.
DATABASE_URL=postgresql+asyncpg://capimax_app:>>> EDIT: DB password <<<@localhost:5432/capimax

# Cookies / CORS / links — HTTPS + the shared parent domain (Decision B).
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=.example.com                 # >>> EDIT <<< parent domain shared by api. & app.
FRONTEND_ORIGIN=https://app.example.com    # >>> EDIT <<< CORS allow-list (comma-separate if >1)
APP_BASE_URL=https://app.example.com       # >>> EDIT <<< used in email links + OAuth redirects

# Shared secret for the cron endpoints (Stage 6). Generate: `openssl rand -hex 32`
CRON_SECRET=>>> EDIT: paste a fresh `openssl rand -hex 32` <<<

# Redis is OPTIONAL (only for multi-worker shared rate-limit counters). Leave unset for a
# single/few-worker start; /healthz does NOT depend on it.
# REDIS_URL=redis://localhost:6379/0

# ----- Storage (documents / certificates / images / avatars — BUILT, Group 2) -----
# 'local' writes real files under STORAGE_DIR; put that on a persistent, backed-up path.
# Switch to 's3' (+ the S3_* vars in DEPLOYMENT_CHECKLIST §1.9) when you want object storage.
STORAGE_PROVIDER=local
STORAGE_DIR=/opt/capimax/storage           # created in 3.4; survives app redeploys
STORAGE_MAX_UPLOAD_MB=25

# ===================== PROVIDERS (leave blank now; fill in Stage 7) =====================
# Names below are authoritative; values + webhook URLs are in DEPLOYMENT_CHECKLIST §1.
# Until set, the related feature returns an honest 503 / shows disabled UI.
EMAIL_PROVIDER=console        # 'resend' or 'smtp' in prod (DEPLOYMENT_CHECKLIST §1.6)
# EMAIL_FROM=CapiMax <no-reply@example.com>
# RESEND_API_KEY=
# STRIPE_SECRET_KEY=
# STRIPE_WEBHOOK_SECRET=
# STRIPE_PUBLISHABLE_KEY=
# NOWPAYMENTS_API_KEY=
# NOWPAYMENTS_IPN_SECRET=
# NOWPAYMENTS_SANDBOX=false
# NOWPAYMENTS_EMAIL=
# NOWPAYMENTS_PASSWORD=
# SUMSUB_APP_TOKEN=
# SUMSUB_SECRET_KEY=
# SUMSUB_WEBHOOK_SECRET=
# SUMSUB_LEVEL_NAME=basic-kyc-level
# SUMSUB_BASE_URL=https://api.sumsub.com
# GOOGLE_CLIENT_ID=
# GOOGLE_CLIENT_SECRET=
# APPLE_CLIENT_ID=
# APPLE_TEAM_ID=
# APPLE_KEY_ID=
# APPLE_PRIVATE_KEY=
```
Lock the file down:
```bash
chmod 600 /opt/capimax/app/backend/.env
```

```bash
# --- 3.4 Persistent storage dir (for the 'local' storage provider) ---
mkdir -p /opt/capimax/storage      # matches STORAGE_DIR; back this up with the DB

# --- 3.5 Run migrations — MUST run from backend/ so .env loads ---
cd /opt/capimax/app/backend
alembic upgrade head
alembic current                    # MUST print revision 0019 (head)
```
> **Why `cd backend` matters:** pydantic loads `.env` from the **current working directory**.
> Running alembic (and later gunicorn) from `backend/` is required or `DATABASE_URL` won't be
> read. The systemd unit in Stage 4 enforces this via `WorkingDirectory`.

**✅ Verify before continuing:**
```bash
cd /opt/capimax/app/backend
alembic current | grep -q 0019 && echo "schema at head 0019 ✅" || echo "NOT at 0019 ❌"
# all 19 migrations' tables exist — spot-check the latest groups:
psql "postgresql://capimax_app@localhost/capimax" -c "\dt" | \
  grep -E 'scheduled_gifts|estate_beneficiaries|saved_payment_methods|developer_updates|property_milestones'
```
You should see all five tables listed (gifting / estate / payment-methods / comms / milestones).
**Do not create the admin yet** — `seed_admin.py` promotes an *existing* user, so it runs at the
end of Stage 4 after the API is up and you've registered the admin account.

---

## Stage 4 — Process (systemd) + web (nginx + DNS + TLS) + first admin

### 4.1 systemd service (gunicorn + uvicorn workers)
The gunicorn invocation matches `backend/Dockerfile`; it binds to **localhost** (nginx proxies
to it — port 8000 is never public) and trusts the local proxy's forwarded headers.

```bash
sudo tee /etc/systemd/system/capimax.service >/dev/null <<'UNIT'
[Unit]
Description=CapiMax PropShare API (gunicorn/uvicorn)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=deploy
Group=deploy
# WorkingDirectory MUST be backend/ so pydantic loads backend/.env
WorkingDirectory=/opt/capimax/app/backend
EnvironmentFile=/opt/capimax/app/backend/.env
ExecStart=/opt/capimax/venv/bin/gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --workers 2 \
  --forwarded-allow-ips=127.0.0.1 \
  --access-logfile - --error-logfile -
Restart=on-failure
RestartSec=3
# Hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now capimax.service
sudo systemctl status capimax.service --no-pager
```
> `--workers 2` matches the Dockerfile. Tune later toward `2 × CPU cores + 1` if needed; if you
> run more than ~2 workers and want shared rate-limit counters, provision Redis and set `REDIS_URL`.

**Local smoke test (before TLS/DNS):**
```bash
curl -s http://127.0.0.1:8000/healthz   # -> {"status":"ok", ... "database":"up" ...}
```

### 4.2 DNS
At the domain registrar / DNS provider, add **A records** → `<VPS_IP>`:
- `api.example.com  A  <VPS_IP>`
- `app.example.com  A  <VPS_IP>`

(Add matching `AAAA` records if the VPS has IPv6.) Verify they resolve before issuing certs:
```bash
dig +short api.example.com
dig +short app.example.com    # both must return <VPS_IP>
```

### 4.3 nginx (HTTP first; certbot adds TLS in 4.4)
```bash
sudo tee /etc/nginx/sites-available/capimax >/dev/null <<'NGINX'
# --- API: reverse proxy to gunicorn on localhost ---
server {
    listen 80;
    server_name api.example.com;          # >>> EDIT <<<

    # Document/avatar/property-image uploads can be up to 25 MB (STORAGE_MAX_UPLOAD_MB).
    client_max_body_size 30M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # app sees HTTPS -> correct links/cookies
    }
}

# --- SPA: serve the built frontend (dist/ from Stage 5) ---
server {
    listen 80;
    server_name app.example.com;          # >>> EDIT <<<
    root /opt/capimax/app/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;  # SPA history fallback
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/capimax /etc/nginx/sites-enabled/capimax
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 4.4 TLS (Let's Encrypt) + force HTTPS
```bash
sudo certbot --nginx -d api.example.com -d app.example.com   # >>> EDIT domains <<<
# Choose "redirect" so HTTP -> HTTPS is enforced. certbot installs a renewal timer.
sudo systemctl list-timers | grep certbot     # renewal timer present
```

### 4.5 Create the FIRST admin (now that the API is up)
`seed_admin.py` grants admin to an **existing** user, so register that user first:
```bash
# Register the admin account through the real API (use the owner's chosen admin email):
curl -s -X POST https://api.example.com/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":">>> EDIT strong pw <<<","full_name":"Admin"}'
# Promote it to admin (run from backend/ so .env loads):
cd /opt/capimax/app/backend
/opt/capimax/venv/bin/python scripts/seed_admin.py admin@example.com   # >>> EDIT email <<<
# -> "OK: admin@example.com is now admin (active_role=admin)."
```

**✅ Verify before continuing:**
```bash
curl -s https://api.example.com/healthz                 # 200, {"status":"ok","database":"up"}
curl -s -o /dev/null -w "%{http_code}\n" https://app.example.com/   # 200 (SPA shell)
# HTTP is redirected to HTTPS:
curl -s -o /dev/null -w "%{http_code}\n" http://api.example.com/healthz   # 301/308
```
Admin can log in at `https://api.example.com/admin` (SQLAdmin) with the seeded credentials.

---

## Stage 5 — Frontend build + serve

`VITE_*` vars are **baked in at build time** — set them before building. The SPA talks to the
API via `VITE_API_BASE_URL`. (No `VITE_STRIPE_*` is needed — card deposits use Stripe **hosted
checkout**, so no Stripe key ships in the SPA. The OAuth client IDs are only needed once you
wire Google/Apple in Stage 7; you can rebuild then.)

```bash
cd /opt/capimax/app
npm ci

# Build-time env (a .env.production file Vite reads, in the repo root):
cat > .env.production <<'ENVP'
VITE_API_BASE_URL=https://api.example.com
# Set these when you enable OAuth (Stage 7), then rebuild:
# VITE_GOOGLE_CLIENT_ID=
# VITE_APPLE_CLIENT_ID=
ENVP
# >>> EDIT the API URL above <<<

npm run build        # outputs to /opt/capimax/app/dist (nginx 'app.' root already points here)
```

**✅ Verify before continuing:**
- Open `https://app.example.com` in a browser → the app loads (no white screen).
- Register/login a test investor → it succeeds and the dashboard loads → confirms the SPA is
  reaching the API and the refresh cookie works across the subdomains.
- In dev tools → Network, API calls go to `https://api.example.com` and return 200.

> **Rebuilds:** after a `git pull`, re-run `npm ci && npm run build` (frontend) and
> `pip install -e ./backend && cd backend && alembic upgrade head` + `sudo systemctl restart
> capimax` (backend). Whenever you change a `VITE_*` value, you must rebuild the frontend.

---

## Stage 6 — Cron jobs (7) — system cron → admin endpoints

All 7 are idempotent and authenticate with the `X-Cron-Secret: $CRON_SECRET` header (the value
you put in `.env` at 3.3). Install them in the `deploy` user's crontab:

```bash
crontab -e
```
Paste (replace `SECRET` with the **real** `CRON_SECRET`, and the API host):
```cron
# m h  command   (CapiMax cron — SECRET = the CRON_SECRET from backend/.env)
*/2  * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/withdrawals/execute
*/15 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/withdrawals/reconcile
*/5  * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/investments/maintenance/expire-reservations
*    * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/notifications/dispatch-emails
*/10 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/liquidity/expire-requests
*/30 * * * *  curl -fsS -X POST -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/gifts/run-due
30 2 * * *    curl -fsS      -H "X-Cron-Secret: SECRET" https://api.example.com/api/v1/admin/reconciliation
```
(Cadence is adjustable. The last one is a nightly **GET**; the rest are POSTs.)

**✅ Verify before continuing — fire one manually and expect HTTP 200:**
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "X-Cron-Secret: >>> EDIT: real CRON_SECRET <<<" \
  https://api.example.com/api/v1/admin/gifts/run-due        # -> 200
# A wrong/missing secret must be rejected:
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "X-Cron-Secret: wrong" https://api.example.com/api/v1/admin/gifts/run-due   # -> 401
```
The 7 endpoints + their purpose are documented in `plan/DEPLOYMENT_CHECKLIST.md` §4.

---

## Stage 7 — Providers + live verification (LATER — one at a time)

Now wire external providers **incrementally**. For **each** provider:
1. Add its keys to `backend/.env` (exact names + webhook URLs: `DEPLOYMENT_CHECKLIST.md` §1).
2. `sudo systemctl restart capimax` (env reloads).
3. Run **that provider's** live-verification step (`DEPLOYMENT_CHECKLIST.md` §5).
4. Run reconciliation and **confirm zero drift** before adding the next provider:
   ```bash
   cd /opt/capimax/app/backend
   /opt/capimax/venv/bin/python scripts/reconcile.py     # expect ok: true, zero drift
   ```

**Recommended order** (start with the one already locally tested):
1. **Stripe deposits** (§1.1) — register the webhook `…/api/v1/payments/webhooks/stripe`, then
   §5.1: deposit → hosted checkout → wallet credits via the webhook → check `/admin → Transactions`.
2. **Stripe Connect payouts** (§1.2 / §5.3) → 3. **NOWPayments deposits** (§1.3 / §5.2) →
   4. **NOWPayments payouts** (§1.4 / §5.4) → 5. **Sumsub KYC** (§1.5 / §5.5) →
   6. **Resend email** (§1.6 / §5.6 — flip `EMAIL_PROVIDER=resend`) →
   7. **Google + Apple OAuth** (§1.7–1.8 / §5.7 — set the `VITE_*` IDs and **rebuild the
      frontend**, Stage 5).
8. **Gift executor** end-to-end (§5.9): schedule a gift due today → confirm units reserved /
   cash escrowed → fire `…/admin/gifts/run-due` → real transfer/credit + the one-time 7-day reminder.
9. **Final reconciliation** (§5.10): `scripts/reconcile.py` → `ok: true`, zero drift everywhere.
10. **Compliance copy** (§5.11): confirm the marketing/legal claims (AUM / owners / "Regulated by
    FSA" / "Up to 12% APY") are substantiated **before public launch** — owner's responsibility.

> **PASSIVE LP pool stays hard-locked** (`lp_passive_enabled=false`) — do not enable it; its
> economics/licensing are an open owner decision (`DEPLOYMENT_CHECKLIST.md` Notes).

---

## Appendix — Day-2 operations

- **Logs:** `journalctl -u capimax -f` (app); `sudo tail -f /var/log/nginx/{access,error}.log`.
- **Restart / status:** `sudo systemctl restart capimax`; `systemctl status capimax`.
- **Deploy an update:**
  ```bash
  cd /opt/capimax/app && git pull
  source /opt/capimax/venv/bin/activate && pip install -e ./backend
  cd backend && alembic upgrade head        # confirm `alembic current` advanced
  sudo systemctl restart capimax
  cd /opt/capimax/app && npm ci && npm run build   # if the frontend changed / VITE_* changed
  ```
- **Database backups (set up before real money flows):** a nightly `pg_dump capimax` to
  off-server storage, plus back up `STORAGE_DIR` (uploaded documents/certificates) alongside it.
- **Secrets:** rotating `JWT_SECRET` invalidates all sessions (users re-login). `CRON_SECRET`
  rotation must be updated in both `.env` and the crontab.
