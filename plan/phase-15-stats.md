# Phase 15 — Owner/Developer Real Stats (design, for sign-off)

**Type:** real-aggregation phase. **Read endpoints + frontend wiring only. NO migration**
(occupancy / milestones / comms tables are their own later sub-groups). Server-authoritative,
no fabricated numbers, DELETE NOTHING (every card stays; data source swapped mock→real or
honest-empty).

Auth: both the Owner and Developer dashboards are gated to the **`owner`** role
(`App.tsx` `ProtectedRoute roles={["owner"]}`), so both new endpoints use
`require_active_role_db("owner")` (the existing `OwnerDep`).

Money/Decimal values are returned as **strings** (matches every existing money API).

---

## 1. New backend endpoints

New module `app/api/routes/owner_stats.py` (prefix `/api/v1`, tag `owner-stats`) + new
`app/services/owner_stats_service.py` + `app/schemas/owner_stats.py`. Registered in the app
router alongside the others.

### 1.1 `GET /api/v1/owner/portfolio-stats` → Owner Overview
```jsonc
{
  "total_portfolio_value": "5000000.00",   // Σ properties.total_value (owner's props)
  "total_investors": 150,                   // distinct holders, net units > 0
  "occupancy": null,                        // honest-empty: NO occupancy domain exists
  "monthly_revenue_current": "12000.00",    // current calendar month generated-distributions
  "monthly_revenue_series": [               // last 6 months incl. current, real zeros
    { "month": "2026-01", "amount": "0.00" },
    { "month": "2026-02", "amount": "8000.00" }, ...
  ],
  "per_property": [
    { "property_id": "…", "revenue_generated": "20000.00", "occupancy": null }  // all-time
  ]
}
```

### 1.2 `GET /api/v1/owner/funding-stats` → Developer dashboard
```jsonc
{
  "monthly_funding_series": [               // last 6 months incl. current, real zeros
    { "month": "2026-01", "amount": "250000.00" }, ...
  ],
  "funding_this_month": "65000.00",         // current calendar month confirmed funding
  "repeat_investors": { "repeat": 1, "total": 2, "pct": "50.0" },
  "distinct_investors": 2                    // distinct investors w/ ≥1 confirmed (optional Total-Investors source)
}
```

---

## 2. Exact aggregation logic per card

`owner_props` = `SELECT id FROM properties WHERE owner_id = :owner` (scalar subquery / IN list).
All sums `COALESCE(..., 0)`. The month spine (last 6 months incl. current) is generated in
Python (`datetime.now(tz=utc)` back 5 months) and left-joined onto the grouped result so empty
months are **real zeros**, never omitted.

| Card | Source | Logic |
|---|---|---|
| **Owner — Total Portfolio Value** | `properties` | `SUM(total_value) WHERE owner_id=:owner` |
| **Owner — Total Investors** | `ownership_ledger` | `COUNT(*)` over `(SELECT user_id FROM ownership_ledger WHERE property_id IN owner_props GROUP BY user_id HAVING SUM(units) > 0)` — current holders only (fully-exited users excluded) |
| **Owner — Monthly Revenue (card + chart)** | `distributions` | `date_trunc('month', created_at)`, `SUM(gross_pool)`, `WHERE property_id IN owner_props AND status='completed'`. Card = current-month bucket; chart = the 6-month series. "Revenue generated on your properties" (NOT owner personal income — none exists). |
| **Owner — Avg. Occupancy** | — | **null** → honest empty state. No occupancy/tenancy/lease/rentable-unit model exists; fractional-ownership units ≠ physical units. Future domain (own phase). |
| **Owner — per-property Revenue** | `distributions` | `SUM(gross_pool) GROUP BY property_id` (all-time, `status='completed'`), keyed back onto each property card. |
| **Owner — per-property Occupancy** | — | **null** → same honest empty state. |
| **Dev — Monthly Funding chart** | `investments` | `date_trunc('month', confirmed_at)`, `SUM(amount)`, `WHERE property_id IN owner_props AND status='confirmed' AND confirmed_at IS NOT NULL`. 6-month series, real zeros. |
| **Dev — "This Month"** | `investments` | current-month bucket of the same series. |
| **Dev — Repeat Investors** | `investments` | `WITH per_user AS (SELECT user_id, COUNT(*) n FROM investments WHERE property_id IN owner_props AND status='confirmed' GROUP BY user_id)` → `repeat = COUNT(*) FILTER (WHERE n>=2)`, `total = COUNT(*)`, `pct = round(repeat/total*100,1)` (0 when total=0). |
| **Dev — core stats** (Active Projects / Total Raised / Total Investors / Avg Funding / Avg Investment) | already real (frontend Σ from `listOwner`, cleanup pass) | unchanged; **optional**: switch *Total Investors* to `distinct_investors` from this endpoint (ledger/investment-distinct, no cross-property double-count). |

**Definitions to confirm (called out, not assumed):**
- **Total Investors = net-holders (`HAVING SUM(units) > 0`)** rather than "any user_id ever in the ledger" — avoids counting users who fully exited. (Owner's note said "distinct user_id in ownership_ledger"; this is the honest refinement — please confirm.)
- **Monthly Revenue card = current calendar month** (matches the "Monthly" label; honestly $0 in months with no distribution). Alternative: trailing-6-month total. Recommend current-month.
- **Repeat Investors = ≥2 confirmed investment rows** across the dev's properties (so buying twice in one project counts). Alternative: invested in ≥2 distinct properties. Recommend the row-count definition per your note.
- **Confirmed** = `investments.status='confirmed'`; **settled distribution** = `distributions.status='completed'`.

---

## 3. Honest-empty occupancy treatment (DELETE NOTHING)
The two occupancy surfaces (overview card + per-property cell) stay present and render a
real **empty state** — `occupancy: null` from the API → UI shows `"—"` with sublabel
`"No occupancy data yet"`. This is a real card awaiting a future occupancy/tenancy domain,
**not** a disabled feature and **not** a fabricated 94%. No data source invented.

---

## 4. Frontend wiring

`src/lib/api.ts` — new `ownerStatsApi`:
- `portfolioStats(): Promise<OwnerPortfolioStats>` → `/owner/portfolio-stats`
- `fundingStats(): Promise<DeveloperFundingStats>` → `/owner/funding-stats`

**OwnerDashboard.tsx**
- `useQuery(["owner","portfolio-stats"], ownerStatsApi.portfolioStats)`.
- 4 cards read from the endpoint: portfolio value, total investors, monthly-revenue (current), occupancy → empty state.
- **Restore the revenue chart** (re-add `recharts` AreaChart removed in cleanup) fed by `monthly_revenue_series` (real, incl. zeros).
- Per-property cards: overlay `per_property[].revenue_generated` ("Revenue Generated") + occupancy empty, matched by `property_id`; keep Investors/Next-Payout. Still uses `listOwner` for the property list (names/images/funding) — DELETE NOTHING.
- Greeting already real (`user.full_name`); confirm "Emaar Properties" mock is gone (it is, post-cleanup).

**DeveloperDashboard.tsx**
- `useQuery(["owner","funding-stats"], ownerStatsApi.fundingStats)`.
- **Restore the Monthly Funding chart** (re-add `recharts` BarChart) fed by `monthly_funding_series`.
- "This Month" card → `funding_this_month`; Repeat Investors card → `repeat_investors.pct`.
- Core stats unchanged (optionally Total Investors → `distinct_investors`).
- **Milestones tab + Investor Communications:** reworded honest **"Coming soon — being built"** state (NOT "not available"/disabled), since they're the immediate next sub-group. No fabricated data; "Add Milestone Update"/"Send Update" stay disabled until their tables land.

All mock literals already retired in the cleanup pass stay retired; this phase removes the
remaining frontend Σ-placeholders by pointing the cards at the real endpoints.

---

## 5. Test plan

**Backend — new `app/tests/test_owner_stats_db.py` (DB-backed):**
- Portfolio value = Σ total_value (owner-scoped; another owner's props excluded).
- Total investors = distinct net-holders: seed a holder who fully exited (net 0) → excluded; two with net>0 → 2.
- Monthly revenue: seed `completed` distributions in 2 distinct months → series has those months' `gross_pool`, **zeros for the other months**; current-month card matches; `pending` distribution excluded; per-property revenue correct & owner-scoped.
- Occupancy: payload `occupancy` is null (aggregate + per-property).
- Funding series: seed `confirmed` investments across months → series correct with real zeros; `funding_this_month` correct; `pending`/`expired` excluded; other dev's properties excluded.
- Repeat investors: user A 2 confirmed, user B 1 confirmed → `{repeat:1,total:2,pct:"50.0"}`; zero-state → `{0,0,"0.0"}`.
- Auth: non-owner role → 403; unauthenticated → 401.

**Frontend — update `OwnerDashboard.test.tsx` / `DeveloperDashboard.test.tsx` (+ mock `ownerStatsApi`):**
- Cards render the real endpoint values; **occupancy shows "No occupancy data yet"** (no 94%).
- Charts render the real monthly series (incl. a zero month).
- No fabricated literals remain ($12.5M/$85k/1,234/94%/$45.2M/3,456/92%/$6.5M).
- Greeting uses the real name.
- Milestones/Comms show "coming soon / being built" (not fabricated rows).

Gate: ruff/black/mypy/pytest (backend) + tsc/eslint/vitest/build (frontend) all green;
**backend test count +~9**, frontend tests updated (no net mock literals).

---

## 6. Built-now vs later sub-groups

**Built now (Phase 15):** the two read endpoints + service + schemas (no migration), all
frontend card/chart wiring above, occupancy honest-empty, greeting. Real aggregation only.

**Next sub-groups (NOT this phase — flagged honestly in UI as "coming soon / being built"):**
1. **15b — Milestones** → new table `property_milestones` (property_id, title, description, status, target_date, completed_at, ordering, created_by); owner CRUD + investor-readable on the property page.
2. **15c — Investor Communications** → new table `developer_updates` (developer/property scope, subject, body, sent_at); **send = fan-out via the existing Phase-12 `notify()` + `email_outbox`**; recipient-count real, in-app read-count via `notifications.read`; true email open-rate deferred.
3. **Storage → Investment Certificates / documents** (needs app document storage).
4. **Saved Payment Methods** (security-sensitive, tokenized storage).
5. **Estate / inheritance / beneficiaries / gifting** — LAST, with a dedicated legal-design step (CapiMax's own scope).

Occupancy/tenancy remains its own future domain (property-management subsystem) — out of all
the above sub-groups unless the owner scopes it explicitly.
