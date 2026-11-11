"""Seed the assistant's knowledge base with the platform's approved wording (plan §7).

Articles are WORDING ONLY: how things work, what to expect, where to go. They carry no live
figures (fees, prices, limits, dates) — those come from tools that read the real data, so an
article can never go stale about money. Sources: the public explainer pages (FAQ, How it
works, Fees, Exit mechanisms, Platform rules, SPV model) reduced to what the platform
actually does today.

Every run writes DRAFTS (a new version only when the text changed). Approval is a separate,
audited act in the admin panel (Knowledge Base -> Approve), or ``--approve-as <admin email>``
for a local/dev database.

Usage:
    python scripts/seed_kb.py                      # drafts only
    python scripts/seed_kb.py --approve-as admin@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import session_scope
from app.models import KbArticle
from app.services import auth_service, kb_service

# (slug, title, category, priority, body)
ARTICLES: list[tuple[str, str, str, int, str]] = [
    (
        "what-is-fractional-ownership",
        "What fractional ownership means here",
        "basics",
        10,
        """Capimax PropShare lets several investors own one property together. A property is split
into units with a fixed unit price; you buy whole units and own that share of the property.
Each investor's share is recorded in the platform's ownership ledger and documented through
the investment agreements. Ownership is held through a Special Purpose Vehicle (SPV): a
separate legal company that owns the property, so your investment is linked to the asset, not
to the platform's balance sheet. The platform is the digital marketplace and operator; it does
not own the properties.""",
    ),
    (
        "ownership-models",
        "The property models: ready income, under construction, in full or in installments",
        "basics",
        20,
        """Every listing states its model on the property page.
- Ready property (income): a completed, leased property. Net rental income is distributed to
  holders periodically and lands in your wallet, where you can withdraw or reinvest it.
- Under construction (development / off-plan): there is no rental income while the project is
  being built; you earn through the price of a unit going up. The platform gives the property
  a new unit price as the project is revalued, about once a month, and when a new sales phase
  opens: a later buyer pays the new price, and what you hold is valued at it. The listing
  shows the price now and its history, construction progress, milestones and the expected
  completion date.
- How an under-construction property is bought depends on the listing: paid in full at the
  current unit price (a project sold in phases, each phase at its own price), through an
  installment plan (a down payment now and monthly instalments after, with no bank interest,
  at the unit price locked when the plan starts), or either. The plan and its schedule are
  shown before you commit and afterwards under your portfolio.
What you hold in an under-construction property can be offered for sale at any time, like a
ready one, including a plan you are still paying (see "How to exit").
Use the property page for the figures of a specific listing (unit price, minimum investment,
expected yield, fees, exit options); the assistant reads them from the same data.""",
    ),
    (
        "getting-started",
        "How to start: account, verification, funding, investing",
        "basics",
        30,
        """1. Create an account and confirm your email address (a verification link is sent;
   you can ask for it again from your account or from the assistant).
2. Complete identity verification (KYC). Investing and withdrawing are only possible once
   your verification status is "verified". The Account page shows your status and, if a
   check was rejected, the reason and how to resubmit.
3. Add funds to your wallet: card, cryptocurrency, or bank transfer. Bank transfers are
   credited after the team matches your transfer reference; the wallet shows pending and
   available balance separately.
4. Open a property, choose the number of units, review the total including fees and the
   exit options, and confirm. Every property takes the same payment methods: your wallet
   balance, a card (Apple Pay and Google Pay on devices that support them), cryptocurrency
   (you choose the coin and its network on PropShare, then send it on the payment page that
   opens for that coin), Pronova (a discount off what you pay now) or a
   Nova Sukuk certificate (our team reviews it; the units stay pledged to Nova Finance until
   it releases them). Your investment then appears in your portfolio, and a digital
   investment certificate can be downloaded from there.
The assistant can show your own balance, verification status, investments and payments, and
send you to the right page, but it never invests, deposits or withdraws for you.""",
    ),
    (
        "wallet-deposits-withdrawals",
        "Wallet, deposits and withdrawals",
        "payments",
        40,
        """Your wallet holds your available balance and any amount on hold (for example a
withdrawal that is being processed). Deposits: card payments and crypto are credited
automatically when the payment provider confirms them; a bank transfer must be matched to the
reference shown on the deposit page and is credited by the team after review.
Crypto: you choose the coin and its network on PropShare first, and the payment page that
opens asks for that one coin, at one address and for an exact amount. Send that coin, on that
network. Scanning the QR code, copying the address or connecting a wallet on that page are the
same transfer and are all detected by themselves. You can close the page after sending: the
top of the wallet shows the payment as on its way, and it is credited once the network
confirms it (usually within minutes), with a notification. A transfer that arrives short, or
in another coin or network that the payment provider could still process, is credited to the
wallet at the value that arrived (this can take longer) and you are told the amount. A crypto
payment for a purchase or a down payment that arrives clearly short does not complete it: the
units are released and what arrived goes to the wallet, to buy from there. One that is short
by a hair only (a rounding or network-fee difference) still completes it. Every coin has a
smallest payment, which moves with its network's fees: it is shown under the coin when you
choose it, and an amount under it cannot be paid in that coin (choose another coin or a
larger amount). A coin that needs a memo or tag must be sent with the one shown on the
payment page.
Withdrawals: first save where the money goes (Wallet -> Payment Methods: a bank account with
the bank, holder, IBAN or account number, SWIFT, country and currency, or a crypto wallet with
its network and address); numbers are only ever shown as their last four. A withdrawal needs a
confirmed email address and at most your available balance; the request holds the amount at
once and gets a number (WD-...). A manual withdrawal is paid by our team by hand to the saved
account on the request, usually within 1-2 business days: you are notified and emailed when it
is sent (with the transfer reference) or, if it could not be sent, with the reason, and then
the amount is back in your wallet. If the platform pays bank withdrawals automatically and
you have linked your bank once through Stripe from the wallet page (available for accounts in
the US, UK, EEA, Canada and Switzerland), the withdraw screen lets you choose Automatic (sent
at once, ticked first) or Manual (a saved bank account our team pays). Crypto withdrawals are
manual. Every wallet movement, a withdrawal and its refund included, has a numbered PDF
receipt: the download icon beside it in the wallet's history. Where instant
payouts are switched on, an eligible debit card can receive the money within minutes for a
small fee that is shown before you confirm and deducted from the amount; if an instant payout
cannot go through it is sent at standard speed instead, never lost. You see every withdrawal,
its number, destination and status in your wallet (Withdrawal requests) and are notified when
it is paid or returned (returned funds go back to your wallet). Every document you download
from the platform (certificates, receipts, statements, installment schedules) comes in the
language you have the site in: English, Arabic or French. An account statement for any period you choose (up to
three years at a time) can be downloaded as a PDF or an Excel file from the Account statement
card on the wallet page: opening and closing balance, every movement with a running balance,
totals by type and your holdings at the end of the period. Your units have their own
statement: Dashboard -> Active Investments -> Unit Movements -> "Download statement" gives,
for the period you choose and as a PDF or an Excel file, every purchase, sale and transfer of
units with the units held in that property after it, and per property the units held at the
start and at the end. If a payment looks stuck, the assistant can show its current status and
open a support ticket with the reference for a person to follow up.""",
    ),
    (
        "fees-overview",
        "Which fees exist and where you see them",
        "fees",
        50,
        """All investor fees are shown before you confirm and are included in the checkout
summary, so the total you see is the total you pay. The kinds of fees on the platform:
- a platform fee when buying units, added on top of the units' price;
- an annual management fee on income-generating properties, deducted before distributions;
- a resale fee on a secondary-market trade, paid by the buyer on top of the price (the seller
  receives the price in full); when an installment position is sold it is calculated on the
  amount the buyer pays the seller;
- an installment fee on plans, added to the down payment and to each instalment and shown in
  the schedule;
- a liquidity-market discount/fee when exiting instantly through a liquidity provider.
Some properties or programmes carry a discount (for example reinvesting distributions).
The current rates are platform settings: the assistant reads them live (get_platform_settings)
and the Fees page and every checkout show them. Fee history is visible in your transactions.""",
    ),
    (
        "returns-and-distributions",
        "Returns and distributions",
        "returns",
        60,
        """For income properties, net rental income (after operating costs and the management
fee) is distributed to holders in proportion to their units and credited to their wallets.
Your portfolio shows each distribution and your total returns; the Reports page has the
history. Expected or target yields shown on a property page are projections from the
developer or the platform, not promises: actual distributions depend on real rental income.
Nobody on the platform, including the assistant, guarantees a return.""",
    ),
    (
        "exit-options",
        "How to exit: secondary market and liquidity market",
        "exit",
        70,
        """You are not locked into a property until it is sold: you can offer what you hold for
sale at any time, whether the property is ready or still under construction (a lock-up period
may apply after a purchase). Two exit paths exist:
- Secondary market: list some or all of your units at a price you set; another investor buys
  them and the units transfer when the buyer pays. The property's current unit price is the
  guide price. Best for maximum value when you are not in a hurry. You can cancel an unsold
  listing.
- Liquidity market: request an exit at the platform-quoted price (the current unit price less
  a discount and a fee) and a liquidity provider funds it, usually faster than waiting for a
  buyer.
Units you are paying for through an installment plan that is still running go with their
instalments: you can sell the whole plan or some of its units (one, two, any number), on the
secondary market or to a liquidity provider, or send them to another person. The buyer pays
you the principal you have paid on those units (the instalment fees you paid are not
returned) plus the increase in the unit price on them, and takes over their share of every
remaining instalment on its date. If the unit price has fallen, the decrease is taken off
instead. Example: a plan for units worth one thousand, with two hundred paid; the unit price
has risen by a tenth, so the position is worth eleven hundred; for the whole plan the buyer
pays you three hundred (the two hundred you paid plus the hundred gained) and then pays the
remaining eight hundred as the schedule says. Selling three units of ten is three tenths of
all of it: the buyer pays you three tenths of that, gets a plan of their own with the same
dates where every instalment is three tenths of yours, and your plan keeps seven units with
every instalment at seven tenths. A buyer can also take only some of the units you list. Part
of a plan changes hands only when none of its instalments is overdue: pay those first. If you
took the plan over from another investor, what you have paid means what you paid for it plus
your own instalments since, and the increase is counted from the price you bought it at.
A sale needs a buyer: no buyer, price or date is guaranteed. Both paths are used from your
portfolio; the assistant can show your holdings, positions, listings and requests and prepare
a listing for you, but the listing, sale or request is confirmed by you on that page.""",
    ),
    (
        "installment-plans",
        "Installment plans",
        "installments",
        80,
        """For properties sold in installments you pay a down payment now and monthly
instalments afterwards; the platform offers a set of plan lengths and the down payment
depends on the length chosen. The unit price is locked when the plan starts: later changes to
the property's unit price do not change your schedule, and an increase is your gain. The down
payment takes any of the platform's payment methods — the wallet, a card (Apple Pay / Google
Pay), crypto, Pronova (its discount comes off the down payment) or a Nova Sukuk certificate
(the plan starts once our team approves it). The full schedule, with the installment fee on
each payment, is shown before you commit and afterwards under Portfolio -> Installments.
Instalments are taken
from your wallet automatically on their due dates, and you receive a reminder a few days
before each one. If the wallet cannot cover an instalment on its due date, it is marked
overdue and retried automatically once funds are there: there is no late fee and your units
are not forfeited. Keep your wallet funded ahead of the due date. You can also pay the next
instalment early; the assistant can show your plans and schedule and prepare that payment.
The units of a running plan stay with their instalments: you can sell the whole plan, or
some of its units, at any time (see "How to exit"): the buyer pays you what you paid on them
plus the price increase and carries on with their share of the remaining instalments, as a
plan of their own; your plan keeps the rest, with each instalment reduced by the part sold.
Units of a plan can also go to a liquidity provider or, from Transfers, to another person, who
then pays their share of the instalments. Your Installments page shows what the position is
worth today.""",
    ),
    (
        "kyc-verification",
        "Identity verification (KYC)",
        "kyc",
        90,
        """Verification is required before investing or withdrawing, in line with anti-money
laundering rules. It is done from the Account page through the platform's verification
provider: identity document plus a selfie. Statuses: pending (not started or in progress),
verified, rejected (with a reason shown on the Account page; you can resubmit), and manual
review (a person is checking; you will be notified). The assistant can tell you your current
status and reason, and send you to the verification page, but it cannot verify you or change a
decision. If your check is stuck, ask the assistant to open a support ticket.""",
    ),
    (
        "secondary-market-rules",
        "Trading rules on the secondary market",
        "rules",
        100,
        """When selling or buying units between investors: list at a fair price within the
platform's price band, honour accepted offers, keep enough wallet balance to settle, and pay
the applicable fees shown at confirmation. Price manipulation, wash trading and artificial
volume are prohibited and lead to suspension. A lock-up period may apply before units can be
listed; the Sell form says when it ends. A position on an installment plan that is still running is
listed whole or in part, and a buyer can take all the units listed or some of them: before
buying, the buyer sees the units, what is paid to the seller now and the instalments taken
over with their dates and amounts; the buyer confirms that amount, gets those units as a plan
(the whole plan itself, or a plan of their own with the same dates) and pays its instalments
from their wallet on their dates.""",
    ),
    (
        "platform-rules",
        "Platform rules in short",
        "rules",
        110,
        """Provide accurate information at registration, verification and every transaction;
complete KYC before investing or withdrawing; use the platform for lawful investment only;
respect each listing's minimum investment, limits, lock-ups and exit procedures; do not create
multiple accounts, impersonate others, scrape, or try to bypass security. Violations can lead
to suspension, transaction reversal, holds pending investigation, legal action or regulatory
reporting. Suspected violations, fraud or legal matters go to the compliance team through a
high-priority support ticket, not to the assistant.""",
    ),
    (
        "spv-structure",
        "The SPV structure and what happens if the platform stops",
        "legal",
        120,
        """Each property is owned by its own Special Purpose Vehicle (SPV), a separate legal
company created for that property alone. The SPV holds the title, issues the fractional
interests, receives income or sale proceeds and distributes them. Because assets and
liabilities are separated per SPV, a problem with one property does not affect another, and
investor funds are never part of the platform's balance sheet. If the platform ceased
operating, the SPV and your ownership rights remain: a new manager can be appointed, income
can keep being distributed, or the asset can be sold and the proceeds distributed. Disputes
follow the governing law of the SPV's jurisdiction as set out in the agreements. SPV and
property documents are available on each property page.""",
    ),
    (
        "family-and-brokers",
        "Family groups and broker referrals",
        "roles",
        130,
        """Family group: a member can create a family group, add relatives, transfer their own
units to them and allocate returns within the group. Both sides are told every time, in their
notifications and by email. The Family Investment tab lists the activity of each member on
either side (members added, units and returns transferred or allocated, with their dates), so
a relative who only received sees it there too, and the Active Investments tab lists every
unit movement with the other person named. Units or returns allocated to a relative who has
no verified account yet stay reserved for them until they register with that email address,
confirm the address and verify their identity. Confirming the address matters: what is sent
to a person by email address (a family allocation, a gift) reaches the account registered
with that address only once the account confirmed it. The confirmation link is emailed at
sign-up and works from inside the account (sign in first, then open it); a new one can be
requested from Account Settings or from the assistant, and setting a new password with
"Forgot password" confirms the address too.
The assistant shows your group and its members' allocations (never their identity documents).
Brokers: an approved broker has a referral code;
investors who sign up with it are linked to the broker. When such a client invests, the broker
earns a percentage of the investment, paid by the platform (the client pays nothing extra):
each property can have its own rate, otherwise the general rate applies, and on an installment
plan it is earned on each payment. The broker's Commissions tab lists the rate of each property
and every commission earned (get_my_broker_activity has the figures). The broker dashboard's
"Listings & Referrals" tab lists everything the broker brought, with its status: "Add client"
emails the person the broker's link (they are linked only if they sign up through it), and
"Add property" / "Add project" introduces a property or an off-plan project with the owner or
developer contact and documents for the team to review (the team contacts them and lists it,
or explains why not; an introduction alone earns no commission). Applying for the broker,
owner or liquidity-provider role is done from Account -> Roles and reviewed by the team.""",
    ),
    (
        "beneficiaries-and-claims",
        "Beneficiaries, their certificate, and claiming after a holder's death",
        "roles",
        135,
        """Naming beneficiaries: an account holder names the people who should receive their
holdings under Dashboard -> Family Investment -> Beneficiaries & Inheritance. For each person
the holder records the full name as on their identity document, the relationship, the role
(beneficiary, heir, authorized person or legal representative), the identity document type and
number, and the share allocated to them; the shares of all the people together cannot pass the
whole. The holder can upload a copy of the person's identity document (a photo or a PDF) to
keep with the record, can edit or remove a record at any time, and can download a certificate
for each person. The certificate carries the platform's logo, the person's details as recorded,
a certificate number, its version (every change to a record makes a new version, and the
latest one is the valid one) and where a claim is made. It comes in the language the site is
in, and states the name in Latin letters, as on the passport, so the name must be written in
Latin letters; it also needs the identity document number. It records the
holder's wishes and is not a will. The assistant never shows identity documents or their
numbers.

What a share covers: a person's share of the holder's units is always part of it, and the
future returns of those units go with them. If the holder also ticked Wallet Balance or Full
Portfolio for that person, the same share of the holder's wallet balance on the day of the
transfer moves too (less any returns the holder had already allocated to relatives). Units
that are held back that day (listed for sale, in an exit request, in a scheduled gift, vested
under a running installment plan) and installment plans are not part of it: the team handles
them on request. The transfer condition the holder chose (for example "on verified death" or
"after 12 months inactivity") records a wish: nothing is ever transferred by itself, only
through a claim the team reviews.

Claiming: after the holder's death, or when the holder can no longer manage the account, the
person named opens the public page "Report a death or make a claim" (in the site's menu under
Help, and on the Support page) and sends their name, country and contact details, the holder's
name, the reason and the date of death, the certificate with its number, a copy of their own
identity document and, when they have it, the official document (for a death, the death
certificate). They receive a claim reference by email. The team checks the claim against the
holder's register, may ask for more, and decides. Assets are transferred only to the claimant's
own Capimax PropShare account once their identity is verified in it, so the claimant needs an
account of their own; nobody is ever given the holder's account, password or records. Each
person named makes their own claim for their own share. A signed-in claimant sees their claims
and their status on the same page and can add a document the team asked for. A claim sent
before signing in appears there, and is tied to the claimant's account, once the account uses
the same email address and that address is confirmed (a new confirmation link can be requested
on that page or in Account Settings). When the first claim on a holder's account is approved,
the holder's register is closed and can no longer be changed; and when that claim is for a
death, or for a holder who can no longer manage the account, the holder's account itself is
closed: it can no longer be signed in to, and what remains in it waits for the other claims.
The holder's address is told, so a holder who is there can object, and the team can reopen
an account. Someone who has no certificate should contact support.""",
    ),
    (
        "support-and-the-assistant",
        "What the assistant can do, and how to reach a person",
        "support",
        140,
        """The assistant answers from the platform's approved information and your own live
account data. It can show balances, statuses, investments, plans, holdings, notifications and
tickets; explain how things work; hand you the exact page; and, with your confirmation, resend
your verification email, mark notifications read, update your notification preferences, cancel
an unsold secondary-market listing, cancel a pending liquidity exit request, cancel a scheduled
family gift, or open a support ticket. It never moves money, never changes security settings
such as your password or two-factor authentication, and it does not give personal investment
advice. When it cannot
answer, it records the question for the team and offers the support link. Support tickets are
followed up by a person; you can see and reply to your tickets from the Support page, and you
are notified of each reply.""",
    ),
    (
        "account-security-2fa",
        "Account security and two-factor authentication",
        "account",
        150,
        """You can protect your account with two-factor authentication (2FA) from Account settings
-> Security. Scan the QR code with an authenticator app (Google Authenticator, Microsoft
Authenticator, Authy or similar), enter the six-digit code to confirm, and save the recovery
codes shown once: each one works a single time if you lose your phone. From then on, signing in
with your password or with Google asks for the current code from the app. Several wrong codes
in a row lock the second step for a short while. You can turn 2FA off or create new recovery
codes from the same page after confirming a current code. If you lost both your phone and your
recovery codes, open a support ticket: after the team verifies your identity an administrator
can reset 2FA so you can set it up again. The assistant can tell you whether 2FA is on, but it
never turns it on or off and never asks you for a code or password.""",
    ),
    (
        "developers-and-verification-center",
        "Developer profiles and verifying documents",
        "basics",
        160,
        """Each property page names its developer; View Profile opens the developer's public page
with what the platform has recorded about them (about, website, track record, verifications)
and their listings that are open on the platform. Investment certificates are downloaded from
the Certificates tab; each one carries a number, a verification code and a QR code, and the
Verification tab of the investor dashboard lists them for every certificate you hold.

The Verification Center page says where each kind of record is verified.
- Capimax PropShare investment certificates are verified on PropShare itself: scan the QR code
  printed on the certificate with your phone's camera and it opens the certificate's
  verification page, which shows whether it is authentic and its current status (valid,
  superseded by a newer certificate, or revoked) with what it states. Can't scan it? Enter the
  verification code printed beside the QR code on the Verification Center. A certificate
  states the units you held when it was issued: when they change, your next certificate states
  the new count and the old one shows as superseded.
- Valuation and financial documents (valuation reports, investment studies, financial
  analyses, accounting and financial reports, due diligence reports): CIM Global Financial
  (https://www.cimglobalfinancial.com/capimax-verify). Enter the document number or
  verification ID.
- Insurance certificates: CoverTech Insurance
  (https://www.covertechinsurance.com/capimax-ecosystem), to confirm authenticity, coverage
  and current status.
- Legal documents and agreements: the LexCrest Global Document Center
  (https://lexcrestlegal.xyz/document-center). Enter the unique document number shown on the
  document; where permitted, public documents can be previewed or downloaded.
- Blockchain records, smart contracts, tokenized assets and digital certificates of the
  ecosystem's blockchain-enabled platforms (not PropShare): Proof Anchor
  (https://www.proofanchor.io/verify). Search by certificate or verification number, contract
  or token address, asset ID or project name.
The Capimax Trust gateway is linked from the same page.""",
    ),
    (
        "capimax-ecosystem-and-partners",
        "PropShare in the Capimax ecosystem, and its partners",
        "basics",
        5,
        """Capimax PropShare is the Capimax ecosystem's digital, non-blockchain platform for
fractional participation in real estate, focused on off-plan and under-construction projects and
portfolios. Units are digitally recorded contractual participation interests backed by each
property's SPV, agreements and holder register; they are not crypto tokens. Sister routes:
Capimax Assets (ready, income-producing property, non-blockchain), Capimax BRX and Capimax RT (the
ecosystem's separate tokenized routes), Capimax Group and Capimax One (group umbrella and
discovery portal), Capimax Pro with CPV (property and document verification), Nova Digital
Finance (financing, separate from ownership) and Pronova / PRN (a separate digital-asset
project, never a share in a property). Partners by role: payments (Stripe, PayPal, NOWPayments),
identity and compliance (Sumsub), banking (Mercury, Revolut Business, Wise Business), financial
studies and valuation (CIM Global Financial), legal (LexCrest Global Legal), insurance
(CoverTech, Assurax), developers (Westoria Capital Estates, Crestmark Global, Valora Estates
Global, Verdea Estates, Aethera Development, Elevate Properties, Prime Stone Global) and
operators (Priminn Hotels, Elite Gate Properties, Crown Facilities). Details, what each one does
and official links are in the reference library.""",
    ),
    (
        "transfers-and-messages",
        "Transfers to another person, and messages from the team",
        "payments",
        135,
        """Transfers: an investor can send units of a property they hold, or an amount from their
wallet, to anyone by email: Dashboard -> Transfers (Transfer units / Transfer balance), or the
Transfer button in the wallet. Sending needs a confirmed email address and a verified identity.
The form takes the recipient's email (and name, optional), what to send, a delivery date (today,
or up to a year ahead) and an optional message; the review step shows what will be sent, its
value, the transfer fee (none unless the platform sets one) and what leaves the wallet now, and
nothing is sent before Confirm. Each transfer gets a number, TR- and ten characters.
What is sent is held at once: units are set aside from the holding (they cannot be listed,
offered to a liquidity provider or sent twice), an amount and the fee leave the wallet. Only
free units can be sent: units already listed for sale, reserved for something else, pledged or
on a running installment plan cannot. If the recipient's email is confirmed and their identity
verified, the transfer reaches them straight away (or on the chosen date): units appear in
their holdings, an amount in their wallet, and both sides are notified and emailed. If not,
the recipient is emailed an invitation and receives it as soon as they sign up with that email,
confirm it and verify their identity; if they do not within 30 days, everything comes back to
the sender, fee included. The sender can cancel a transfer that has not been delivered yet on
the Transfers tab, and everything comes back. A delivered transfer cannot be taken back.
The Transfers tab lists every transfer sent and received with its number, status (Scheduled,
Waiting for the recipient, Delivered, Cancelled / Expired / Failed - returned) and dates;
the wallet statement and receipts, and the unit movements, show the same TR- number.
Gifts work the same way now: a gift waiting for its recipient can be cancelled, and comes back
to the giver if it is not received within 30 days.
Messages: the Capimax PropShare team writes to members from the admin panel, to one member or
to everyone holding a role (investors, property owners and developers, brokers, liquidity
providers, or everyone). They arrive in Messages (in the menu, /messages), as a notification
and by email. Emails of messages sent to everyone can be turned off in Account Settings ->
Notifications -> Announcements; they still arrive in Messages, and a message written to one
member alone is always emailed.""",
    ),
]


# Arabic versions (Batch D). Same slugs, same rule (wording only, no live figures). Written
# in clear standard Arabic that reads naturally in Gulf and Egyptian use; the owner reviews
# and approves them from the admin panel like any other draft.
ARTICLES_AR: list[tuple[str, str, str, int, str]] = [
    (
        "what-is-fractional-ownership",
        "معنى الملكية الجزئية في المنصة",
        "basics",
        10,
        """تتيح Capimax PropShare لعدة مستثمرين امتلاك عقار واحد معًا. يُقسَّم العقار إلى وحدات
بسعر ثابت للوحدة، وتشتري أنت وحدات كاملة فتملك هذه الحصة من العقار. تُسجَّل حصة كل مستثمر في
سجل الملكية بالمنصة وتُوثَّق باتفاقيات الاستثمار. تُحفظ الملكية عبر شركة ذات غرض خاص (SPV):
شركة قانونية مستقلة تملك العقار، فيكون استثمارك مرتبطًا بالأصل لا بميزانية المنصة. المنصة هي
السوق الرقمي والمشغّل فقط؛ لا تملك العقارات.""",
    ),
    (
        "ownership-models",
        "نماذج العقارات: جاهز بدخل، تحت الإنشاء، بالدفع الكامل أو بالأقساط",
        "basics",
        20,
        """كل إدراج يذكر نموذجه في صفحة العقار.
- عقار جاهز (دخل): عقار مكتمل ومؤجَّر. يُوزَّع صافي دخل الإيجار على الملاك دوريًا ويصل إلى
  محفظتك، ومنها تسحب أو تعيد الاستثمار.
- تحت الإنشاء (تطوير / على الخريطة): لا يوجد دخل إيجاري أثناء البناء، وعائدك من ارتفاع سعر
  الوحدة. تحدّد المنصة للعقار سعر وحدة جديدًا كلما أُعيد تقييم المشروع، شهريًا تقريبًا، وعند
  فتح مرحلة بيع جديدة: المشتري اللاحق يدفع السعر الجديد، وما تملكه يُقيَّم به. يعرض الإدراج
  السعر الحالي وسجله ونسبة الإنجاز والمراحل وتاريخ الاكتمال المتوقع.
- طريقة شراء العقار تحت الإنشاء يحددها الإدراج: دفع كامل بسعر الوحدة الحالي (مشروع يُباع على
  مراحل، لكل مرحلة سعرها)، أو خطة أقساط (دفعة أولى الآن وأقساط شهرية بعدها بلا فوائد بنكية،
  بسعر الوحدة المثبَّت عند بدء الخطة)، أو أيهما. تُعرض الخطة وجدولها قبل التأكيد وبعده في
  محفظتك.
ما تملكه في عقار تحت الإنشاء يمكن عرضه للبيع في أي وقت مثل العقار الجاهز، حتى الخطة التي ما
زلت تسدد أقساطها (انظر «كيف تخرج»).
للأرقام الخاصة بإدراج معيّن (سعر الوحدة، الحد الأدنى، العائد المتوقع، الرسوم، خيارات الخروج)
ارجع لصفحة العقار؛ المساعد يقرأها من البيانات نفسها.""",
    ),
    (
        "getting-started",
        "كيف تبدأ: الحساب، التحقق، الشحن، الاستثمار",
        "basics",
        30,
        """1. أنشئ حسابًا وأكّد بريدك الإلكتروني (يصلك رابط تفعيل، ويمكنك طلبه مجددًا من حسابك
   أو من المساعد).
2. أكمل التحقق من الهوية (KYC). الاستثمار والسحب متاحان فقط عندما تصبح حالتك "تم التحقق".
   تعرض صفحة الحساب حالتك، وإن رُفض الطلب تجد السبب وطريقة إعادة الإرسال.
3. أضف أموالًا إلى محفظتك: بطاقة، عملة رقمية، أو تحويل بنكي. يُقيَّد التحويل البنكي بعد
   مطابقة الفريق لمرجع التحويل؛ تعرض المحفظة الرصيد المعلّق والمتاح كلًّا على حدة.
4. افتح عقارًا، اختر عدد الوحدات، راجع الإجمالي شاملًا الرسوم وخيارات الخروج، ثم أكّد. كل
   العقارات تقبل طرق الدفع نفسها: رصيد محفظتك، أو بطاقة (مع Apple Pay وGoogle Pay على الأجهزة
   التي تدعمهما)، أو عملة رقمية (تختار العملة وشبكتها على PropShare ثم ترسلها من صفحة الدفع
   التي تُفتح لهذه العملة)، أو Pronova (خصم على ما
   تدفعه الآن)، أو شهادة صكوك نوفا (Nova Sukuk) يراجعها فريقنا، وتبقى وحداتها مرهونة لصالح
   Nova Finance حتى تفكّ الرهن. يظهر استثمارك في محفظتك ويمكن تنزيل شهادة استثمار رقمية منها.
يستطيع المساعد أن يعرض رصيدك وحالة التحقق واستثماراتك ومدفوعاتك ويرشدك للصفحة الصحيحة، لكنه لا
يستثمر ولا يودع ولا يسحب نيابةً عنك أبدًا.""",
    ),
    (
        "wallet-deposits-withdrawals",
        "المحفظة والإيداع والسحب",
        "payments",
        40,
        """تحتفظ محفظتك بالرصيد المتاح وأي مبلغ محجوز (مثل سحب قيد المعالجة). الإيداع: مدفوعات
البطاقة والعملات الرقمية تُقيَّد تلقائيًا عند تأكيد مزوّد الدفع؛ أما التحويل البنكي فيجب مطابقته
مع المرجع المعروض في صفحة الإيداع ويقيّده الفريق بعد المراجعة.
العملات الرقمية: تختار العملة وشبكتها على PropShare أولًا، وصفحة الدفع التي تُفتح تطلب هذه
العملة وحدها على عنوان واحد وبمبلغ محدد. أرسل العملة نفسها على الشبكة نفسها. مسح رمز QR أو نسخ
العنوان أو ربط المحفظة في تلك الصفحة كلها تحويل واحد ويُرصد تلقائيًا. يمكنك إغلاق الصفحة بعد
الإرسال: يعرض أعلى المحفظة الدفعة على أنها في الطريق، وتُقيَّد عند تأكيد الشبكة (عادةً خلال دقائق)
مع إشعار. التحويل الذي يصل ناقصًا، أو بعملة أو شبكة أخرى استطاع مزوّد الدفع معالجتها، يُقيَّد في
المحفظة بالقيمة التي وصلت (وقد يستغرق وقتًا أطول) ويصلك إشعار بالمبلغ. ودفعة العملات الرقمية
لشراء أو لدفعة مقدمة إذا وصلت ناقصة بفارق واضح لا تُتمّه: تُفرج الوحدات ويذهب ما وصل إلى المحفظة
لتشتري منها. أما النقص الطفيف جدًا (فرق تقريب أو رسوم شبكة) فلا يمنع إتمامها. ولكل عملة حد أدنى
للدفعة يتغيّر مع رسوم شبكتها: يظهر تحت العملة عند اختيارها، والمبلغ الأقل منه لا يُدفع بتلك
العملة (اختر عملة أخرى أو مبلغًا أكبر).
والعملة التي تحتاج memo أو tag يجب إرسالها مع الرقم المعروض في صفحة الدفع.
السحب: احفظ أولًا وجهة المبلغ (المحفظة ← Payment Methods: حساب بنكي باسم البنك وصاحب الحساب
وIBAN أو رقم الحساب وSWIFT والدولة والعملة، أو محفظة كريبتو بالشبكة والعنوان)، والأرقام لا تظهر
إلا بآخر أربعة. يحتاج السحب إلى بريد إلكتروني مؤكَّد وألا يزيد على رصيدك المتاح؛ ويحجز الطلب المبلغ
فورًا ويأخذ رقمًا (WD-...). السحب اليدوي يحوّله فريقنا بنفسه إلى الحساب المحفوظ على الطلب، عادة
خلال يوم إلى يومي عمل: يصلك إشعار وبريد عند التحويل (مع رقم التحويل)، أو بالسبب إن تعذّر التحويل
وعندها يعود المبلغ إلى محفظتك. وإذا كانت المنصة تصرف السحب البنكي تلقائيًا وربطت بنكك مرة واحدة
عبر Stripe من صفحة المحفظة (متاح للحسابات في الولايات المتحدة والمملكة المتحدة والمنطقة
الاقتصادية الأوروبية وكندا وسويسرا)، تختار في شاشة السحب بين "تلقائي" (يُرسل فورًا، ومحدَّد من
البداية) و"يدوي" (حساب بنكي محفوظ يحوّل له الفريق). سحب الكريبتو يدوي. ولكل حركة في المحفظة،
ومنها السحب واسترداده، إيصال PDF برقم: أيقونة التنزيل بجانبها في سجل المحفظة. وحيث يكون السحب
الفوري مفعّلًا،
يمكن أن يصل المبلغ إلى بطاقة خصم مؤهلة خلال دقائق مقابل رسم صغير يُعرض قبل التأكيد ويُخصم من
المبلغ؛ وإن تعذّر الصرف الفوري يُرسل بالسرعة العادية ولا يضيع. ترى كل سحب وسرعته ورسمه وحالته في
المحفظة (Withdrawal requests) برقمه ووجهته وحالته، ويصلك إشعار عند الصرف أو الإرجاع (المبلغ
المرتجع يعود لمحفظتك). وكل مستند تنزّله من المنصة (الشهادات والإيصالات والكشوف وجداول الأقساط)
يأتي باللغة التي تستخدم بها الموقع: الإنجليزية أو العربية أو الفرنسية. ويمكنك تنزيل كشف حساب لأي
فترة تختارها (حتى ثلاث سنوات في المرة) بصيغة PDF أو Excel من بطاقة "كشف الحساب" في صفحة المحفظة:
الرصيد الافتتاحي والختامي، وكل حركة مع الرصيد بعدها، والإجماليات حسب النوع، وحيازاتك في نهاية
الفترة. وللوحدات كشف خاص بها: من لوحة التحكم ← Active Investments ← Unit Movements ← "Download
statement" تنزّل للفترة التي تختارها، بصيغة PDF أو Excel، كل شراء وبيع وتحويل للوحدات مع عدد
الوحدات المملوكة في ذلك العقار بعده، ولكل عقار الوحدات في بداية الفترة ونهايتها. إن بدا دفع متوقفًا،
يستطيع المساعد عرض حالته الحالية وفتح تذكرة دعم بالمرجع ليتابعها شخص من الفريق.""",
    ),
    (
        "fees-overview",
        "الرسوم الموجودة وأين تراها",
        "fees",
        50,
        """كل رسوم المستثمر تُعرض قبل التأكيد وتُدرج في ملخص الدفع، فالإجمالي الذي تراه هو ما
تدفعه. أنواع الرسوم في المنصة:
- رسوم منصة عند شراء الوحدات، تُضاف على سعر الوحدات؛
- رسوم إدارة سنوية على العقارات المدرّة للدخل، تُخصم قبل التوزيعات؛
- رسوم إعادة بيع على صفقة السوق الثانوي، يدفعها المشتري فوق السعر (البائع يستلم السعر كاملًا)؛
  وعند بيع مركز أقساط تُحسب على المبلغ الذي يدفعه المشتري للبائع؛
- رسوم أقساط على الخطط، تُضاف للدفعة الأولى ولكل قسط وتظهر في الجدول؛
- خصم/رسوم سوق السيولة عند الخروج الفوري عبر مزوّد سيولة.
بعض العقارات أو البرامج تحمل خصمًا (مثل إعادة استثمار التوزيعات). النسب الحالية إعدادات في
المنصة: يقرأها المساعد مباشرة (get_platform_settings) وتعرضها صفحة الرسوم وكل عملية شراء. سجل
الرسوم ظاهر في معاملاتك.""",
    ),
    (
        "returns-and-distributions",
        "العوائد والتوزيعات",
        "returns",
        60,
        """في العقارات المدرّة للدخل يُوزَّع صافي دخل الإيجار (بعد تكاليف التشغيل ورسوم الإدارة)
على الملاك بنسبة وحداتهم ويُقيَّد في محافظهم. تعرض محفظتك كل توزيع وإجمالي عوائدك، وصفحة
التقارير تحوي السجل. العوائد المتوقعة أو المستهدفة في صفحة العقار توقعات من المطوّر أو المنصة
وليست وعودًا: التوزيعات الفعلية تعتمد على دخل الإيجار الحقيقي. لا أحد في المنصة، بما فيه المساعد،
يضمن عائدًا.""",
    ),
    (
        "exit-options",
        "كيف تخرج: السوق الثانوي وسوق السيولة",
        "exit",
        70,
        """لست مقيّدًا بعقار حتى يُباع: يمكنك عرض ما تملكه للبيع في أي وقت، سواء كان العقار جاهزًا أو
ما زال تحت الإنشاء (قد توجد فترة حظر بعد الشراء). يوجد مساران للخروج:
- السوق الثانوي: تعرض بعض وحداتك أو كلها بسعر تحدده؛ يشتريها مستثمر آخر وتنتقل الوحدات عند دفع
  المشتري. سعر الوحدة الحالي للعقار هو السعر الاسترشادي. الأنسب لأقصى قيمة عندما لا تكون
  مستعجلًا. يمكنك إلغاء عرض لم يُبَع.
- سوق السيولة: تطلب الخروج بالسعر الذي تحدده المنصة (سعر الوحدة الحالي ناقص خصم ورسوم) ويموّله
  مزوّد سيولة، عادةً أسرع من انتظار مشترٍ.
الوحدات التي تسددها بخطة أقساط ما زالت جارية تنتقل مع أقساطها: يمكنك بيع الخطة كلها أو بعض
وحداتها (وحدة أو اثنتين أو أي عدد)، في السوق الثانوي أو لمزوّد سيولة، أو إرسالها لشخص آخر. يدفع
لك المشتري أصل ما سددته على هذه الوحدات (رسوم التقسيط التي دفعتها لا تُرد) مضافًا إليه زيادة
سعر الوحدة عليها، ثم يكمل هو نصيبها من كل قسط متبقٍ في موعده. وإذا انخفض سعر الوحدة يُخصم
الانخفاض بدل الزيادة. مثال: خطة لوحدات قيمتها ألف، سُدِّد منها مئتان؛ ارتفع سعر الوحدة بمقدار
العُشر فصارت قيمة المركز ألفًا ومئة؛ عند بيع الخطة كلها يدفع لك المشتري ثلاثمئة (المئتان
اللتان سددتهما والمئة التي زادت) ثم يسدد الثمانمئة المتبقية حسب الجدول. وبيع ثلاث وحدات من عشر
هو ثلاثة أعشار كل شيء: يدفع لك المشتري ثلاثة أعشار ذلك، وتصير له خطة باسمه بنفس المواعيد كل قسط
فيها ثلاثة أعشار قسطك، وتبقى لخطتك سبع وحدات وكل قسط فيها سبعة أعشار. ويمكن للمشتري أيضًا أن
يأخذ بعض الوحدات المعروضة فقط. ولا ينتقل جزء من خطة إلا إذا لم يكن عليها قسط متأخر: سدّده أولًا.
وإذا كنت قد اشتريت الخطة من مستثمر آخر فالمقصود بما سددته هو ما دفعته ثمنًا لها مضافًا إليه
أقساطك بعد ذلك، وتُحسب الزيادة من السعر الذي اشتريت به.
البيع يحتاج مشتريًا: لا ضمان لمشترٍ أو سعر أو موعد. المساران من محفظتك؛ يستطيع المساعد عرض
حيازاتك ومراكزك وعروضك وطلباتك وتجهيز عرض البيع لك، لكن العرض أو البيع أو الطلب تؤكده أنت في
تلك الصفحة.""",
    ),
    (
        "installment-plans",
        "خطط الأقساط",
        "installments",
        80,
        """في العقارات المباعة بالأقساط تدفع دفعة أولى الآن وأقساطًا شهرية بعدها؛ تقدّم المنصة
مجموعة مدد للخطط وتعتمد الدفعة الأولى على المدة المختارة. سعر الوحدة يُثبَّت عند بدء الخطة:
تغيّر سعر وحدة العقار بعد ذلك لا يغيّر جدولك، وأي زيادة هي ربح لك. تُدفع الدفعة الأولى بأي طريقة
دفع في المنصة — المحفظة، أو بطاقة (Apple Pay / Google Pay)، أو عملة رقمية، أو Pronova (خصمها
على الدفعة الأولى)، أو شهادة صكوك نوفا (تبدأ الخطة بعد موافقة فريقنا). يُعرض الجدول الكامل، مع
رسوم الأقساط
على كل دفعة، قبل التأكيد وبعده في المحفظة ← الأقساط. تُخصم الأقساط من محفظتك تلقائيًا في
مواعيدها، ويصلك تذكير قبل كل قسط بأيام. إذا لم يكفِ رصيد المحفظة يوم الاستحقاق يُسجَّل القسط
متأخرًا ويُعاد خصمه تلقائيًا عند توفر الرصيد: لا توجد غرامة تأخير ولا تُسحب منك وحداتك. احرص على
شحن محفظتك قبل موعد الاستحقاق. ويمكنك أيضًا دفع القسط التالي مبكرًا؛ يستطيع المساعد عرض خططك
وجدولك وتجهيز هذه الدفعة.
وحدات الخطة الجارية تبقى مع أقساطها: يمكنك بيع الخطة كلها أو بعض وحداتها في أي وقت (انظر
«كيف تخرج»): يدفع لك المشتري ما سددته عليها مضافًا إليه زيادة السعر ويكمل هو نصيبها من الأقساط
المتبقية كخطة باسمه، وتبقى لخطتك بقية الوحدات وكل قسط فيها أقل بقدر الجزء المبيع. ويمكن أيضًا أن
تنتقل وحدات الخطة إلى مزوّد سيولة أو، من «التحويلات»، إلى شخص آخر يسدد نصيبها من الأقساط. صفحة
الأقساط تعرض قيمة مركزك اليوم.""",
    ),
    (
        "kyc-verification",
        "التحقق من الهوية (KYC)",
        "kyc",
        90,
        """التحقق مطلوب قبل الاستثمار أو السحب، التزامًا بقواعد مكافحة غسل الأموال. يتم من صفحة
الحساب عبر مزوّد التحقق في المنصة: وثيقة هوية وصورة شخصية. الحالات: معلّق (لم يبدأ أو قيد
التنفيذ)، تم التحقق، مرفوض (مع السبب في صفحة الحساب ويمكنك إعادة الإرسال)، ومراجعة يدوية (شخص
يراجع طلبك وسيصلك إشعار). يستطيع المساعد إخبارك بحالتك الحالية وسببها وإرشادك لصفحة التحقق، لكنه
لا يستطيع التحقق منك ولا تغيير قرار. إن تعطّل طلبك، اطلب من المساعد فتح تذكرة دعم.""",
    ),
    (
        "secondary-market-rules",
        "قواعد التداول في السوق الثانوي",
        "rules",
        100,
        """عند بيع أو شراء الوحدات بين المستثمرين: اعرض بسعر عادل ضمن نطاق أسعار المنصة، التزم
بالعروض المقبولة، احتفظ برصيد كافٍ في المحفظة للتسوية، وادفع الرسوم المعروضة عند التأكيد. التلاعب
بالأسعار والتداول الوهمي وافتعال الأحجام ممنوعة وتؤدي إلى الإيقاف. قد توجد فترة حظر قبل إمكانية
عرض الوحدات؛ يوضح نموذج البيع موعد انتهائها. مركز خطة الأقساط الجارية يُعرض كاملًا أو جزءًا منه،
ويمكن للمشتري أخذ كل الوحدات المعروضة أو بعضها: قبل الشراء يرى المشتري عدد الوحدات وما يدفعه
للبائع الآن والأقساط التي يتولاها بتواريخها ومبالغها؛ يؤكد المشتري ذلك المبلغ، ويستلم الوحدات
كخطة (الخطة نفسها، أو خطة باسمه بنفس المواعيد)، ويسدد أقساطها من محفظته في مواعيدها.""",
    ),
    (
        "platform-rules",
        "قواعد المنصة باختصار",
        "rules",
        110,
        """قدّم معلومات صحيحة عند التسجيل والتحقق وكل معاملة؛ أكمل التحقق قبل الاستثمار أو السحب؛
استخدم المنصة لأغراض استثمار مشروعة فقط؛ احترم الحد الأدنى للاستثمار وحدود كل إدراج وفترات الحظر
وإجراءات الخروج؛ لا تنشئ حسابات متعددة ولا تنتحل صفة غيرك ولا تجمع البيانات آليًا ولا تحاول تجاوز
الحماية. قد تؤدي المخالفات إلى الإيقاف أو عكس المعاملات أو حجز الأموال أثناء التحقيق أو إجراءات
قانونية أو إبلاغ الجهات. الشبهات والاحتيال والمسائل القانونية تذهب لفريق الامتثال عبر تذكرة دعم
عالية الأولوية، لا إلى المساعد.""",
    ),
    (
        "spv-structure",
        "هيكل الـ SPV وماذا يحدث لو توقفت المنصة",
        "legal",
        120,
        """كل عقار تملكه شركة ذات غرض خاص (SPV) مستقلة، أُنشئت لهذا العقار وحده. تحمل الـ SPV
الملكية، وتصدر الحصص الجزئية، وتستلم الدخل أو عوائد البيع وتوزّعها. ولأن الأصول والالتزامات مفصولة
لكل SPV، فمشكلة في عقار لا تؤثر على آخر، وأموال المستثمرين ليست جزءًا من ميزانية المنصة أبدًا. لو
توقفت المنصة عن العمل تبقى الـ SPV وحقوق ملكيتك قائمة: يمكن تعيين مدير جديد، أو استمرار توزيع
الدخل، أو بيع الأصل وتوزيع العوائد. تُحل النزاعات وفق قانون اختصاص الـ SPV كما تنص الاتفاقيات.
مستندات الـ SPV والعقار متاحة في صفحة كل عقار.""",
    ),
    (
        "family-and-brokers",
        "مجموعات العائلة وإحالات الوسطاء",
        "roles",
        130,
        """مجموعة العائلة: يستطيع العضو إنشاء مجموعة عائلية وإضافة أقاربه وتحويل وحداته هو إليهم
وتخصيص العوائد داخل المجموعة. يصل الطرفين إشعار داخل المنصة ورسالة بالبريد في كل مرة. يعرض تبويب
"استثمار العائلة" نشاط كل عضو من جهته (الأعضاء المضافون، والوحدات والعوائد المحوّلة أو المخصّصة
بتواريخها)، فيرى القريب الذي استلم فقط ما وصله هناك أيضًا، ويعرض تبويب "الاستثمارات النشطة" كل
حركة على الوحدات مع اسم الطرف الآخر. الوحدات أو العوائد المخصّصة لقريب ليس له حساب موثّق بعد تبقى
محجوزة له إلى أن يسجّل بذلك البريد الإلكتروني ويؤكّد البريد ويوثّق هويته. تأكيد البريد مهم: ما
يُرسل لشخص بعنوان بريده (تخصيص عائلي أو هدية) لا يصل إلى الحساب المسجّل بذلك العنوان إلا بعد أن
يؤكّده الحساب. رابط التأكيد يُرسل بالبريد عند التسجيل ويعمل من داخل الحساب (سجّل الدخول أولًا ثم
افتحه)، ويمكن طلب رابط جديد من إعدادات الحساب أو من المساعد، وتعيين كلمة مرور جديدة عبر "نسيت كلمة
المرور" يؤكّد البريد أيضًا. يعرض المساعد مجموعتك وتخصيصات أعضائها (ولا يعرض وثائق هوياتهم أبدًا).
الوسطاء: للوسيط المعتمد كود إحالة؛ المستثمرون الذين يسجلون به يُربطون بالوسيط. عندما يستثمر هذا العميل
يحصل الوسيط على نسبة من مبلغ الاستثمار تدفعها المنصة (ولا يدفع العميل شيئًا إضافيًا): لكل عقار أن تكون له
نسبته، وإلا تُطبَّق النسبة العامة، وفي خطة الأقساط تُحتسب على كل دفعة. يعرض تبويب العمولات لدى الوسيط نسبة
كل عقار وكل عمولة حصل عليها. في لوحة الوسيط تبويب "الإدراجات
والإحالات" يعرض كل ما قدّمه الوسيط وحالته: "إضافة عميل" يرسل للشخص رابط الوسيط بالبريد (ولا يُربط به
إلا إذا سجّل من الرابط)، و"إضافة عقار" / "إضافة مشروع" لتقديم عقار أو مشروع على الخريطة مع بيانات
المالك أو المطوّر ومستنداته ليراجعه الفريق (يتواصل معه ويدرجه أو يوضح السبب، والتقديم وحده لا
يستحق عمولة). التقدم لدور الوسيط أو المالك أو مزوّد السيولة يتم من الحساب ← الأدوار ويراجعه
الفريق.""",
    ),
    (
        "beneficiaries-and-claims",
        "المستفيدون وشهادتهم والمطالبة بعد وفاة صاحب الحساب",
        "roles",
        135,
        """تسمية المستفيدين: يسمّي صاحب الحساب الأشخاص الذين تؤول إليهم حيازاته من لوحة المستثمر ←
استثمار العائلة ← المستفيدون والميراث. يسجّل لكل شخص الاسم الكامل كما في وثيقة هويته، وصلة
القرابة، والصفة (مستفيد، وريث، شخص مفوّض أو ممثل قانوني)، ونوع وثيقة الهوية ورقمها، والحصة المخصّصة
له؛ ولا يتجاوز مجموع حصص الجميع الكل. يستطيع صاحب الحساب رفع صورة من وثيقة هوية الشخص (صورة أو
ملف PDF) لتُحفظ مع سجله، وتعديل السجل أو حذفه في أي وقت، وتنزيل شهادة لكل شخص. تحمل الشهادة شعار
المنصة وبيانات الشخص كما سُجّلت ورقم الشهادة وإصدارها (كل تعديل على السجل يصدر إصدارًا جديدًا،
والأحدث هو المعتمد) ومكان تقديم المطالبة. تصدر الشهادة بلغة الموقع، وتذكر الاسم بالحروف
اللاتينية كما في جواز السفر، فيُكتب الاسم بالحروف اللاتينية، ويلزم لها رقم وثيقة الهوية.
وهي سجل لرغبة صاحب الحساب وليست وصية. ولا يعرض المساعد
وثائق الهوية ولا أرقامها أبدًا.

ما تشمله الحصة: حصة الشخص من وحدات صاحب الحساب مشمولة دائمًا، وتتبعها عوائدها القادمة. وإذا اختار
صاحب الحساب لذلك الشخص "Wallet Balance" (رصيد المحفظة) أو "Full Portfolio" (المحفظة الكاملة)
انتقلت معها النسبة نفسها من رصيد محفظته يوم التحويل (بعد خصم العوائد التي كان قد خصّصها لأقاربه).
أما الوحدات المحجوزة يومها (المعروضة للبيع، أو في طلب خروج، أو في هدية مجدولة، أو المكتسبة ضمن
خطة تقسيط جارية) وخطط التقسيط فلا تدخل في ذلك، ويتولاها الفريق عند الطلب. وشرط التحويل الذي
اختاره صاحب الحساب (مثل "عند الوفاة الموثّقة" أو "بعد 12 شهرًا من عدم النشاط") تسجيل لرغبته: لا
يُحوَّل شيء تلقائيًا أبدًا، وإنما بمطالبة يراجعها الفريق.

المطالبة: بعد وفاة صاحب الحساب، أو إذا لم يعد قادرًا على إدارة حسابه، يفتح الشخص المسمّى الصفحة
العامة "الإبلاغ عن وفاة أو تقديم مطالبة" (في قائمة الموقع تحت "المساعدة" وفي صفحة الدعم)
ويرسل اسمه ودولته وبيانات التواصل،
واسم صاحب الحساب، والسبب وتاريخ الوفاة، والشهادة ورقمها، وصورة من وثيقة هويته هو، والمستند
الرسمي إن توفّر (شهادة الوفاة في حالة الوفاة). يصله رقم مرجعي للمطالبة بالبريد. يراجع الفريق
المطالبة مقارنةً بسجل صاحب الحساب، وقد يطلب مستندات إضافية، ثم يقرّر. تُحوَّل الأصول فقط إلى حساب
المطالِب نفسه على كابي مكس بروبشير بعد توثيق هويته فيه، ولذلك يلزمه حساب خاص به؛ ولا يُعطى أحدٌ
حساب صاحب الحساب ولا كلمة مروره ولا سجلاته أبدًا. يقدّم كل شخص مسمّى مطالبته عن حصته هو. المطالِب
المسجّل دخوله يرى مطالباته وحالتها في الصفحة نفسها ويستطيع إضافة مستند طلبه الفريق. أما المطالبة
المرسلة قبل تسجيل الدخول فتظهر هناك وتُربط بحساب المطالِب بعد أن يكون الحساب بالبريد الإلكتروني
نفسه ويُؤكَّد هذا البريد (يمكن طلب رابط تأكيد جديد من الصفحة نفسها أو من إعدادات الحساب). وعند
الموافقة على أول مطالبة على حساب، يُغلق سجل المستفيدين لذلك الحساب ولا يمكن تعديله بعدها؛ وإذا
كانت المطالبة بسبب الوفاة أو لأن صاحب الحساب لم يعد قادرًا على إدارته، أُغلق الحساب نفسه: لا يمكن
تسجيل الدخول إليه، وما بقي فيه ينتظر بقية المطالبات. يُبلَّغ بريد صاحب الحساب بذلك ليعترض إن كان
موجودًا، ويستطيع الفريق إعادة فتح الحساب. ومن ليست لديه شهادة يتواصل مع الدعم.""",
    ),
    (
        "support-and-the-assistant",
        "ما يستطيع المساعد فعله، وكيف تصل إلى شخص",
        "support",
        140,
        """يجيب المساعد من معلومات المنصة المعتمدة ومن بيانات حسابك الحيّة. يستطيع عرض الأرصدة
والحالات والاستثمارات والخطط والحيازات والإشعارات والتذاكر؛ وشرح كيف تعمل الأمور؛ وإعطاءك الصفحة
المطلوبة تحديدًا؛ وبتأكيدك: إعادة إرسال رسالة التفعيل، أو تعليم الإشعارات كمقروءة، أو تعديل
تفضيلات الإشعارات، أو إلغاء عرض لم يُبع في السوق الثانوي، أو إلغاء طلب خروج معلّق في سوق السيولة،
أو إلغاء هدية عائلية مجدولة، أو فتح تذكرة دعم. لا يحرّك مالًا أبدًا، ولا يغيّر إعدادات الأمان مثل
كلمة المرور أو التحقق بخطوتين، ولا يقدّم نصيحة استثمارية شخصية. عندما لا يستطيع الإجابة
يسجّل السؤال للفريق ويعرض رابط الدعم. تذاكر الدعم يتابعها شخص؛ يمكنك رؤية تذاكرك والرد عليها من
صفحة الدعم، ويصلك إشعار بكل رد.""",
    ),
    (
        "account-security-2fa",
        "أمان الحساب والتحقق بخطوتين",
        "account",
        150,
        """يمكنك حماية حسابك بالتحقق بخطوتين (2FA) من إعدادات الحساب ← الأمان. امسح رمز QR بتطبيق
مصادقة (Google Authenticator أو Microsoft Authenticator أو Authy أو ما يشبهها)، واكتب الرمز
المكوّن من ستة أرقام للتأكيد، واحفظ رموز الاسترداد التي تظهر مرة واحدة فقط: كل رمز منها يعمل مرة
واحدة إن فقدت هاتفك. بعد ذلك يطلب منك الدخول بكلمة المرور أو بحساب Google الرمز الحالي من
التطبيق. عدة رموز خاطئة متتالية توقف الخطوة الثانية لفترة قصيرة. يمكنك إيقاف التحقق بخطوتين أو
إنشاء رموز استرداد جديدة من الصفحة نفسها بعد إدخال رمز حالي. إن فقدت هاتفك ورموز الاسترداد معًا
افتح تذكرة دعم: بعد أن يتحقق الفريق من هويتك يستطيع المسؤول إعادة ضبط التحقق بخطوتين لتفعّله من
جديد. يستطيع المساعد إخبارك هل التحقق بخطوتين مفعّل أم لا، لكنه لا يفعّله ولا يوقفه أبدًا ولا يطلب
منك رمزًا أو كلمة مرور.""",
    ),
    (
        "developers-and-verification-center",
        "صفحات المطوّرين والتحقق من المستندات",
        "basics",
        160,
        """تذكر كل صفحة عقار اسم المطوّر؛ وزر "عرض الملف" يفتح صفحة المطوّر العامة بما سجّلته المنصة
عنه (نبذة، الموقع الإلكتروني، سجل الأعمال، التحققات) وعقاراته المعروضة حاليًا على المنصة. تُنزَّل
شهادات الاستثمار من تبويب الشهادات، ولكل شهادة رقم ورمز تحقق ورمز QR، ويعرضها تبويب "مركز
التحقق" في لوحة المستثمر لكل شهادة لديك.

توضّح صفحة مركز التحقق أين يُتحقق من كل نوع من السجلات:
- شهادات الاستثمار من Capimax PropShare يُتحقق منها على بروبشير نفسها: امسح رمز QR المطبوع على
  الشهادة بكاميرا هاتفك فتفتح صفحة التحقق الخاصة بها، وتعرض هل هي أصلية وحالتها الحالية (سارية، أو
  حلّت محلها شهادة أحدث، أو ملغاة) مع ما تثبته. لا يمكنك المسح؟ أدخل رمز التحقق المطبوع بجانب رمز
  QR في مركز التحقق. تثبت الشهادة الوحدات التي كانت لديك يوم إصدارها: إذا تغيّرت، تثبت شهادتك
  التالية العدد الجديد وتظهر القديمة على أن شهادة أحدث حلّت محلها.
- مستندات التقييم والمستندات المالية (تقارير تقييم العقارات والوحدات، دراسات الاستثمار، التحليلات
  المالية، السجلات المحاسبية والتقارير المالية، تقارير العناية الواجبة): CIM Global Financial
  (https://www.cimglobalfinancial.com/capimax-verify). أدخل رقم المستند أو معرّف التحقق.
- شهادات التأمين: CoverTech Insurance (https://www.covertechinsurance.com/capimax-ecosystem)
  لتأكيد صحة الشهادة وبيانات التغطية وحالتها الحالية.
- المستندات القانونية والاتفاقيات: مركز مستندات LexCrest Global
  (https://lexcrestlegal.xyz/document-center). أدخل رقم المستند الفريد المكتوب عليه؛ وحيثما
  يُسمح، يمكن معاينة المستندات العامة أو تنزيلها.
- سجلات البلوك تشين والعقود الذكية والأصول المرمّزة والشهادات الرقمية لمنصات المنظومة القائمة على
  البلوك تشين (وليس بروبشير): Proof Anchor (https://www.proofanchor.io/verify). ابحث برقم الشهادة
  أو رقم التحقق أو عنوان العقد أو عنوان التوكن أو معرّف الأصل أو اسم المشروع.
وبوابة Capimax Trust متاحة من الصفحة نفسها.""",
    ),
    (
        "capimax-ecosystem-and-partners",
        "بروبشير داخل منظومة كابي مكس وشركاؤها",
        "basics",
        5,
        """كابي مكس بروبشير هي منصة المنظومة الرقمية غير القائمة على البلوك تشين للمشاركة الجزئية في
العقارات، وتركّز على المشروعات على الخارطة وتحت الإنشاء والمحافظ المرتبطة بها. الوحدات حصص
مشاركة تعاقدية مسجّلة رقميًا تدعمها شركة الغرض الخاص لكل عقار والاتفاقيات وسجل الملاك، وليست
عملات رقمية. المنصات الشقيقة: Capimax Assets (عقارات جاهزة ومدرّة للدخل بصيغة غير مرمّزة)،
وCapimax BRX وCapimax RT (المساران المرمّزان المستقلان في المنظومة)، وCapimax Group وCapimax One
(المظلة المؤسسية وبوابة الاكتشاف)، وCapimax Pro مع CPV (التحقق من العقارات والمستندات)، ونوفا
ديجيتال فاينانس (التمويل، منفصل عن الملكية)، وبرونوفا / PRN (مشروع أصول رقمية منفصل، ليس حصة في
أي عقار). الشركاء حسب الدور: المدفوعات (Stripe وPayPal وNOWPayments)، الهوية والامتثال (Sumsub)،
الخدمات البنكية (Mercury وRevolut Business وWise Business)، الدراسات المالية والتقييم (CIM Global
Financial)، القانوني (LexCrest Global Legal)، التأمين (CoverTech وAssurax)، المطورون (Westoria
Capital Estates وCrestmark Global وValora Estates Global وVerdea Estates وAethera Development
وElevate Properties وPrime Stone Global)، والتشغيل (Priminn Hotels وElite Gate Properties وCrown
Facilities). التفاصيل ودور كل جهة والروابط الرسمية في مكتبة المراجع.""",
    ),
    (
        "transfers-and-messages",
        "التحويل لشخص آخر، ورسائل فريق المنصة",
        "payments",
        135,
        """التحويلات: يستطيع المستثمر أن يرسل وحدات من عقار يملكه أو مبلغًا من محفظته لأي شخص ببريده
الإلكتروني: من لوحة التحكم ← التحويلات (تحويل وحدات / تحويل رصيد)، أو زر "تحويل" في المحفظة. يتطلب
الإرسال بريدًا مؤكّدًا وهوية موثّقة. يطلب النموذج بريد المستلم (واسمه اختياريًا) وما يُرسل وتاريخ
التسليم (اليوم أو حتى سنة قادمة) ورسالة اختيارية؛ وتعرض خطوة المراجعة ما سيُرسل وقيمته ورسوم التحويل
(صفر ما لم تحددها المنصة) وما سيُخصم من المحفظة الآن، ولا يُرسل شيء قبل الضغط على "تأكيد وإرسال".
لكل تحويل رقم يبدأ بـ TR- يليه عشرة أحرف.
يُحجز ما يُرسل فورًا: تُجنّب الوحدات من الملكية (فلا تُعرض للبيع ولا لمزوّد السيولة ولا تُرسل مرتين)،
ويُخصم المبلغ والرسوم من المحفظة. لا يُرسل إلا الوحدات الحرة: الوحدات المعروضة للبيع أو المحجوزة لغرض
آخر أو المرهونة أو المرتبطة بخطة تقسيط جارية لا يمكن إرسالها. إذا كان بريد المستلم مؤكّدًا وهويته
موثّقة يصله التحويل فورًا (أو في التاريخ المختار): تظهر الوحدات في ملكيته والمبلغ في محفظته، ويصل
الطرفين إشعار وبريد. وإن لم يكن، يصله بريد دعوة ويستلم التحويل فور تسجيله بنفس البريد وتأكيده وتوثيق
هويته؛ وإن لم يفعل خلال 30 يومًا يعود كل شيء للمرسل ومعه الرسوم. يستطيع المرسل إلغاء تحويل لم يُسلَّم
بعد من تبويب التحويلات فيعود إليه كل شيء، أما التحويل المُسلَّم فلا يمكن استرجاعه.
يعرض تبويب التحويلات كل تحويل مرسل ومستلم برقمه وحالته (مجدول، بانتظار المستلم، تم التسليم، أُلغي /
انتهت المهلة / تعذّر التسليم - أُعيد) وتواريخه، ويظهر نفس رقم TR- في كشف المحفظة وإيصالاتها وفي حركات
الوحدات. والهدايا تعمل بنفس الطريقة الآن: الهدية التي تنتظر مستلمها يمكن إلغاؤها، وتعود للمُهدي إن لم
تُستلم خلال 30 يومًا.
الرسائل: يكتب فريق Capimax PropShare للأعضاء من لوحة الإدارة، لعضو واحد أو لكل من يحمل دورًا معينًا
(المستثمرون، ملاك العقارات والمطوّرون، الوسطاء، مزوّدو السيولة، أو الجميع). تصل في صفحة "الرسائل" (في
القائمة، /messages) وكإشعار وبالبريد. يمكن إيقاف بريد الرسائل الموجّهة للجميع من إعدادات الحساب ←
الإشعارات ← الإعلانات، وتظل تصل في صفحة الرسائل، أما الرسالة الموجّهة لعضو بعينه فتصله
بالبريد دائمًا.""",
    ),
]


async def _seed(approve_as: str | None) -> int:
    created = 0
    async with session_scope() as session:
        actor = None
        if approve_as:
            user = await auth_service.get_user_by_email(session, approve_as)
            if user is None or "admin" not in await auth_service.get_roles(session, user.id):
                print(f"refusing: {approve_as} is not an admin", file=sys.stderr)
                return 2
            actor = user.id
        for lang, articles in (("en", ARTICLES), ("ar", ARTICLES_AR)):
            for slug, title, category, priority, body in articles:
                body = body.strip()
                latest = await session.scalar(
                    select(KbArticle)
                    .where(KbArticle.slug == slug, KbArticle.lang == lang)
                    .order_by(KbArticle.version.desc())
                    .limit(1)
                )
                if latest is not None and latest.body_md.strip() == body and latest.title == title:
                    row = latest
                else:
                    row = await kb_service.upsert_draft(
                        session,
                        slug=slug,
                        lang=lang,
                        title=title,
                        body_md=body,
                        category=category,
                        priority=priority,
                        source_ref="seed_kb.py",
                    )
                    created += 1
                if actor is not None and row.status == "draft":
                    await kb_service.approve(session, article_id=row.id, actor_id=actor)
    total = len(ARTICLES) + len(ARTICLES_AR)
    print(f"seed_kb: {created} new draft version(s); {total} articles total (en + ar)")
    return 0


def main(argv: list[str]) -> int:
    approve_as = None
    if "--approve-as" in argv:
        approve_as = argv[argv.index("--approve-as") + 1]
    return asyncio.run(_seed(approve_as))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
