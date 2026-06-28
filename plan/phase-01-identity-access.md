# Phase 1 — Identity, Auth & Access Control ⚠️ (security-critical)

**Size:** Large → **Larger under Scenario B (≈3–4 weeks)**. It re-implements auth (a divergence from [BACKEND_SPEC.md](../BACKEND_SPEC.md) §3.2, mandated by the owner), migrates identity off `auth.users`, builds the **multi-role / active-role** system (D12), *and* hardens the frontend. It cannot be safely split smaller: the auth swap, the route guards, and the role-switcher lockdown must land together or the app is left in a state where real auth exists but anyone can still self-assign a role.

> ⚠️ **Security scheduling (explicit, per the task constraint):** the visible role-switcher dropdown ([AppSidebar.tsx:369](../src/components/layout/AppSidebar.tsx:369)) and the total absence of route guards ([App.tsx:72-106](../src/App.tsx:72)) are harmless **only while no real data is wired**. The moment this phase connects real auth and roles, they become live privilege-escalation vulnerabilities. Therefore **de-fanging the role-switcher and adding real route/role guards are in-scope for Phase 1**, not a later cleanup. Phase 1 does not pass its test gate until both are done.
>
> **Scenario B nuance (D12):** the dropdown is **repurposed, not deleted.** Its insecure behavior — client-side `setUserRole` letting anyone become any role — is removed entirely. In its place it (a) shows **only the roles the user is authorized for** (from the backend), (b) calls a backend **switch-active-role** endpoint, and (c) the backend **rejects any switch to a role outside the authorized set**, even if the request is tampered with. Security lives in the backend, not in hiding the control.

## Goal
Replace Supabase client-side auth with a Python-owned identity + **multi-role/active-role RBAC** system (Scenario B), migrate the schema's identity ownership off `auth.users`, wire the real login/profile/settings screens to it, and lock down the frontend (route guards + server-enforced role switching).

## Testable outcome ("done when…")
- A user registers and logs in (email/password **and** Google/Apple OAuth) against the **backend**, receiving an app JWT carrying `roles` (authorized set) + `active_role`; `GET /auth/me` returns profile + authorized roles + active role + KYC status + wallet summary.
- A **guest** (no session) navigating to `/dashboard`, `/owner-dashboard`, `/admin`, etc. is redirected to `/auth` (route guards enforce it). Guest is the unauthenticated state, not a role.
- A **multi-role** user can **switch active role only among their authorized roles**; the sidebar shows only those roles; the per-role menu changes with the active role. A tampered switch request to an unauthorized role is rejected `403 ROLE_NOT_AUTHORIZED` by the backend.
- There is **no client path to grant oneself an unauthorized role**; the old "assume any role" behavior is gone.
- Role acquisition works per the sub-decision: **self-serve** add of `investor`/`owner`; `broker`/`liquidity_provider`/`admin` go through an **admin-approved request**; `admin` is never self-grantable.
- Account Settings (profile, avatar, password) and the KYC-status card read/write through the backend, not `supabase-js`.

## Dependencies
Phase 0.

## Backend work
- **Auth service & endpoints:**
  - `POST /auth/register` → create `users` row (Argon2 hash) + provision `profiles`/`wallets`/`kyc_verifications` in one tx (replaces the `handle_new_user` trigger); captures optional **referral code** (for Phase 11); sends a **verification email** (see comms below). Request: email, password, full_name, phone, optional referral_code. Errors: `409 EMAIL_EXISTS`, `422` validation.
  - `POST /auth/login` → email+password → in-memory **access JWT** + sets **httpOnly refresh cookie**. Errors: `401 INVALID_CREDENTIALS`.
  - `POST /auth/oauth/{google|apple}` → Authlib exchange → find/create user → tokens (mirrors [Auth.tsx:159](../src/pages/Auth.tsx:159),[193](../src/pages/Auth.tsx:193)).
  - `POST /auth/refresh` (reads the httpOnly cookie, issues a fresh short-TTL access token), `POST /auth/logout` (clears the cookie + invalidates the refresh token).
  - `POST /auth/password/forgot` + `POST /auth/password/reset` (token-based) and `POST /auth/verify-email` → **fixes the dead "Forgot password?" link** ([Auth.tsx:291](../src/pages/Auth.tsx:291)). These are the **only** comms wired in Phase 1.
  - `GET /auth/me` → bootstrap payload (profile, authorized roles, active role, kyc_status, wallet summary).
- **Token model (owner-mandated):** short-TTL **access token kept in memory** (never `localStorage`) + **httpOnly/Secure/SameSite refresh cookie**. Refresh tokens are revocable (logout / role-revoke).
- **Multi-role / active-role (Scenario B, D12):**
  - JWT carries `sub`, `roles` (authorized set from `user_roles`), `active_role` (∈ `roles`). Default `active_role` persisted as `users.active_role`.
  - `GET /auth/roles` — the caller's authorized roles (drives the repurposed sidebar switcher).
  - `POST /auth/switch-role {role}` — re-mint JWT with new `active_role` **iff `role ∈ roles`**, else `403 ROLE_NOT_AUTHORIZED`. Audit-logged.
  - `POST /roles/request {role}` — **self-serve** for `investor`/`owner` (insert into `user_roles` immediately); for `broker`/`liquidity_provider` create a `role_grant_requests` row (`pending`); `admin` is rejected (never self-serve).
- **RBAC dependencies** (`api/deps.py`): `current_user` (loads authorized roles + active role), `require_role(...)` (passes only if role is the active role AND authorized), **`require_active_role_db(...)` which re-queries `user_roles` at action time** (owner-mandated — used by every money/privileged endpoint so a revoked role can't act within a still-valid token's TTL), `require_kyc_verified`, `require_owner(...)` per [01-architecture.md](01-architecture.md) §4. Phase 1 ships the dependency + a unit test; the money endpoints that consume it arrive in Phases 4–11.
- **Comms (minimal, Phase 1 only):** a thin `email.send()` via **Resend or SMTP** wired solely for **email verification + password reset**. The full notifications/comms system stays Phase 12; login is not shippable (even for test) without password reset, so this slice lands here.
- **Profiles:** `GET/PATCH /profiles/me`, `POST /profiles/me/avatar` (→ app storage, signed URL). Replaces [AccountSettings.tsx:105](../src/pages/AccountSettings.tsx:105),[164](../src/pages/AccountSettings.tsx:164),[214](../src/pages/AccountSettings.tsx:214).
- **Admin role management:** `GET /admin/users`, `POST /admin/users/{id}/roles` (direct grant/revoke), `GET /admin/role-requests`, `POST /admin/role-requests/{id}/approve|reject` (the approval path for `broker`/`liquidity_provider`/`admin`). Audit-logged. `scripts/seed_admin.py` seeds the **first** admin; thereafter **an existing admin can grant `admin` to others** — `admin` is **never self-serve**. Revoking a role deletes the `user_roles` row and revokes the user's refresh tokens so the change takes effect immediately (works with the action-time DB re-check above).
- **Notification prefs:** add a prefs store so the Settings toggles persist (currently fake — [AccountSettings.tsx:240](../src/pages/AccountSettings.tsx:240)). Minimal `GET/PATCH /profiles/me/notification-prefs`.
- **Storage seam (partial):** avatar + KYC document paths move to the app storage interface now; full document storage in Phase 12.

## DB tables/columns touched / new migrations
- New migration: **`users`** table (app-owned identity: id, email, password_hash, oauth fields, email_verified, active_role, referred_by, created_at) and **re-point FKs** previously on `auth.users` (`profiles.id`, `user_roles.user_id`, `kyc_verifications.user_id`, `properties.owner_id`, `investments.user_id`, `wallets.user_id`, `transactions.user_id`, `notifications.user_id`, `documents.user_id`, `secondary_listings.seller_id`, `family_groups.owner_id`, `family_members.user_id`, `family_transfers`/`family_return_allocations` indirect). **Clean cutover (owner-confirmed): `auth.users` is empty except test accounts → no data migration; the FK target is repointed and the Supabase `auth` schema dependency is dropped.** New migration also adds a **`refresh_tokens`** table (revocable sessions for the httpOnly-cookie model).
- Drop/replace the `handle_new_user` trigger with app-level provisioning.
- New migration: notification-preferences column/table; `referred_by` column on `users` (referral capture); **`active_role` column on `users`** (default active role); **`role_grant_requests`** table (`id, user_id, requested_role, status[pending|approved|rejected], decided_by, decided_at, created_at`) for admin-approved roles.
- `user_roles` is **already many-to-many** (`UNIQUE(user_id, role)`) — no change needed to hold multiple roles; we simply stop reading only `roles[0]`.
- Reads: `user_roles`, `profiles`, `kyc_verifications`, `wallets`.

## Frontend wiring
- **Auth client swap:** replace `supabase.auth.*` usage in [Auth.tsx](../src/pages/Auth.tsx), [AuthContext.tsx](../src/contexts/AuthContext.tsx), [AccountSettings.tsx](../src/pages/AccountSettings.tsx) with calls to the backend; attach the app JWT as `Authorization: Bearer` on all API calls.
- **AuthContext (Scenario B):** change the shape from a single `userRole` to `authorizedRoles: UserRole[]` + `activeRole: UserRole` + `isAuthenticated`, all sourced from `/auth/me`. **Replace the public `setUserRole`** ([AuthContext.tsx:11](../src/contexts/AuthContext.tsx:11),[93](../src/contexts/AuthContext.tsx:93)) — and the current `roles[0]` single-role assumption ([AuthContext.tsx:41](../src/contexts/AuthContext.tsx:41),[66](../src/contexts/AuthContext.tsx:66)) — with a `switchActiveRole(role)` that calls `POST /auth/switch-role` and refreshes the JWT; it can only succeed for an authorized role (backend-enforced).
- **Repurpose the role-switcher** `<Select onValueChange={setUserRole}>` ([AppSidebar.tsx:369](../src/components/layout/AppSidebar.tsx:369)): populate options from `authorizedRoles` (from `/auth/roles`), call `switchActiveRole` on change, and render the per-role sidebar menu from `activeRole`. `Guest` is shown only when unauthenticated and is not a switch target. The insecure "assume any role" path is removed.
- **Add route guards:** introduce `<ProtectedRoute requiredRole?>` and wrap the gated routes in [App.tsx:72-106](../src/App.tsx:72) (dashboards, kyc, settings, admin). Guards check the **active role** against `requiredRole`. Public routes (marketing/legal/marketplace/auth) stay open.
- Fix dead auth UI: "Forgot password?" ([Auth.tsx:291](../src/pages/Auth.tsx:291)); persist notification toggles ([AccountSettings.tsx:240](../src/pages/AccountSettings.tsx:240)); 2FA/sessions buttons ([AccountSettings.tsx:540](../src/pages/AccountSettings.tsx:540),[551](../src/pages/AccountSettings.tsx:551)) — either wire minimally or mark explicitly deferred (no fake "Enable").
- Retire mock: the hardcoded greeting "Ahmed" ([InvestorDashboard.tsx:62](../src/pages/InvestorDashboard.tsx:62)) → real profile name.

## External integrations
- OAuth providers (Google, Apple) via Authlib — requires client IDs/secrets configured.
- App storage (S3-compatible) for avatars/KYC paths.

## Test plan
- **Success:** register → login (password + OAuth) → `/auth/me` returns correct authorized roles + active role + kyc/wallet; profile + password update persist.
- **Multi-role (Scenario B):** a user with `{investor, owner}` can switch active role between the two and the sidebar menu + route access change accordingly; self-serve `POST /roles/request investor|owner` succeeds immediately; `broker`/`liquidity_provider` requests create a pending `role_grant_requests` row and only appear after an admin approves; `admin` self-request is rejected.
- **Failure / security (the lockdown gate):** guest hitting a guarded route → redirected to `/auth`; **`POST /auth/switch-role` to a role NOT in the authorized set → `403 ROLE_NOT_AUTHORIZED`** even with a tampered/crafted request (server-enforced, not UI-hidden); non-admin → `403` approving role requests; expired/forged JWT → `401`; duplicate email → `409`; a JWT whose `active_role ∉ roles` is rejected.
- **Revoked-role-within-TTL (owner-mandated):** issue a token with `active_role=broker`, admin revokes `broker`, then a call to a `require_active_role_db` endpoint with the *still-valid* token → **`403`** (DB re-check beats the token). Confirms a revoked role cannot act inside the access-token TTL.
- **Token storage:** access token is returned in the body/memory only and **never** set in a JS-readable cookie/localStorage; the refresh token is an **httpOnly, Secure, SameSite** cookie; `/auth/refresh` works from the cookie; `/auth/logout` invalidates it (subsequent refresh → `401`).
- **Email flows:** verification + password-reset emails send (sandbox) and their tokens are single-use and time-limited.
- **Migration:** FK re-point migration applies cleanly; provisioning creates profile+wallet+kyc atomically on register; failure mid-provision rolls back (no orphan user).

## Risks / watch-outs
- **Identity migration** touches many FKs; do it as one reviewed migration with a rollback. **Owner-confirmed clean cutover** (no real users) — but the test accounts in `auth.users` will be dropped; re-create them through the new `/auth/register` after cutover.
- **OAuth config the owner must provide (flagged early so it doesn't block the build):**
  - **Google:** OAuth 2.0 Client ID + Client Secret; **Authorized redirect URI(s)** for the backend callback (e.g. `https://<api-host>/api/v1/auth/oauth/google/callback`) per environment. *Needed before the Google login path is testable — mid-Phase-1.*
  - **Apple (the long-pole):** Services ID (client_id), Team ID, Key ID, and the **.p8 private key**; the **Return URL** registered on the Services ID; Apple's domain-verification file if required. *Apple's setup lead time is the risk — please start provisioning at Phase 1 kickoff; the email/password + Google paths can ship first if Apple slips.*
  - **Email (Resend or SMTP):** API key / SMTP creds + a verified sender domain — needed for verification/reset emails (early Phase 1).
- **Active-role enforcement is the security crux:** every protected endpoint must check the active role *server-side* against the authorized set; never trust the client's claimed role. The repurposed dropdown is a convenience, not a gate. This is the exact vulnerability the audit flagged ([AppSidebar.tsx:369](../src/components/layout/AppSidebar.tsx:369)) — its removal must be verified by the tamper test, not by confirming the UI looks right.
- **OAuth parity:** Apple sign-in setup (keys, return URLs) is fiddly; budget time. The current OAuth goes through Lovable's wrapper ([src/integrations/lovable/index.ts](../src/integrations/lovable/index.ts)) — that dependency is removed.
- **Active-role on JWT vs. statelessness:** switching role re-mints the token; ensure old tokens with a stale `active_role` aren't honored beyond their short expiry, and that `active_role ∉ roles` (e.g. after an admin revokes a role) is rejected at verification time.
- **Don't leave a fake control:** every auth/settings button must be real or explicitly disabled — no new fake-success (the audit's central complaint).
- Token storage/refresh in the SPA must be secure (avoid long-lived tokens in localStorage where possible).
