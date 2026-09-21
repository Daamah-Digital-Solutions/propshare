# Automatic bank withdrawals via Stripe — what is built and what the owner must do

Built 2026-09-21, local only (not pushed, not enabled). Crypto withdrawals are **unchanged**:
they still hold funds and wait for an admin. This document covers bank withdrawals only.

---

## 1. What the code now does

| Piece | Behaviour |
|---|---|
| `payout_auto_methods` (new platform setting) | Comma-separated methods that settle through their provider instead of the admin queue. `bank` = Stripe Connect, `crypto` = NOWPayments. Empty (the default) = everything stays manual. Validated: any other word is rejected with 422. |
| `manual_payouts_enabled` (existing) | Still the global default for any method not listed above. Setting `payout_auto_methods=bank` while this stays `true` gives **automatic bank, manual crypto** — the shape asked for. |
| Instant submit | An automatic withdrawal at or under `withdrawal_auto_approve_limit` is submitted to Stripe by the request itself (background task, after the hold is committed). The executor cron stays as the retry net. |
| Over the limit | Still goes to the admin review queue, on either rail. Default limit: $5,000 per request. |
| Not yet onboarded | Honest 409 `CONNECT_NOT_READY`; the wallet shows a **Link bank account** button instead of the saved-IBAN picker. |
| Provider not configured | A method listed as automatic whose provider has no keys silently stays manual. No customer-facing 503. |
| Stripe balance too low | The withdrawal returns to the admin queue **with its hold intact** (`withdrawal.submit_deferred` in the audit log), never "failed". See §4 — this is the most likely day-to-day issue. |
| Settlement | Unchanged: signed Stripe webhook marks it completed; a failure or reversal returns the money to the wallet; the reconcile cron re-queries stuck rows. |

New endpoint `GET /api/v1/wallet/payout-config` tells the wallet which flow to render per
method, so the UI never guesses.

## 2. What the owner must do in Stripe (cannot be done from our side)

1. **Activate the account and switch to live keys** — this is go-live blocker A2 in
   `GO_LIVE_CHECKLIST.md`. Automatic payouts cannot run on test keys.
2. **Enable Connect** in the Stripe dashboard, with **Express** accounts, and complete the
   platform profile Stripe asks for (business details, support contact, payout statement
   descriptor).
3. **Check country coverage.** Express payouts depend on the platform's country and on each
   recipient's country. Confirm with Stripe that the countries Capimax's investors live in are
   supported before promising instant bank withdrawals to them.
4. **Register the Connect/payout webhook**: `https://api.capimaxpropshare.com/api/v1/payments/webhooks/stripe-payouts`
   with the events `transfer.paid`, `transfer.failed`, `payout.paid`, `payout.failed`,
   `payout.returned`, `account.updated`. Put its `whsec_…` in `STRIPE_WEBHOOK_SECRET`.
5. **Decide the auto-approve limit.** Anything above it still needs a human. $5,000 is the
   current default.

## 3. Turning it on (after step 2 is done)

In `/admin → Platform Settings`:

| Key | Value |
|---|---|
| `payout_auto_methods` | `bank` |
| `manual_payouts_enabled` | leave `true` (keeps crypto manual) |
| `withdrawal_auto_approve_limit` | your number |

No restart needed — settings are read per request. To roll back instantly, blank
`payout_auto_methods`: every new withdrawal returns to the admin queue. Rows already sent to
Stripe are not affected.

## 4. Two truths to tell the customer honestly

**"Instant" is instant on our side, not at the bank.** The moment the customer confirms, the
money leaves our platform and is transferred to their Stripe-held account. Stripe then pays
their bank on its own schedule — normally **1–2 business days**, longer across borders. The
wallet wording says exactly this. For money in **minutes**, see the Instant Payouts section
at the end of this document — that is a separate, opt-in speed with a fee.

**Stripe can only pay out money that is in the Stripe balance.** Card deposits land there;
bank transfers and crypto deposits do not. If investors fund by bank or crypto and then
withdraw to bank, the Stripe balance runs dry and transfers are refused. The platform keeps
the withdrawal held and queued for an admin instead of failing it, but the fix is
operational: keep the Stripe balance topped up, or leave bank withdrawals manual until card
deposits are the main rail.

## 5. Tests

`backend/app/tests/test_payout_auto_mode_db.py`: bank automatic while crypto stays manual,
submit-on-request, over-limit review, 409 before onboarding, unconfigured fallback,
payout-config output and auth, settings validation, balance shortfall queued with the hold
intact, and other provider errors still returning the money. (The instant-speed cases are
listed in the last section.)
`src/components/dashboard/InvestorWallet.payouts.test.tsx`: manual keeps the saved account
picker, automatic asks for linking and blocks withdrawal until linked, a linked user sends
without a saved-account id and is told it was sent.

---

# Instant Payouts (money in minutes) — US investors

Added 2026-09-21 after confirming the Stripe account is registered in the **US**.

## Who can use it

Stripe pays a connected account instantly only when **both** the platform and the recipient
are in supported countries, and Connect itself only reaches connected accounts in the
**US, UK, EEA, Canada and Switzerland** from a US platform. Investors in the Gulf cannot be
paid through Stripe at all — neither instantly nor on the standard schedule — so the manual
admin-settled rail stays in place for them. Their withdrawals are unaffected by everything
in this document.

Within the eligible group, the investor also needs an **instant-eligible debit card** on
their Stripe account. We check that before ever showing the option, because Stripe fails an
instant payout to an ineligible destination.

## How a request flows

1. The investor ticks **Get it in minutes** and sees the fee and the net amount before
   confirming.
2. The wallet is held for the **full** amount, exactly as before.
3. We transfer `amount - fee` from the platform balance into their connected account.
4. We immediately pay that out to their card with `method=instant`.
5. The fee stays in our Stripe balance and covers the 1% Stripe charges the platform.

If step 4 fails (card removed, balance not yet instantly available), the withdrawal is
**downgraded to standard**, not failed: the money is already theirs and arrives on the normal
schedule. The row records why, and the customer keeps their money either way.

## Settings

| Key | Default | Meaning |
|---|---|---|
| `payout_instant_enabled` | `false` | Master switch for the instant option |
| `payout_instant_fee_pct` | `1.0` | What we deduct from the customer, rounded up to the cent |
| `payout_instant_max` | `9999` | Stripe's per-payout cap in the account currency |

Requires `payout_auto_methods=bank` — instant is a faster finish to the automatic rail, not a
separate one.

## What Stripe charges and limits

| Item | Value |
|---|---|
| Stripe fee to the platform | 1% of each instant payout |
| Arrival | Usually within 30 minutes, 24/7 including weekends |
| Per-payout cap | 9,999 USD |
| Daily cap | Platform-wide, visible in the Stripe Dashboard |
| Eligibility | Not automatic for new platforms — confirm in the Dashboard before switching it on |

Two operational notes. Only funds that came from **card** payments count as instantly
available, so bank-transfer and crypto deposits do not feed this rail. And `payout_instant_max`
must be kept in step with Stripe's published cap.

## Before switching it on

1. Confirm in the Stripe Dashboard that the platform is eligible for Instant Payouts and note
   the daily limit.
2. In Connect external account settings, set **Allow debit cards** to **Yes**, otherwise
   investors cannot add an eligible card.
3. Make sure onboarding uses the **full** service agreement — recipient-agreement accounts
   cannot receive instant payouts.
4. Disclose the fee wherever it is marketed. Stripe requires it.

## Tests

`backend/app/tests/test_payout_auto_mode_db.py` grew to 16: fee deducted and rounded up, the
card push carries the net amount, the wallet ledger stays single-entry, a failed instant leg
downgrades without losing money, refusal without an eligible card happens before any hold,
the per-payout cap is refused while the same amount passes at standard speed, refusal when
the switch is off or the rail is manual, and readiness published to the wallet.
`src/components/dashboard/InvestorWallet.payouts.test.tsx` grew to 6: the option appears only
when the server allows it, the fee is shown before confirming and `speed=instant` is sent,
and an over-cap amount is blocked client-side.
