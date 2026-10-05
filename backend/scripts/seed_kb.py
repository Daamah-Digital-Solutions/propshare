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
   (you pick the coin on NOWPayments' page), Pronova (a discount off what you pay now) or a
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
Withdrawals: a request holds the amount immediately. Depending on how the platform is set up
for each method (the assistant reads this live), a withdrawal is either paid automatically
through the payment provider as soon as you request it, or reviewed and paid by the team.
Automatic bank withdrawals go to a bank account you link once through Stripe from the wallet
page (available for accounts in the US, UK, EEA, Canada and Switzerland). Where instant
payouts are switched on, an eligible debit card can receive the money within minutes for a
small fee that is shown before you confirm and deducted from the amount; if an instant payout
cannot go through it is sent at standard speed instead, never lost. You see every withdrawal,
its speed, fee and status in your wallet and are notified when it is paid or rejected
(rejected funds return to your wallet). An account statement for any period you choose (up to
three years at a time) can be downloaded as a PDF or an Excel file from the Account statement
card on the wallet page: opening and closing balance, every movement with a running balance,
totals by type and your holdings at the end of the period. If a payment looks stuck, the
assistant can show its current status and open a support ticket with the reference for a
person to follow up.""",
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
Units you are paying for through an installment plan that is still running are sold with the
plan, whole, as one position on the secondary market: the buyer pays you the principal you
have paid (the instalment fees you paid are not returned) plus the increase in the unit price
on all the plan's units, and takes over the remaining instalments on their dates. If the unit
price has fallen, the decrease is taken off instead. Example: a plan for units worth one
thousand, with two hundred
paid; the unit price has risen by a tenth, so the position is worth eleven hundred; the buyer
pays you three hundred (the two hundred you paid plus the hundred gained) and then pays the
remaining eight hundred as the schedule says. If you took the plan over from another investor,
what you have paid means what you paid for it plus your own instalments since, and the
increase is counted from the price you bought it at.
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
The units of a running plan stay with the plan: they are not listed one by one, but you can
sell the whole plan as a position at any time (see "How to exit"): the buyer pays you what you
paid plus the price increase and carries on with the remaining instalments. Your Installments
page shows what the position is worth today.""",
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
listed and bought whole: the listing shows its price, what has been paid and the remaining
instalments with their dates; the buyer confirms the amount paid to the seller, takes the plan
over and pays those instalments from their wallet on their dates.""",
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
        """Family group: one member can create a family group, add relatives, transfer units to
them and allocate returns within the group; the assistant shows your group and its members'
allocations (never their identity documents). Brokers: an approved broker has a referral code;
investors who sign up with it are linked to the broker, who earns a share of the platform's
fees on their activity (never a share of the investment itself). The broker dashboard's
"Listings & Referrals" tab lists everything the broker brought, with its status: "Add client"
emails the person the broker's link (they are linked only if they sign up through it), and
"Add property" / "Add project" introduces a property or an off-plan project with the owner or
developer contact and documents for the team to review (the team contacts them and lists it,
or explains why not; an introduction alone earns no commission). Applying for the broker,
owner or liquidity-provider role is done from Account -> Roles and reviewed by the team.""",
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
the Certificates tab; each one carries a reference, and the Verification tab of the investor
dashboard lists the reference of every certificate you hold.

PropShare verifies nothing itself: the Verification Center page links to the ecosystem's
designated verification partners, each for one kind of record.
- Capimax documents and investment certificates: CIM Global Financial's Capimax Verify
  (https://www.cimglobalfinancial.com/capimax-verify). Enter the verification, record or
  certificate number (for a PropShare certificate, the reference printed on it), or scan the
  QR code, to confirm authenticity and the current status.
- Valuation and financial documents (valuation reports, investment studies, financial
  analyses, accounting and financial reports, due diligence reports): CIM Global Financial,
  same link. Enter the document number or verification ID.
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
   التي تدعمهما)، أو عملة رقمية (تختار العملة من صفحة NOWPayments)، أو Pronova (خصم على ما
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
السحب: يحجز الطلب المبلغ فورًا. وحسب إعداد المنصة لكل وسيلة (يقرؤه المساعد مباشرة) إمّا أن يُصرف
السحب تلقائيًا عبر مزوّد الدفع لحظة طلبه، أو يراجعه الفريق ويصرفه. السحب البنكي التلقائي يذهب إلى
حساب بنكي تربطه مرة واحدة عبر Stripe من صفحة المحفظة (متاح للحسابات في الولايات المتحدة
والمملكة المتحدة والمنطقة الاقتصادية الأوروبية وكندا وسويسرا). وحيث يكون السحب الفوري مفعّلًا،
يمكن أن يصل المبلغ إلى بطاقة خصم مؤهلة خلال دقائق مقابل رسم صغير يُعرض قبل التأكيد ويُخصم من
المبلغ؛ وإن تعذّر الصرف الفوري يُرسل بالسرعة العادية ولا يضيع. ترى كل سحب وسرعته ورسمه وحالته في
المحفظة ويصلك إشعار عند الصرف أو الرفض (المبلغ المرفوض يعود لمحفظتك). ويمكنك تنزيل كشف حساب لأي
فترة تختارها (حتى ثلاث سنوات في المرة) بصيغة PDF أو Excel من بطاقة "كشف الحساب" في صفحة المحفظة:
الرصيد الافتتاحي والختامي، وكل حركة مع الرصيد بعدها، والإجماليات حسب النوع، وحيازاتك في نهاية
الفترة. إن بدا دفع متوقفًا،
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
الوحدات التي تسددها بخطة أقساط ما زالت جارية تُباع مع الخطة كلها كمركز واحد في السوق الثانوي:
يدفع لك المشتري أصل ما سددته (رسوم التقسيط التي دفعتها لا تُرد) مضافًا إليه زيادة سعر الوحدة
على كل وحدات الخطة، ثم يكمل هو الأقساط المتبقية في مواعيدها. وإذا انخفض سعر الوحدة يُخصم
الانخفاض بدل الزيادة. مثال: خطة لوحدات قيمتها ألف، سُدِّد منها مئتان؛ ارتفع سعر الوحدة بمقدار
العُشر فصارت قيمة المركز ألفًا ومئة؛ يدفع لك المشتري ثلاثمئة (المئتان اللتان سددتهما والمئة
التي زادت) ثم يسدد الثمانمئة المتبقية حسب الجدول. وإذا كنت قد اشتريت الخطة من مستثمر آخر
فالمقصود بما سددته هو ما دفعته ثمنًا لها مضافًا إليه أقساطك بعد ذلك، وتُحسب الزيادة من السعر
الذي اشتريت به.
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
وحدات الخطة الجارية تبقى مع الخطة: لا تُعرض وحدةً وحدة، لكن يمكنك بيع الخطة كلها كمركز واحد في
أي وقت (انظر «كيف تخرج»): يدفع لك المشتري ما سددته مضافًا إليه زيادة السعر ويكمل هو الأقساط
المتبقية. صفحة الأقساط تعرض قيمة مركزك اليوم.""",
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
عرض الوحدات؛ يوضح نموذج البيع موعد انتهائها. مركز خطة الأقساط الجارية يُعرض ويُشترى كاملًا:
يوضح العرض سعره
والمسدَّد منه والأقساط المتبقية بتواريخها؛ يؤكد المشتري المبلغ الذي يدفعه للبائع، ويستلم الخطة،
ويسدد تلك الأقساط من محفظته في مواعيدها.""",
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
        """مجموعة العائلة: يستطيع عضو إنشاء مجموعة عائلية وإضافة أقاربه وتحويل وحدات إليهم وتخصيص
العوائد داخل المجموعة؛ يعرض المساعد مجموعتك وتخصيصات أعضائها (ولا يعرض وثائق هوياتهم أبدًا).
الوسطاء: للوسيط المعتمد كود إحالة؛ المستثمرون الذين يسجلون به يُربطون بالوسيط الذي يحصل على نسبة
من رسوم المنصة على نشاطهم (وليس من الاستثمار نفسه أبدًا). في لوحة الوسيط تبويب "الإدراجات
والإحالات" يعرض كل ما قدّمه الوسيط وحالته: "إضافة عميل" يرسل للشخص رابط الوسيط بالبريد (ولا يُربط به
إلا إذا سجّل من الرابط)، و"إضافة عقار" / "إضافة مشروع" لتقديم عقار أو مشروع على الخريطة مع بيانات
المالك أو المطوّر ومستنداته ليراجعه الفريق (يتواصل معه ويدرجه أو يوضح السبب، والتقديم وحده لا
يستحق عمولة). التقدم لدور الوسيط أو المالك أو مزوّد السيولة يتم من الحساب ← الأدوار ويراجعه
الفريق.""",
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
شهادات الاستثمار من تبويب الشهادات، ولكل شهادة رقم مرجعي، ويعرض تبويب "مركز التحقق" في لوحة
المستثمر الرقم المرجعي لكل شهادة لديك.

لا تتحقق بروبشير من أي مستند بنفسها: صفحة مركز التحقق تربطك بشركاء التحقق المعتمدين في المنظومة،
ولكل نوع من السجلات جهة:
- مستندات Capimax وشهادات الاستثمار: Capimax Verify من CIM Global Financial
  (https://www.cimglobalfinancial.com/capimax-verify). أدخل رقم التحقق أو رقم السجل أو رقم
  الشهادة (لشهادة بروبشير: الرقم المرجعي المطبوع عليها)، أو امسح رمز QR، لتأكيد صحتها وحالتها
  الحالية.
- مستندات التقييم والمستندات المالية (تقارير تقييم العقارات والوحدات، دراسات الاستثمار، التحليلات
  المالية، السجلات المحاسبية والتقارير المالية، تقارير العناية الواجبة): CIM Global Financial على
  الرابط نفسه. أدخل رقم المستند أو معرّف التحقق.
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
