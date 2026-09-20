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
        "The property models: ready income, under construction, installments",
        "basics",
        20,
        """Every listing states its model on the property page.
- Ready property (income): a completed, leased property. Net rental income is distributed to
  holders periodically and lands in your wallet, where you can withdraw or reinvest it.
- Under construction (development / off-plan): you invest early at the offering price; there
  is no rental income while the project is being built. The listing shows construction
  progress, milestones and the expected completion date. Returns come from appreciation when
  the project completes or is sold.
- Off-plan paid in installments: the same early investment, paid through a structured plan:
  a down payment now and monthly instalments after, with no bank interest. The plan and its
  schedule are shown before you commit and afterwards under your portfolio.
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
   exit options, and confirm. Your investment then appears in your portfolio, and a digital
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
reference shown on the deposit page and is credited by the team after review. Withdrawals go
to a saved payout method (bank account or crypto wallet). A withdrawal request holds the
amount immediately and is reviewed and paid by the team; you see its status under Wallet and
receive a notification when it is paid or if it is rejected (rejected funds return to your
wallet). If a payment looks stuck, the assistant can show its current status and open a
support ticket with the reference for a person to follow up.""",
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
- an exit fee when selling units on the secondary market, calculated on the trade;
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
        """You are not locked into a property forever. Two exit paths exist, and each property
page states which apply to it and any lock-up period:
- Secondary market: list some or all of your units at a price you set; another investor buys
  them and the units transfer through the SPV when the buyer pays. Best for maximum value
  when you are not in a hurry. You can cancel an unsold listing.
- Liquidity market: request an exit at the platform-quoted price and a liquidity provider
  funds it, usually faster than waiting for a buyer, in exchange for a discount and a fee.
Both are done from your portfolio; the assistant can show your holdings, listings and
requests and take you to the right page, but the listing, sale or request is confirmed by you
on that page.""",
    ),
    (
        "installment-plans",
        "Installment plans",
        "installments",
        80,
        """For properties sold in installments you pay a down payment now and monthly
instalments afterwards; the platform offers a set of plan lengths and the down payment
depends on the length chosen. The full schedule, with the installment fee on each payment, is
shown before you commit and afterwards under Portfolio -> Installments. Instalments are taken
from your wallet on their due dates; you receive reminders before each one and there is a
grace period before a missed instalment becomes overdue. Keep your wallet funded ahead of the
due date. The assistant can show your plans, schedule and next due amount.""",
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
volume are prohibited and lead to suspension. Some properties have a lock-up period before
units can be listed; the property page and your holdings show it.""",
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
fees on their activity (never a share of the investment itself). The broker dashboard shows
referrals and commissions. Applying for the broker, owner or liquidity-provider role is done
from Account -> Roles and reviewed by the team.""",
    ),
    (
        "support-and-the-assistant",
        "What the assistant can do, and how to reach a person",
        "support",
        140,
        """The assistant answers from the platform's approved information and your own live
account data. It can show balances, statuses, investments, plans, holdings, notifications and
tickets; explain how things work; hand you the exact page; and, with your confirmation, resend
your verification email, mark notifications read, or open a support ticket. It never moves
money or changes settings, and it does not give personal investment advice. When it cannot
answer, it records the question for the team and offers the support link. Support tickets are
followed up by a person; you can see and reply to your tickets from the Support page, and you
are notified of each reply.""",
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
        "نماذج العقارات: جاهز بدخل، تحت الإنشاء، بالأقساط",
        "basics",
        20,
        """كل إدراج يذكر نموذجه في صفحة العقار.
- عقار جاهز (دخل): عقار مكتمل ومؤجَّر. يُوزَّع صافي دخل الإيجار على الملاك دوريًا ويصل إلى
  محفظتك، ومنها تسحب أو تعيد الاستثمار.
- تحت الإنشاء (تطوير / على الخريطة): تستثمر مبكرًا بسعر الطرح ولا يوجد دخل إيجاري أثناء البناء.
  يعرض الإدراج نسبة الإنجاز والمراحل وتاريخ الاكتمال المتوقع، والعائد يأتي من ارتفاع القيمة
  عند الاكتمال أو البيع.
- على الخريطة بالأقساط: نفس الاستثمار المبكر لكن بخطة منظّمة: دفعة أولى الآن وأقساط شهرية
  بعدها، بلا فوائد بنكية. تُعرض الخطة وجدولها قبل التأكيد وبعده في محفظتك.
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
4. افتح عقارًا، اختر عدد الوحدات، راجع الإجمالي شاملًا الرسوم وخيارات الخروج، ثم أكّد. يظهر
   استثمارك في محفظتك ويمكن تنزيل شهادة استثمار رقمية منها.
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
مع المرجع المعروض في صفحة الإيداع ويقيّده الفريق بعد المراجعة. السحب يذهب إلى وسيلة صرف محفوظة
(حساب بنكي أو محفظة عملات رقمية). يحجز طلب السحب المبلغ فورًا ويراجعه الفريق ويصرفه؛ ترى حالته
في المحفظة ويصلك إشعار عند الصرف أو الرفض (المبلغ المرفوض يعود لمحفظتك). إن بدا دفع متوقفًا،
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
- رسوم خروج عند بيع الوحدات في السوق الثانوي، تُحسب على الصفقة؛
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
        """لست مقيّدًا بعقار للأبد. يوجد مساران للخروج، وتذكر صفحة كل عقار أيهما ينطبق عليه وأي
فترة حظر:
- السوق الثانوي: تعرض بعض وحداتك أو كلها بسعر تحدده؛ يشتريها مستثمر آخر وتنتقل الوحدات عبر
  الـ SPV عند دفع المشتري. الأنسب لأقصى قيمة عندما لا تكون مستعجلًا. يمكنك إلغاء عرض لم يُبَع.
- سوق السيولة: تطلب الخروج بالسعر الذي تحدده المنصة ويموّله مزوّد سيولة، عادةً أسرع من انتظار
  مشترٍ، مقابل خصم ورسوم.
كلاهما من محفظتك؛ يستطيع المساعد عرض حيازاتك وعروضك وطلباتك وإرشادك للصفحة الصحيحة، لكن
العرض أو البيع أو الطلب تؤكده أنت في تلك الصفحة.""",
    ),
    (
        "installment-plans",
        "خطط الأقساط",
        "installments",
        80,
        """في العقارات المباعة بالأقساط تدفع دفعة أولى الآن وأقساطًا شهرية بعدها؛ تقدّم المنصة
مجموعة مدد للخطط وتعتمد الدفعة الأولى على المدة المختارة. يُعرض الجدول الكامل، مع رسوم الأقساط
على كل دفعة، قبل التأكيد وبعده في المحفظة ← الأقساط. تُخصم الأقساط من محفظتك في مواعيدها؛ يصلك
تذكير قبل كل قسط وهناك فترة سماح قبل أن يصبح القسط الفائت متأخرًا. احرص على شحن محفظتك قبل موعد
الاستحقاق. يستطيع المساعد عرض خططك وجدولك والمبلغ المستحق التالي.""",
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
بالأسعار والتداول الوهمي وافتعال الأحجام ممنوعة وتؤدي إلى الإيقاف. بعض العقارات لها فترة حظر قبل
إمكانية عرض الوحدات؛ تظهر في صفحة العقار وفي حيازاتك.""",
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
من رسوم المنصة على نشاطهم (وليس من الاستثمار نفسه أبدًا). تعرض لوحة الوسيط الإحالات والعمولات.
التقدم لدور الوسيط أو المالك أو مزوّد السيولة يتم من الحساب ← الأدوار ويراجعه الفريق.""",
    ),
    (
        "support-and-the-assistant",
        "ما يستطيع المساعد فعله، وكيف تصل إلى شخص",
        "support",
        140,
        """يجيب المساعد من معلومات المنصة المعتمدة ومن بيانات حسابك الحيّة. يستطيع عرض الأرصدة
والحالات والاستثمارات والخطط والحيازات والإشعارات والتذاكر؛ وشرح كيف تعمل الأمور؛ وإعطاءك الصفحة
المطلوبة تحديدًا؛ وبتأكيدك: إعادة إرسال رسالة التفعيل، أو تعليم الإشعارات كمقروءة، أو فتح تذكرة
دعم. لا يحرّك مالًا ولا يغيّر إعدادات، ولا يقدّم نصيحة استثمارية شخصية. عندما لا يستطيع الإجابة
يسجّل السؤال للفريق ويعرض رابط الدعم. تذاكر الدعم يتابعها شخص؛ يمكنك رؤية تذاكرك والرد عليها من
صفحة الدعم، ويصلك إشعار بكل رد.""",
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
