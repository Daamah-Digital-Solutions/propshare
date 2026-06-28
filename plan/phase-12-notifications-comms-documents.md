# Phase 12 — Notifications, Comms & Documents

**Size:** Medium (≈1.5–2 weeks). Cross-cutting; consumes the `notify()` helper seeded in Phase 2 and adds real external channels + document generation.

## Goal
Turn the cosmetic notification/comms surfaces into real ones: in-app notifications feed, transactional email/SMS/WhatsApp, and **secure signed-URL download of uploaded documents**. **Generated contract/SPV/certificate documents are deferred out of v1 (D11)** — the templates and generation engine are post-launch. Replaces dead bells, fake "preferences saved", simulated live chat, and `#` document links ([audit/03-buttons.md](../audit/03-buttons.md)).

## Testable outcome ("done when…")
- Platform events (KYC decision, investment confirmed, payment, withdrawal, distribution, secondary sale, family transfer) create a **`notifications` row** the bell reads, plus a **real email/SMS** where configured.
- **Uploaded** documents (e.g. owner-supplied property docs) download via a short-lived signed URL after an authz check (no `#` links, no console.log stubs).
- **Generated** contracts/certificates/statements are **explicitly out of v1** — those buttons show a clear "available after launch" state, not fabricated documents.
- Notification preferences (Phase 1 store) actually control what is sent.

## Dependencies
Phases 2 (notify helper), 5/6/7/8/10/11 (the events to notify about). (Generated-document templates **deferred — D11**.)

## Backend work
- **`notification_service`** finalized: `notify(user_id, type, title, message)` writes `notifications` and fans out to email/SMS/WhatsApp per the user's prefs. Wire it into every event-producing service.
- **Comms integrations**: email (Resend/Postmark/SES), SMS/WhatsApp (Twilio/Meta) behind interfaces.
- **`document_service` (read/serve only in v1)**: authorize + issue signed URLs for **uploaded** documents in the `documents`/`kyc-documents` buckets via the app storage seam. **Document *generation* (contract/certificate/statement rendering) is deferred — D11** (no HTML→PDF engine, no templates in v1).
- Endpoints:
  - `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all` — replaces dead bells ([InvestorDashboard.tsx:70](../src/pages/InvestorDashboard.tsx:70), [MainLayout.tsx:54](../src/components/layout/MainLayout.tsx:54)) and the hardcoded "3" badge.
  - `GET /documents` (authorized list — mirrors the existing `documents` SELECT rule), `GET /documents/{id}/download` (signed URL), `POST /documents` (owner/admin attach).
  - `POST /support/contact` — real support submission (replaces fake-success [Support.tsx:100](../src/pages/Support.tsx:100)); decide if live chat is real or a documented "email/WhatsApp only".

## DB tables/columns touched / new migrations
- `notifications`: full read/write. `documents`: real rows + storage. Notification-prefs store (Phase 1). Storage seam completed for the `documents`/`kyc-documents` private buckets (signed URLs).

## Frontend wiring
- Bells/notification UI ([InvestorDashboard.tsx:70](../src/pages/InvestorDashboard.tsx:70), [MainLayout.tsx:54](../src/components/layout/MainLayout.tsx:54), home [NotificationsSection.tsx](../src/components/home/NotificationsSection.tsx)) read `/notifications`.
- Document downloads ([PropertyDocuments.tsx:90](../src/components/property/PropertyDocuments.tsx:90), property detail doc tabs): real signed-URL downloads of **uploaded** docs; retire console.log/`#` stubs.
- **Generated** documents — investment certificates ([InvestmentCertificates.tsx:73](../src/components/dashboard/InvestmentCertificates.tsx:73)) and statement exports ([ReturnsTracker.tsx:225](../src/components/dashboard/ReturnsTracker.tsx:225), [InstallmentSchedule.tsx:74](../src/components/dashboard/InstallmentSchedule.tsx:74)): show an explicit "available after launch" state (**deferred — D11**), not a fabricated/console.log download.
- [Support.tsx](../src/pages/Support.tsx): real contact submission; honest chat state.
- AccountSettings notification toggles drive real preferences (built Phase 1, consumed here).

## External integrations
- Email + SMS + WhatsApp providers; PDF rendering; document templates (D11).

## Test plan
- **Success:** each event creates a notification + sends the configured channel; opt-out preference suppresses the channel; investment contract generates and downloads via signed URL.
- **Failure/authz:** unauthorized document download `403`; signed URL expires; forged/expired link rejected.
- **Comms:** sandbox email/SMS delivered; no PII leaked in messages.

## Risks / watch-outs
- **Don't reintroduce fakes** — every comms/document action must be real or explicitly disabled (the deferred generated-docs must show an honest "after launch" state, never a fabricated file).
- **Generated documents deferred (D11):** contracts/SPV/certificates/statements are post-launch; ensure nothing downstream (e.g. Phase 5's "attach a contract on confirmed investment") hard-depends on them — treat contract generation as an optional, later hook.
- **Deliverability/compliance** for email/SMS (sender verification, opt-out) — configure properly.
