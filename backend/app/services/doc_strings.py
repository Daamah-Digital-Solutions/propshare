# ruff: noqa: E501
"""Arabic and French for the text the platform's documents (PDF / Excel) carry.

English text -> (Arabic, French). Matching ignores case: a label written in capitals comes out in
capitals, one in lower case in lower case. A key with {0}, {1}... is a template for text built
with values; the values are translated too when they are known text. Figures, currency codes,
references, addresses and the names people entered stay as they are.

Terms follow the site's dictionaries (src/lib/i18n/ar.json, fr.json), so a document says what the
page it was downloaded from says. Arabic is written without vowel marks: the document font draws
them apart from their letters.
"""

from __future__ import annotations

MONTHS: dict[str, list[str]] = {
    "ar": [
        "يناير",
        "فبراير",
        "مارس",
        "أبريل",
        "مايو",
        "يونيو",
        "يوليو",
        "أغسطس",
        "سبتمبر",
        "أكتوبر",
        "نوفمبر",
        "ديسمبر",
    ],
    "fr": [
        "janv.",
        "févr.",
        "mars",
        "avr.",
        "mai",
        "juin",
        "juil.",
        "août",
        "sept.",
        "oct.",
        "nov.",
        "déc.",
    ],
}

TEXT: dict[str, tuple[str, str]] = {
    # --- every document ------------------------------------------------------------------ #
    "{0} (continued)": ("{0} (تابع)", "{0} (suite)"),
    "{0} (UTC)": ("{0}  (بتوقيت UTC)", "{0}  (UTC)"),
    "{0} • page {1} • capimaxpropshare.com": (
        "{0}   •   صفحة {1}   •   capimaxpropshare.com",
        "{0}   •   page {1}   •   capimaxpropshare.com",
    ),
    "Issued": ("تاريخ الإصدار", "Émis le"),
    "Issued {0}": ("صدر في {0}", "Émis le {0}"),
    "Issued (UTC)": ("تاريخ الإصدار (UTC)", "Émis le (UTC)"),
    "Date": ("التاريخ", "Date"),
    "Date (UTC)": ("التاريخ (UTC)", "Date (UTC)"),
    "Type": ("النوع", "Type"),
    "Description": ("الوصف", "Description"),
    "Status": ("الحالة", "Statut"),
    "Amount": ("المبلغ", "Montant"),
    "Balance": ("الرصيد", "Solde"),
    "Reference": ("المرجع", "Référence"),
    "Holder": ("صاحب الحساب", "Titulaire"),
    "Email": ("البريد الإلكتروني", "E-mail"),
    "Currency": ("العملة", "Devise"),
    "Property": ("العقار", "Bien"),
    "Location": ("الموقع", "Emplacement"),
    "Units": ("الوحدات", "Parts"),
    "Total": ("الإجمالي", "Total"),
    "None": ("لا يوجد", "Aucun"),
    "Movement": ("الحركة", "Mouvement"),
    "Movements": ("الحركات", "Mouvements"),
    "Period (UTC, inclusive)": ("الفترة (UTC، شاملة)", "Période (UTC, incluse)"),
    # --- the ownership certificate -------------------------------------------------------- #
    "Capimax PropShare — Certificate of Ownership": (
        "Capimax PropShare — شهادة ملكية",
        "Capimax PropShare — Certificat de propriété",
    ),
    "Certificate of Ownership": ("شهادة ملكية", "Certificat de propriété"),
    "Fractional Real-Estate Ownership": ("ملكية عقارية جزئية", "Propriété immobilière fractionnée"),
    "This is to certify that": ("نشهد بأن", "Nous certifions que"),
    "is the registered holder of {0} fractional ownership units in": (
        "هو المالك المسجل لعدد {0} من وحدات الملكية الجزئية في",
        "est le titulaire inscrit de {0} parts de propriété fractionnée dans",
    ),
    "as recorded in the Capimax PropShare ownership ledger.": (
        "وفق المسجل في سجل الملكية لدى Capimax PropShare.",
        "comme inscrit au registre de propriété de Capimax PropShare.",
    ),
    "representing {0} of the property,": (
        "بما يمثل {0} من العقار،",
        "soit {0} du bien,",
    ),
    "Recorded value": ("القيمة المسجلة", "Valeur enregistrée"),
    "Units held": ("الوحدات المملوكة", "Parts détenues"),
    "Ownership stake": ("حصة الملكية", "Part de propriété"),
    "Issuing SPV": ("الشركة ذات الغرض الخاص المصدرة", "SPV émettrice"),
    "Jurisdiction": ("الولاية القضائية", "Juridiction"),
    "Certificate number": ("رقم الشهادة", "Numéro de certificat"),
    "Scan to verify": ("امسح للتحقق", "Scanner pour vérifier"),
    "Authorized on behalf of the platform": (
        "معتمد نيابة عن المنصة",
        "Autorisé au nom de la plateforme",
    ),
    "Ownership": ("ملكية", "Propriété"),
    "Certified": ("موثقة", "Certifiée"),
    "This certificate reflects the fractional units recorded in the Capimax PropShare ownership "
    "ledger on its issue date; scan its QR code to confirm it is authentic and still current. It "
    "is not a transferable security or a substitute for the offering documents and SPV "
    "agreements governing this property.": (
        "تعكس هذه الشهادة الوحدات الجزئية المسجلة في سجل الملكية لدى Capimax PropShare في تاريخ "
        "إصدارها؛ امسح رمز QR للتأكد من صحتها وأنها ما زالت سارية. وهي ليست ورقة مالية قابلة للتداول "
        "ولا تحل محل مستندات الطرح واتفاقيات الشركة ذات الغرض الخاص المنظمة لهذا العقار.",
        "Ce certificat reflète les parts fractionnées inscrites au registre de propriété de "
        "Capimax PropShare à sa date d'émission ; scannez son code QR pour confirmer qu'il est "
        "authentique et toujours valable. Il ne constitue ni un titre transférable ni un substitut "
        "aux documents d'offre et aux accords de la SPV régissant ce bien.",
    ),
    "{0} • Verification code {1}": (
        "{0}   •   رمز التحقق {1}",
        "{0}   •   Code de vérification {1}",
    ),
    "Verify at {0}": ("تحقق عبر {0}", "Vérifier sur {0}"),
    # --- the installment schedule --------------------------------------------------------- #
    "Capimax PropShare — Installment Schedule": (
        "Capimax PropShare — جدول الأقساط",
        "Capimax PropShare — Échéancier des versements",
    ),
    "Installment Schedule": ("جدول الأقساط", "Échéancier des versements"),
    "Progressive-Ownership Payment Plan": (
        "خطة سداد بملكية تدريجية",
        "Plan de paiement à propriété progressive",
    ),
    "Plan holder: {0}": ("صاحب الخطة: {0}", "Titulaire du plan : {0}"),
    "{0} / {1} vested": ("{0} / {1} محررة", "{0} / {1} acquises"),
    "Unit price": ("سعر الوحدة", "Prix unitaire"),
    "Contract value": ("قيمة العقد", "Valeur du contrat"),
    "Down payment": ("الدفعة المقدمة", "Acompte"),
    "Duration": ("المدة", "Durée"),
    "{0} months": ("{0} شهرا", "{0} mois"),
    "Installment fee": ("رسوم القسط", "Frais d'échéance"),
    "{0}% / payment": ("{0}% / دفعة", "{0} % / paiement"),
    "Total fees": ("إجمالي الرسوم", "Total des frais"),
    "Grand total": ("الإجمالي الكلي", "Total général"),
    "Paid to date": ("المدفوع حتى الآن", "Payé à ce jour"),
    "Remaining": ("المتبقي", "Restant"),
    "Next payment": ("الدفعة التالية", "Prochain paiement"),
    "Completed — handover": ("مكتملة — تم التسليم", "Terminé — remise"),
    "Payment Schedule": ("جدول الدفعات", "Calendrier des paiements"),
    "Payment": ("الدفعة", "Paiement"),
    "Due date": ("تاريخ الاستحقاق", "Date d'échéance"),
    "Base": ("الأساس", "Base"),
    "Fee": ("الرسوم", "Frais"),
    "Final (Month {0})": ("الأخيرة (الشهر {0})", "Dernier (mois {0})"),
    "Month {0}": ("الشهر {0}", "Mois {0}"),
    "This schedule reflects the installment plan recorded in the Capimax PropShare ledger as of "
    "the issue date. It is generated from live data. Ownership vests progressively with each paid "
    "installment; rental income begins at handover (final payment).": (
        "يعكس هذا الجدول خطة الأقساط المسجلة في سجل Capimax PropShare حتى تاريخ الإصدار، وقد أنشئ من "
        "البيانات الفعلية. تنتقل الملكية تدريجيا مع كل قسط مدفوع، ويبدأ الدخل الإيجاري عند التسليم "
        "(الدفعة الأخيرة).",
        "Cet échéancier reflète le plan de versements inscrit au registre de Capimax PropShare à "
        "la date d'émission. Il est généré à partir des données réelles. La propriété s'acquiert "
        "progressivement à chaque échéance payée ; les revenus locatifs commencent à la remise "
        "(dernier paiement).",
    ),
    "Capimax PropShare — Installment schedule": (
        "Capimax PropShare — جدول الأقساط",
        "Capimax PropShare — Échéancier des versements",
    ),
    "Plan reference": ("مرجع الخطة", "Référence du plan"),
    "Units vested": ("الوحدات المحررة", "Parts acquises"),
    "Unit price (USD)": ("سعر الوحدة (USD)", "Prix unitaire (USD)"),
    "Down payment (%)": ("الدفعة المقدمة (%)", "Acompte (%)"),
    "Duration (months)": ("المدة (بالأشهر)", "Durée (mois)"),
    "Installment fee (% per payment)": (
        "رسوم القسط (% لكل دفعة)",
        "Frais d'échéance (% par paiement)",
    ),
    "Contract value (USD)": ("قيمة العقد (USD)", "Valeur du contrat (USD)"),
    "Total fees (USD)": ("إجمالي الرسوم (USD)", "Total des frais (USD)"),
    "Grand total (USD)": ("الإجمالي الكلي (USD)", "Total général (USD)"),
    "Paid so far (USD)": ("المدفوع حتى الآن (USD)", "Payé à ce jour (USD)"),
    "Remaining (USD)": ("المتبقي (USD)", "Restant (USD)"),
    "Next due": ("الاستحقاق التالي", "Prochaine échéance"),
    "Principal (USD)": ("الأصل (USD)", "Principal (USD)"),
    "Fee (USD)": ("الرسوم (USD)", "Frais (USD)"),
    "Total (USD)": ("الإجمالي (USD)", "Total (USD)"),
    # --- statuses ------------------------------------------------------------------------- #
    "Active": ("نشطة", "Actif"),
    "Completed": ("مكتملة", "Terminé"),
    "In progress": ("قيد التنفيذ", "En cours"),
    "Reversed": ("معكوس", "Annulé"),
    "Returned": ("معاد", "Restitué"),
    "Paid": ("مدفوع", "Payé"),
    "Pending": ("قيد الانتظار", "En attente"),
    "Pending payment": ("بانتظار الدفع", "En attente de paiement"),
    "Scheduled": ("مجدول", "Planifié"),
    "Overdue": ("متأخر", "En retard"),
    "Due": ("مستحق", "Dû"),
    "Failed": ("فشل", "Échoué"),
    "Cancelled": ("ملغى", "Annulé"),
    "Defaulted": ("متعثر", "En défaut"),
    "Sold": ("مباع", "Vendu"),
    "Transferred": ("منقول", "Transféré"),
    "Refunded": ("مسترد", "Remboursé"),
    # --- the account statement ------------------------------------------------------------ #
    "Capimax PropShare — Account Statement": (
        "Capimax PropShare — كشف حساب",
        "Capimax PropShare — Relevé de compte",
    ),
    "Capimax PropShare — Account statement": (
        "Capimax PropShare — كشف حساب",
        "Capimax PropShare — Relevé de compte",
    ),
    "Account Statement": ("كشف حساب", "Relevé de compte"),
    "Statement": ("كشف الحساب", "Relevé"),
    "Opening balance": ("الرصيد الافتتاحي", "Solde d'ouverture"),
    "Closing balance": ("الرصيد الختامي", "Solde de clôture"),
    "Money in": ("الأموال الواردة", "Entrées"),
    "Money out": ("الأموال الصادرة", "Sorties"),
    "Wallet movements": ("حركات المحفظة", "Mouvements du portefeuille"),
    "No wallet movements in this period.": (
        "لا توجد حركات في المحفظة خلال هذه الفترة.",
        "Aucun mouvement du portefeuille sur cette période.",
    ),
    "Summary by type": ("ملخص حسب النوع", "Résumé par type"),
    "Holdings": ("الحيازات", "Avoirs"),
    "Holdings on {0}": ("الحيازات في {0}", "Avoirs au {0}"),
    "Property (units held on {0})": (
        "العقار (الوحدات المملوكة في {0})",
        "Bien (parts détenues au {0})",
    ),
    "Generated from the Capimax PropShare wallet ledger. Times are UTC; the period includes both "
    "dates. Amounts in progress (for example a withdrawal being paid) are shown as they were "
    "booked. This statement is informational and is not a tax document.": (
        "صادر من سجل محفظة Capimax PropShare. الأوقات بتوقيت UTC والفترة تشمل التاريخين. تظهر المبالغ "
        "قيد التنفيذ (مثل سحب جار دفعه) كما سجلت. هذا الكشف للعلم فقط وليس مستندا ضريبيا.",
        "Généré à partir du registre du portefeuille Capimax PropShare. Les heures sont en UTC ; "
        "la période inclut les deux dates. Les montants en cours (par exemple un retrait en cours "
        "de paiement) figurent tels qu'ils ont été enregistrés. Ce relevé est informatif et n'est "
        "pas un document fiscal.",
    ),
    # --- the kinds of wallet movement ----------------------------------------------------- #
    "Deposit": ("إيداع", "Dépôt"),
    "Investment": ("استثمار", "Investissement"),
    "Withdrawal": ("سحب", "Retrait"),
    "Return / distribution": ("العائد / التوزيع", "Rendement / distribution"),
    "Referral commission": ("عمولة الإحالة", "Commission de parrainage"),
    "Secondary-market sale": ("البيع عبر السوق الثانوي", "Vente sur le marché secondaire"),
    "Liquidity pool": ("مجمع السيولة", "Pool de liquidité"),
    "Liquidity pool yield": ("عائد مجمع السيولة", "Rendement du pool de liquidité"),
    "Family allocation": ("التخصيص العائلي", "Allocation familiale"),
    "Gift": ("هدية", "Don"),
    "Beneficiary transfer": ("تحويل المستفيد", "Transfert au bénéficiaire"),
    "Transfer": ("تحويل", "Transfert"),
    # --- what a wallet movement says ------------------------------------------------------ #
    "Referral commission (installment)": (
        "عمولة إحالة (قسط)",
        "Commission de parrainage (échéance)",
    ),
    "Referral commission (investment)": (
        "عمولة إحالة (استثمار)",
        "Commission de parrainage (investissement)",
    ),
    "Return — {0} ({1})": ("عائد — {0} ({1})", "Rendement — {0} ({1})"),
    "Transferred to a designated beneficiary": (
        "نقلت إلى مستفيد معين",
        "Transféré à un bénéficiaire désigné",
    ),
    "Received as a designated beneficiary": (
        "مستلمة بصفتك مستفيدا معينا",
        "Reçu en tant que bénéficiaire désigné",
    ),
    "Family reinvest — {0}": ("إعادة استثمار عائلية — {0}", "Réinvestissement familial — {0}"),
    "Family allocation received": ("تخصيص عائلي مستلم", "Allocation familiale reçue"),
    "Family transfer fee": ("رسوم التحويل العائلي", "Frais de transfert familial"),
    "Family returns released": ("صرف العوائد العائلية", "Rendements familiaux libérés"),
    "Family returns released on verification": (
        "صرف العوائد العائلية عند التحقق",
        "Rendements familiaux libérés après vérification",
    ),
    "Gift escrow — scheduled": ("حجز هدية — مجدولة", "Séquestre du don — planifié"),
    "Gift escrow — recurring": ("حجز هدية — متكررة", "Séquestre du don — récurrent"),
    "Gift cancelled — escrow refunded": (
        "ألغيت الهدية — أعيد المبلغ",
        "Don annulé — séquestre remboursé",
    ),
    "Gift not received — escrow refunded": (
        "لم تستلم الهدية — أعيد المبلغ",
        "Don non reçu — séquestre remboursé",
    ),
    "Gift received": ("هدية مستلمة", "Don reçu"),
    "Gift fee": ("رسوم الهدية", "Frais de don"),
    "Refund — installment plan could not start": (
        "استرداد — تعذر بدء خطة الأقساط",
        "Remboursement — le plan de versements n'a pas pu démarrer",
    ),
    "Installment {0} — {1}": ("القسط {0} — {1}", "Échéance {0} — {1}"),
    "Investment in {0}": ("استثمار في {0}", "Investissement dans {0}"),
    "Platform fee (one-time)": ("رسوم المنصة (مرة واحدة)", "Frais de plateforme (une seule fois)"),
    "Refund — investment could not be fulfilled": (
        "استرداد — تعذر تنفيذ الاستثمار",
        "Remboursement — l'investissement n'a pas pu être réalisé",
    ),
    "Reinvest — {0}": ("إعادة استثمار — {0}", "Réinvestissement — {0}"),
    "LP buyback — {0}": (
        "إعادة شراء مزود السيولة — {0}",
        "Rachat par le fournisseur de liquidité — {0}",
    ),
    "Instant exit — {0}": ("تخارج فوري — {0}", "Sortie instantanée — {0}"),
    "Liquidity fee": ("رسوم السيولة", "Frais de liquidité"),
    "Bank transfer deposit": ("إيداع بتحويل بنكي", "Dépôt par virement bancaire"),
    "Bank transfer deposit — ref {0}": (
        "إيداع بتحويل بنكي — مرجع {0}",
        "Dépôt par virement bancaire — réf. {0}",
    ),
    "Crypto payment for {0}: credited to the wallet": (
        "دفعة عملات رقمية لـ {0}: أضيفت إلى المحفظة",
        "Paiement crypto pour {0} : crédité sur le portefeuille",
    ),
    "Deposit via {0}": ("إيداع عبر {0}", "Dépôt via {0}"),
    "Crypto payment above the amount due: the difference": (
        "دفعة عملات رقمية أعلى من المستحق: الفرق",
        "Paiement crypto supérieur au montant dû : la différence",
    ),
    "Installment position — {0}": ("مركز أقساط — {0}", "Position en versements — {0}"),
    "Installment position sold — {0}": (
        "بيع مركز أقساط — {0}",
        "Position en versements vendue — {0}",
    ),
    "Resale fee (one-time)": ("رسوم إعادة البيع (مرة واحدة)", "Frais de revente (une seule fois)"),
    "Secondary purchase — {0}": ("شراء ثانوي — {0}", "Achat secondaire — {0}"),
    "Secondary sale — {0}": ("بيع ثانوي — {0}", "Vente secondaire — {0}"),
    "Transfer {0} to {1}": ("تحويل {0} إلى {1}", "Transfert {0} à {1}"),
    "Transfer {0} from {1}": ("تحويل {0} من {1}", "Transfert {0} de {1}"),
    "Transfer {0} returned": ("أعيد التحويل {0}", "Transfert {0} restitué"),
    "Transfer fee {0}": ("رسوم التحويل {0}", "Frais de transfert {0}"),
    "Withdrawal hold": ("حجز السحب", "Blocage du retrait"),
    "Withdrawal reversed: {0}": ("عكس السحب: {0}", "Retrait annulé : {0}"),
    "not sent: {0}": ("لم يرسل: {0}", "non envoyé : {0}"),
    "payout submit failed": ("تعذر إرسال الدفعة", "échec de l'envoi du paiement"),
    "review rejected": ("رفض في المراجعة", "rejeté à la vérification"),
    "payout failed": ("فشلت الدفعة", "échec du paiement"),
    "reconcile: provider reported failed": (
        "التسوية: أبلغ مزود الخدمة بالفشل",
        "rapprochement : échec signalé par le prestataire",
    ),
    # --- the receipt ---------------------------------------------------------------------- #
    "Capimax PropShare — Receipt {0}": (
        "Capimax PropShare — إيصال {0}",
        "Capimax PropShare — Reçu {0}",
    ),
    "Receipt": ("إيصال", "Reçu"),
    "Money into the wallet": ("أموال واردة إلى المحفظة", "Argent entrant dans le portefeuille"),
    "Money out of the wallet": ("أموال صادرة من المحفظة", "Argent sortant du portefeuille"),
    "Receipt number": ("رقم الإيصال", "Numéro de reçu"),
    "Withdrawal request": ("طلب السحب", "Demande de retrait"),
    "Paid to": ("مدفوع إلى", "Payé à"),
    "Transfer reference": ("مرجع التحويل", "Référence du virement"),
    "Issued from the Capimax PropShare wallet ledger for this one movement. Times are UTC. This "
    "receipt is informational and is not a tax document.": (
        "صادر من سجل محفظة Capimax PropShare لهذه الحركة وحدها. الأوقات بتوقيت UTC. هذا الإيصال للعلم "
        "فقط وليس مستندا ضريبيا.",
        "Émis à partir du registre du portefeuille Capimax PropShare pour ce seul mouvement. Les "
        "heures sont en UTC. Ce reçu est informatif et n'est pas un document fiscal.",
    ),
    "{0} • issued {1} • capimaxpropshare.com": (
        "{0}   \u200f•\u200f   صدر في {1}   \u200f•\u200f   capimaxpropshare.com",
        "{0}   •   émis le {1}   •   capimaxpropshare.com",
    ),
    # --- the unit statement --------------------------------------------------------------- #
    "Capimax PropShare — Unit Statement": (
        "Capimax PropShare — كشف الوحدات",
        "Capimax PropShare — Relevé de parts",
    ),
    "Capimax PropShare — Unit statement": (
        "Capimax PropShare — كشف الوحدات",
        "Capimax PropShare — Relevé de parts",
    ),
    "Unit Statement": ("كشف الوحدات", "Relevé de parts"),
    "Unit movements": ("حركات الوحدات", "Mouvements de parts"),
    "Units held at the start": ("الوحدات في البداية", "Parts au début"),
    "Units in": ("وحدات واردة", "Parts entrantes"),
    "Units out": ("وحدات صادرة", "Parts sortantes"),
    "Units held at the end": ("الوحدات في النهاية", "Parts à la fin"),
    "Other party": ("الطرف الآخر", "Autre partie"),
    "Held": ("المملوك", "Détenues"),
    "Held after": ("المملوك بعدها", "Détenues après"),
    "Units by property": ("الوحدات حسب العقار", "Parts par bien"),
    "At the start": ("في البداية", "Au début"),
    "In": ("وارد", "Entrées"),
    "Out": ("صادر", "Sorties"),
    "At the end": ("في النهاية", "À la fin"),
    "No unit movements in this period.": (
        "لا توجد حركات وحدات خلال هذه الفترة.",
        "Aucun mouvement de parts sur cette période.",
    ),
    "No units held in this period.": (
        "لا توجد وحدات مملوكة خلال هذه الفترة.",
        "Aucune part détenue sur cette période.",
    ),
    "From the Capimax PropShare ownership ledger; times are UTC, both dates included. HELD: units "
    "held in that property after the movement. Informational only: not a tax document or a title "
    "deed.": (
        "من سجل الملكية لدى Capimax PropShare؛ الأوقات بتوقيت UTC والفترة تشمل التاريخين. المملوك: "
        "الوحدات المملوكة في ذلك العقار بعد الحركة. للعلم فقط: ليس مستندا ضريبيا ولا سند ملكية.",
        "Issu du registre de propriété de Capimax PropShare ; heures en UTC, les deux dates "
        "incluses. DÉTENUES : parts détenues dans ce bien après le mouvement. À titre informatif "
        "uniquement : ni document fiscal ni titre de propriété.",
    ),
    "Purchase": ("شراء", "Achat"),
    "Bought with reinvested returns": (
        "تم الشراء بعوائد معاد استثمارها",
        "Acheté avec des rendements réinvestis",
    ),
    "Bought at the family discount": ("تم الشراء بخصم العائلة", "Acheté avec la remise famille"),
    "Units released by an installment payment": (
        "وحدات محررة بدفعة قسط",
        "Parts libérées par un paiement d'échéance",
    ),
    "Received from a family member": (
        "مستلمة من أحد أفراد العائلة",
        "Reçu d'un membre de la famille",
    ),
    "Transferred to a family member": (
        "نقلت إلى أحد أفراد العائلة",
        "Transféré à un membre de la famille",
    ),
    "Gift sent": ("هدية مرسلة", "Don envoyé"),
    "Transfer received": ("تحويل مستلم", "Transfert reçu"),
    "Transfer sent": ("تحويل مرسل", "Transfert envoyé"),
    "Bought on the secondary market": (
        "تم الشراء في السوق الثانوي",
        "Acheté sur le marché secondaire",
    ),
    "Sold on the secondary market": ("بيعت في السوق الثانوي", "Vendu sur le marché secondaire"),
    "Sold to a liquidity provider": ("بيعت إلى مزود سيولة", "Vendu à un fournisseur de liquidité"),
    "Acquired as a liquidity provider": (
        "تم التملك بصفة مزود سيولة",
        "Acquis en tant que fournisseur de liquidité",
    ),
    "Units adjusted": ("تعديل الوحدات", "Parts ajustées"),
    "a family member": ("أحد أفراد العائلة", "un membre de la famille"),
    "a named person": ("شخص محدد", "une personne désignée"),
    "a designated beneficiary": ("مستفيد معين", "un bénéficiaire désigné"),
    "the account holder": ("صاحب الحساب", "le titulaire du compte"),
    "a Capimax PropShare member": ("أحد أعضاء Capimax PropShare", "un membre de Capimax PropShare"),
    # --- the beneficiary certificate ------------------------------------------------------ #
    "Capimax PropShare — Certificate of Designation": (
        "Capimax PropShare — شهادة تعيين",
        "Capimax PropShare — Certificat de désignation",
    ),
    "Certificate of Designation": ("شهادة تعيين", "Certificat de désignation"),
    "{0} - Capimax PropShare Beneficiary Register": (
        "{0}  -  سجل المستفيدين في Capimax PropShare",
        "{0}  -  Registre des bénéficiaires Capimax PropShare",
    ),
    "has been designated by the account holder": (
        "قد تم تعيينه من قبل صاحب الحساب",
        "a été désigné(e) par le titulaire du compte",
    ),
    "as {0}, with an allocation of {1}%,": (
        "بصفته {0}، بحصة {1}%،",
        "en tant que {0}, avec une part de {1} %,",
    ),
    "as {0}, with no share allocated,": (
        "بصفته {0}، دون تخصيص حصة،",
        "en tant que {0}, sans part attribuée,",
    ),
    "as recorded in the Capimax PropShare beneficiary register.": (
        "وفق المسجل في سجل المستفيدين لدى Capimax PropShare.",
        "comme inscrit au registre des bénéficiaires de Capimax PropShare.",
    ),
    "Relationship to the holder": ("صلة القرابة بصاحب الحساب", "Lien avec le titulaire"),
    "Designated as": ("معين بصفة", "Désigné(e) en tant que"),
    "Identity document": ("وثيقة الهوية", "Pièce d'identité"),
    "Document number": ("رقم الوثيقة", "Numéro du document"),
    "Allocation": ("الحصة", "Part"),
    "Coverage recorded": ("التغطية المسجلة", "Couverture enregistrée"),
    "Transfer condition": ("شرط التحويل", "Condition de transfert"),
    "Email on record": ("البريد الإلكتروني المسجل", "E-mail enregistré"),
    "{0} - Version {1}": ("{0}  -  الإصدار {1}", "{0}  -  Version {1}"),
    "How a claim is made": ("كيف تقدم المطالبة", "Comment faire une demande"),
    "The person named above presents this certificate together with their own identity document "
    "at capimaxpropshare.com/estate-claim. After verification, the assets allocated to them are "
    "transferred to their own Capimax PropShare account. The holder's account, password and "
    "records are never handed over.": (
        "يقدم الشخص المذكور أعلاه هذه الشهادة مع وثيقة هويته عبر capimaxpropshare.com/estate-claim. "
        "وبعد التحقق تحول الأصول المخصصة له إلى حسابه في Capimax PropShare. ولا يسلم أبدا حساب صاحب "
        "الحساب أو كلمة مروره أو سجلاته.",
        "La personne nommée ci-dessus présente ce certificat avec sa pièce d'identité sur "
        "capimaxpropshare.com/estate-claim. Après vérification, les actifs qui lui sont attribués "
        "sont transférés sur son compte Capimax PropShare. Le compte, le mot de passe et les "
        "données du titulaire ne sont jamais remis.",
    ),
    "Issued from the platform's beneficiary register": (
        "صادرة من سجل المستفيدين في المنصة",
        "Émis à partir du registre des bénéficiaires",
    ),
    "Designation": ("تعيين", "Désignation"),
    "Recorded": ("مسجل", "Enregistrée"),
    "This certificate records a designation made by the account holder in the Capimax PropShare "
    "beneficiary register, as it stood on the issue date. The holder may change or withdraw it at "
    "any time: the register at the time of a claim prevails. It is not a will, not a transferable "
    "instrument and not evidence of ownership. Any transfer is made only after Capimax PropShare "
    "has verified a claim, and is subject to the platform's terms and to applicable law.": (
        "تسجل هذه الشهادة تعيينا أجراه صاحب الحساب في سجل المستفيدين لدى Capimax PropShare كما كان في "
        "تاريخ الإصدار. ويجوز لصاحب الحساب تغييره أو سحبه في أي وقت، ويعتد بالسجل وقت المطالبة. وهي "
        "ليست وصية ولا أداة قابلة للتداول ولا دليل ملكية. ولا يتم أي تحويل إلا بعد تحقق Capimax "
        "PropShare من المطالبة، ويخضع لشروط المنصة والقانون المعمول به.",
        "Ce certificat atteste une désignation faite par le titulaire du compte au registre des "
        "bénéficiaires de Capimax PropShare, telle qu'à la date d'émission. Le titulaire peut la "
        "modifier ou la retirer à tout moment : le registre à la date de la demande prévaut. Ce "
        "n'est ni un testament, ni un instrument transférable, ni une preuve de propriété. Tout "
        "transfert n'a lieu qu'après vérification de la demande par Capimax PropShare, sous réserve "
        "des conditions de la plateforme et du droit applicable.",
    ),
    "No share allocated": ("لا توجد حصة مخصصة", "Aucune part attribuée"),
    "Beneficiary": ("مستفيد", "Bénéficiaire"),
    "Heir": ("وريث", "Héritier"),
    "Authorized Person": ("شخص مفوض", "Personne autorisée"),
    "Legal Representative": ("ممثل قانوني", "Représentant légal"),
    "Ownership Rights": ("حقوق الملكية", "Droits de propriété"),
    "Passive Income": ("دخل سلبي", "Revenu passif"),
    "Rental Returns": ("العوائد الإيجارية", "Rendements locatifs"),
    "Wallet Balance": ("رصيد المحفظة", "Solde du portefeuille"),
    "Full Portfolio": ("المحفظة الكاملة", "Portefeuille complet"),
    "On verified death": ("عند التحقق من الوفاة", "Au décès vérifié"),
    "After 12 months inactivity": ("بعد 12 شهرا من عدم النشاط", "Après 12 mois d'inactivité"),
    "Authorized transfer event": ("حدث تحويل مصرح به", "Événement de transfert autorisé"),
    "Manual / on request": ("يدوي / عند الطلب", "Manuel / sur demande"),
    "Passport": ("جواز السفر", "Passeport"),
    "National ID": ("الهوية الوطنية", "Carte nationale d'identité"),
    "Driving licence": ("رخصة القيادة", "Permis de conduire"),
    "Residence permit": ("تصريح الإقامة", "Titre de séjour"),
    "Spouse": ("زوج / زوجة", "Conjoint(e)"),
    "Husband": ("زوج", "Époux"),
    "Wife": ("زوجة", "Épouse"),
    "Son": ("ابن", "Fils"),
    "Daughter": ("ابنة", "Fille"),
    "Child": ("ابن / ابنة", "Enfant"),
    "Father": ("أب", "Père"),
    "Mother": ("أم", "Mère"),
    "Parent": ("أحد الوالدين", "Parent"),
    "Brother": ("أخ", "Frère"),
    "Sister": ("أخت", "Sœur"),
    "Lawyer": ("محام", "Avocat"),
    "Other": ("أخرى", "Autre"),
}
