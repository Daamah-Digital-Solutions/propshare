# Phase 12 — Notifications + Email (DESIGN, for sign-off)

**Status:** DESIGN — awaiting owner sign-off. No code until approved.
**Scope:** in-app notifications (read path = core deliverable) + email for a limited financial/security event set. **Documents fully deferred** to a standalone phase (mocks honest-disabled, not deleted). No SMS, no push.

---

## 0. Read-back of the two most-likely-to-be-mis-built points

- **(a) Email is limited to the financial/security event set — NOT every event emails.** Every event still writes an **in-app** row. Only these ALSO email: **KYC decision, investment confirmed, investment refunded, return distributed, withdrawal settled, family invite, broker commission.** In-app-ONLY (no email): KYC started, deposit credited, secondary sale, LP exit fill, family member added. The email channel is opt-in *per event at the call site* (`email_category=…`), so adding `email=True` to the wrong event is impossible by omission — a call without an email category never emails.
- **(b) Documents are deferred but their mocks are HONEST-DISABLED, not deleted.** `PropertyDocuments` (8 fake docs), `InvestmentCertificates`, and the dead Download buttons degrade to "Documents not available yet" — the components stay in the tree (DELETE NOTHING; silent removal would hide that the feature was expected). Only the `/documents` **sidebar link** is removed (a link implying a feature that doesn't exist = half-dead nav).

---

## 1. The core problem & the transactional-outbox decision

`notify()` is wired into 11 points but **write-only with no read path**, and most calls happen **inside money transactions** (distribution, withdrawal, investment, secondary, LP, family). Two consequences shape the design:

1. **Read path is the primary deliverable** — a `GET /notifications` (+ unread count + mark-read), then wire the bell + a real page.
2. **Email must NOT be sent inside a money tx.** A blocking `httpx` call to Resend inside `run_distribution` could stall or (on error) roll back a financial transaction. So email uses a **transactional outbox**:
   - Inside the money tx, an email-eligible event writes the in-app `notifications` row **and** an `email_outbox` row (`pending`) — both committed atomically with the money move (or both rolled back).
   - A separate **drainer** (`email_service.dispatch_pending`, cron-able, `SKIP LOCKED`) sends pending rows via the existing `email_provider` seam **outside** any money tx, with retry + idempotency. Console locally; **Resend verified live on the VPS** (already recorded as a VPS-gated item).
   - Bonus: the outbox drainer is one of the Phase-13 crons.

---

## 2. Schema (migration `0013_phase12_notifications`)

No enum changes. `notifications` table already exists (`user_id, type, title, message, read, created_at`) — add an index; add two tables.

```
-- feed + unread-count performance
CREATE INDEX notifications_user_read_idx ON notifications (user_id, read, created_at DESC);

-- per-user email preferences (in-app is always on; only channels we actually send)
CREATE TABLE notification_preferences (
  user_id                  uuid PK REFERENCES users(id) ON DELETE CASCADE,
  email_investment_updates boolean NOT NULL DEFAULT true,
  email_returns            boolean NOT NULL DEFAULT true,
  email_security_alerts    boolean NOT NULL DEFAULT true,
  email_new_properties     boolean NOT NULL DEFAULT true,   -- reserved (marketing); no v1 emitter
  created_at, updated_at
);

-- transactional email outbox (written in-tx, drained out-of-tx)
CREATE TABLE email_outbox (
  id          uuid PK,
  user_id     uuid NULL REFERENCES users(id) ON DELETE SET NULL,  -- NULL for non-user invitees
  to_email    text NOT NULL,
  subject     text NOT NULL,
  body        text NOT NULL,
  category    text NOT NULL,            -- investment_updates | returns | security | invite
  status      text NOT NULL DEFAULT 'pending',   -- pending | sent | failed
  attempts    int  NOT NULL DEFAULT 0,
  last_error  text NULL,
  created_at  timestamptz DEFAULT now(),
  sent_at     timestamptz NULL
);
CREATE INDEX email_outbox_status_idx ON email_outbox (status, created_at);
```

No `platform_settings` keys (email provider stays in env/config: `EMAIL_PROVIDER`/`RESEND_API_KEY`).

---

## 3. Dispatch seam (extend `notification_service.notify`)

Backward-compatible — existing in-app-only callers are unchanged:

```
notify(session, *, user_id, type, title, message,
       email_category: str | None = None,   # set → email-eligible
       email_to: str | None = None,          # override recipient (invitee), else user's email
       force_email: bool = False,            # bypass prefs (invitations)
       email_subject: str | None = None, email_body: str | None = None)
```
Logic (all inside the caller's tx):
1. Always insert the in-app `notifications` row (today's behavior).
2. If `email_category` is set: resolve recipient (`email_to` or the user's email); if `force_email` **or** the user's `notification_preferences[email_category]` is on → insert an `email_outbox` row (`pending`, subject=`email_subject or title`, body=`email_body or message`). Missing prefs row ⇒ treated as default-on.

**Call-site changes (the event matrix):**

| Event | Service call | email_category |
|---|---|---|
| KYC decision | kyc_service | `security` |
| Investment confirmed / refunded | investment_service | `investment_updates` |
| Return distributed | distribution_service | `returns` |
| Withdrawal settled | withdrawal_service (completed) | `security` |
| **Broker commission** *(new notify point)* | broker_service.accrue_commission | `investment_updates` |
| **Family invite** *(new email; invitee often non-user)* | family_service.add_member (when pending/non-user) | `invite` + `force_email`, `email_to`=invitee |
| KYC started, deposit credited, secondary sale, LP fill, family member-added | unchanged | *(none — in-app only)* |

The two investigation gaps are closed: **broker commission** gets a notify call; **family invite** sends a real email to the invitee (an in-app row would reach no one).

---

## 4. Read & preferences API (`routes/notifications.py`, authenticated; own rows only)

- `GET /api/v1/notifications?limit&offset&unread_only` → `{ items, total, unread_count }`
- `GET /api/v1/notifications/unread-count` → `{ count }` (cheap; the bell badge)
- `POST /api/v1/notifications/{id}/read` → mark one read (404 if not the caller's)
- `POST /api/v1/notifications/read-all` → mark all the caller's read
- `GET /api/v1/notifications/preferences` → `{ email_investment_updates, email_returns, email_security_alerts, email_new_properties }`
- `PUT /api/v1/notifications/preferences` → update **email** prefs only (creates the row on first write). SMS/push are **not accepted** (they don't exist).

Admin: cron-able `POST /api/v1/admin/notifications/dispatch-emails` (drains the outbox; `SKIP LOCKED`, retry, idempotent) + read-only SQLAdmin views for `EmailOutbox` and `NotificationPreference`.

---

## 5. Email drainer (`email_service.dispatch_pending`)

`SELECT … FOR UPDATE SKIP LOCKED` over `email_outbox WHERE status='pending'` (capped batch) → for each: call `email_provider.send_email`; on success `status='sent', sent_at`; on failure `attempts += 1, last_error`, leave `pending` (or `failed` after N attempts). Idempotent (already-`sent` skipped), safe to run repeatedly. Console provider locally → logs; **Resend live on the VPS** (end-of-build verification). This is a Phase-13 cron target.

---

## 6. Frontend

- **`notificationApi`** in `api.ts`: `list`, `unreadCount`, `markRead`, `markAllRead`, `getPreferences`, `updatePreferences`.
- **Bell (`MainLayout`)** — kill the hardcoded `3`; show the live `unread-count` (badge hidden when 0); clicking navigates to `/notifications`. Invalidate the count after mark-read.
- **New `/notifications` page** (+ route in `App.tsx`) — live list, relative timestamps, unread styling, per-row "mark read" + "mark all read", honest empty state. Fixes the dead `/notifications` sidebar link for all roles.
- **`AccountSettings`** — wire the **4 email toggles** to `GET/PUT preferences` (real persistence; closes the logged "toggles don't persist" debt). **SMS + push toggles honest-disabled** ("Not available yet", `disabled`), not persisted — same pattern as Virtual Cards / PASSIVE.
- **Documents honest-disabled** — `PropertyDocuments` + `InvestmentCertificates` render a "Documents are not available yet" state; Download/View buttons `disabled`. Components kept (DELETE NOTHING). **Remove the `/documents` sidebar link** from all roles.

---

## 7. Test plan (DB-backed, acceptance bar)

1. **Read path** — list returns only the caller's rows, newest first; `unread_count` correct; auth required.
2. **Mark read** — one + all flip `read`; can't mark another user's row (404); unread-count drops.
3. **Email matrix (the (a) read-back)** — an `investment_updates`/`returns`/`security` event writes **in-app + one `email_outbox`**; an in-app-only event (deposit credited, secondary sale, LP fill, KYC started, family member-added) writes **in-app and NO outbox row**.
4. **Prefs gate email, never in-app** — pref off → event writes in-app but **no outbox**; pref on → outbox written. In-app always written regardless.
5. **Family invite** — `add_member` for a non-user writes an `email_outbox` with `to_email`=invitee, `user_id` NULL, **unconditional** (force, no prefs).
6. **Broker commission** — accrual now writes in-app + outbox (was silent).
7. **Transactional atomicity** — money-tx rollback ⇒ no in-app row AND no outbox row (outbox is in-tx); the email send is **never** inside the money tx.
8. **Drainer** — pending → `sent` (mocked `send_email` asserted called); failure → `attempts++`, retried; already-`sent` not re-sent; `SKIP LOCKED` concurrency safe.
9. **Preferences API** — GET defaults (all true); PUT persists email cats; SMS/push payload keys ignored/rejected.
10. **Auth/gating** on every endpoint; admin gate on the dispatch cron.

Frontend: bell shows the live count (not "3"); `/notifications` lists + marks read; AccountSettings email toggles call `updatePreferences` and SMS/push are disabled; documents surfaces show the disabled state.

---

## 8. Invariants / rules in force

- **In-app is the source of truth feed**; email is a best-effort fan-out via the outbox (decoupled from money txns).
- **Email only for the financial/security set** — an event without an `email_category` can never email.
- **Only deliverable channels are offered** — SMS/push honest-disabled, never persisted.
- **DELETE NOTHING** — document mocks honest-disabled; only the dead `/documents` link removed.
- **No fabricated numbers** — the "3" badge becomes the real unread count.
- **Email = VPS-verify item** — built against the console seam now; Resend drained + verified live at the end.

---

## 9. Build order (after sign-off)

migration 0013 → models (`NotificationPreference`, `EmailOutbox`) → extend `notify()` + `email_service.dispatch_pending` → wire the 7 email call-sites + 2 new notify points → read/prefs routes + admin dispatch + SQLAdmin → DB tests → frontend (`notificationApi`, bell, `/notifications` page, AccountSettings prefs + honest-disabled SMS/push, documents honest-disable, remove `/documents` link) → gates green → PROGRESS.md.
