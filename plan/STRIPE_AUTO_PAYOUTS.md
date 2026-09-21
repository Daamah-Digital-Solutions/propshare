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
wallet wording says exactly this. Stripe's own "Instant Payouts" product (minutes, to an
eligible debit card, for a fee) is a separate feature we have not built.

**Stripe can only pay out money that is in the Stripe balance.** Card deposits land there;
bank transfers and crypto deposits do not. If investors fund by bank or crypto and then
withdraw to bank, the Stripe balance runs dry and transfers are refused. The platform keeps
the withdrawal held and queued for an admin instead of failing it, but the fix is
operational: keep the Stripe balance topped up, or leave bank withdrawals manual until card
deposits are the main rail.

## 5. Tests

`backend/app/tests/test_payout_auto_mode_db.py` (9 tests): bank automatic while crypto stays
manual, instant submit, over-limit review, 409 before onboarding, unconfigured fallback,
payout-config output and auth, settings validation, balance shortfall queued with the hold
intact, and other provider errors still returning the money.
`src/components/dashboard/InvestorWallet.payouts.test.tsx` (3 tests): manual keeps the saved
account picker, automatic asks for linking and blocks withdrawal until linked, a linked user
sends without a saved-account id and is told it was sent.
