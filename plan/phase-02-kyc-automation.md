# Phase 2 — KYC Automation & Gating

**Size:** Medium (≈1.5–2 weeks), plus a **business prerequisite**: a signed KYC/AML provider account (OPEN DECISION **D1**). Engineering is medium; the *account/contract* must be in place to test end-to-end.

## Goal
Make identity verification **instant and automatic** via a specialized provider (no human approval step), and block investing until a user is `verified`. This directly delivers automation requirement #1 ([audit/06-automation-gaps.md](../audit/06-automation-gaps.md)), which today is upload-only with manual approval that never happens ([KYCVerification.tsx:181](../src/pages/KYCVerification.tsx:181)).

## Testable outcome ("done when…")
- A test applicant completes the provider flow and the backend sets `kyc_verifications.status = verified` **automatically via the provider webhook — with no human action**; a failing applicant is set `rejected` with a reason.
- The KYC page reflects live status (pending → submitted → verified/rejected) from the backend.
- An unverified user calling the (Phase 5) invest endpoint — or any KYC-gated endpoint stub — receives `403 KYC_REQUIRED`.
- An admin "exceptions" queue shows only applicants the provider flagged for manual review (the *only* human path), not the default.

## Dependencies
Phase 1 (identity, RBAC, storage seam, notify() introduced here).

## Backend work
- **KYC provider integration** (`services/integrations/kyc_provider`): `create_applicant()`, `get_status()`, and an inbound **signature-verified webhook** that maps provider decision → `verified` / `rejected` / `needs_review`.
- Endpoints:
  - `GET /kyc/me` — own status + fields.
  - `POST /kyc/me/start` — create provider applicant/session; return the provider SDK token/URL the frontend launches.
  - `POST /kyc/me/documents` — (fallback/manual upload path to `kyc-documents` storage) for providers that accept our uploads; otherwise the provider SDK handles capture.
  - `POST /payments/webhooks/kyc` (or `/kyc/webhook/{provider}`) — **the automation core**: verify signature → update status → notify user → audit. Idempotent on provider event id.
  - Admin exceptions: `GET /admin/kyc?status=needs_review`, `POST /admin/kyc/{id}/approve`, `POST /admin/kyc/{id}/reject` — used **only** for provider-flagged cases.
- **Gating dependency** `require_kyc_verified` becomes live (defined Phase 1, enforced here and consumed by Phases 5/7/8).
- **`notify()` helper** (`notification_service`) introduced here — first events: KYC submitted/approved/rejected → writes `notifications` rows (email/SMS fan-out wired in Phase 12).

## DB tables/columns touched / new migrations
- `kyc_verifications`: write status/`verified_at`/`rejection_reason`; add provider columns (`provider`, `provider_applicant_id`, `provider_event_id` for idempotency).
- `notifications`: first real writes.
- `audit_log` (created here if not earlier): KYC decisions are privileged events.

## Frontend wiring
- [KYCVerification.tsx](../src/pages/KYCVerification.tsx): replace the direct `supabase.storage`/`from("kyc_verifications")` calls ([:97](../src/pages/KYCVerification.tsx:97),[128](../src/pages/KYCVerification.tsx:128),[173](../src/pages/KYCVerification.tsx:173)) with the provider SDK launch + backend status polling. Keep the existing status UI (pending/submitted/verified/rejected) — it already matches the `kyc_status` enum.
- Account Settings KYC card ([AccountSettings.tsx:401-425](../src/pages/AccountSettings.tsx:401)) reads live status.
- Fix the private-bucket `getPublicUrl` bug noted in [audit/01-schema.md](../audit/01-schema.md) ([KYCVerification.tsx:137](../src/pages/KYCVerification.tsx:137)) by using backend signed URLs.

## External integrations
- KYC/AML provider (D1: Sumsub / Onfido / Persona) — **requires a paid account + business onboarding**; sandbox keys for testing.

## Test plan
- **Success (automation):** sandbox "approved" applicant → webhook → status `verified` with **zero human steps**; user is notified; can pass `require_kyc_verified`.
- **Failure:** sandbox "declined" → `rejected` + reason shown; user remains blocked from invest (`403 KYC_REQUIRED`).
- **Exception path:** provider "needs review" → appears in admin queue; admin approve/reject works and is audited.
- **Idempotency/security:** replayed webhook event does not flip status twice; forged webhook (bad signature) is rejected `401`.

## Risks / watch-outs
- **Provider availability gates testing** — D1 must be resolved and a sandbox account obtained before this phase can finish.
- **AML/PII retention:** KYC docs are sensitive; store in private storage, access via short-lived signed URLs, log every access. Business confirms retention rules.
- Keep the manual-review path strictly an *exception*, never the default gate (automation requirement #5).
