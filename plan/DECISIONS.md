# CapiMax PropShare — Decision Log

Locked product/engineering decisions, newest groups appended. Companion to `PROGRESS.md`
(state) — this file records *why*. Governing rules apply to every group below.

## Governing rules (all groups)
- **DELETE NOTHING** — never silent-remove; never ship a permanent honest-disabled stub. Build it real.
- **No fabricated numbers / no fake-success** — every figure has a real source or an honest empty state.
- **Reuse existing seams** — provider abstractions (email/storage/payments), `notify()`, ledger, OwnerDep.
- **Server-authoritative + owner-scoped** for anything money- or ownership-adjacent.
- **Verify-before-build**; on any contradiction with the live code, STOP and report.
- **Full gates green per commit** (ruff/black/mypy/pytest + tsc/eslint/vitest/build).

## Phase 15 / 15b / 15c (done earlier this arc)
- **15 — owner/dev stats:** pure aggregation, no migration; occupancy honest-empty; counts real.
- **15b — milestones:** `property_milestones` (mig 0015); NAV `value_index` nullable kept (no C/D regression);
  constructionProgress = current (in_progress) milestone %, else 0; fake 8-event PropertyTimeline deleted.
- **15c — investor communications:** `developer_updates` + `developer_update_recipients` (mig 0016);
  audience = per-property net-holders (Σ units>0); reuse Phase-12 `notify()`/outbox 1:1 (notify now returns
  the created Notification); metrics counts-only (recipients + in-app reads), NO open/click/delivered;
  manual 15b→15c bridge (pre-fill, never auto-send); idempotent on (update_id, user_id).

---

## Group 2 — Storage → Documents / Certificates (DONE 2026-06-28)
- **Storage seam** (`integrations/storage.py`, `STORAGE_PROVIDER`): "local" (default) writes
  REAL files under `storage_dir` (gitignored `backend/var/`), served by the app; "s3" (prod)
  lazy-imports boto3 + presigned URLs. No fake/placeholder files. Mirrors the email seam.
- **No migration** — the `documents` table (0001) + `profiles.avatar_url` + `properties.images`
  already exist (migrations stay at **0016**).
- **Documents:** owner-scoped upload (`POST /properties/{id}/documents`, 403 NOT_PROPERTY_OWNER);
  PUBLIC list + download (property docs are public on active/funded; draft → 404; user-scoped
  docs not served by the public route).
- **Certificates:** generated LIVE as a dependency-free PDF from the caller's net `ownership_ledger`
  holding (`GET /investments/certificate/{property_id}`; 404 NO_HOLDING). Not stored, always current.
  Wording is factual (ledger units; not a transferable security / SPV substitute).
- **Unblocked seams:** `POST /properties/{id}/images` (was 503) + `POST /profiles/me/avatar` now
  store real files; public assets served inline via `GET /files/{key}` (allow-listed prefixes only).
- **Frontend:** PropertyDocuments + InvestmentCertificates wired to real data (mock lists deleted);
  `apiRequest` now supports FormData; `fetchBlob` for authed PDF download.

<!-- groups 3–4 appended below as they complete -->
