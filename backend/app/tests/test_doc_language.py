"""Documents in the site's language (client, 2026-11-01, as on Capimax BRX): the dictionary, the
Arabic drawing and mirroring, every document in Arabic and French, and that English stays the
file it always was."""

from __future__ import annotations

import ast
import datetime as dt
import decimal
import io
import pathlib
import re
import unicodedata

import pytest
from openpyxl import load_workbook

from app.services import (
    certificate_service,
    estate_certificate,
    estate_service,
    installment_pdf,
    receipt_service,
    statement_render,
    statement_service,
    unit_movement_service,
    unit_statement_render,
)
from app.services.doc_lang import (
    DocCanvas,
    date_range,
    doc_language,
    has_arabic,
    is_rtl,
    long_date,
    mbox,
    mx,
    status_text,
    table_date,
    text_width,
    tr,
)
from app.services.doc_strings import MONTHS, TEXT

D = decimal.Decimal
NOW = dt.datetime(2026, 11, 1, 10, 30, tzinfo=dt.UTC)
SERVICES = pathlib.Path(certificate_service.__file__).parent


def _statement(holder="Sara Rashid", title="Sunset Towers") -> statement_service.Statement:
    kinds = list(statement_service.TYPE_LABELS.values())
    states = list(statement_service.STATUS_LABELS.values())
    return statement_service.Statement(
        ref="STM-ABCD",
        holder=holder,
        email="sara@x.io",
        currency="USD",
        start=dt.date(2026, 1, 1),
        end=dt.date(2026, 10, 31),
        generated_at=NOW,
        opening=D("10.00"),
        closing=D("90.00"),
        money_in=D("100.00"),
        money_out=D("20.00"),
        rows=[
            statement_service.StatementRow(
                at=NOW,
                type="deposit",
                type_label=kinds[i % len(kinds)],
                description=f"Investment in {title}",
                status=states[i % len(states)],
                amount=D("5.00") if i % 2 else D("-5.00"),
                balance=D("90.00"),
                reference="AB12CD34",
            )
            for i in range(80)
        ],
        totals=[statement_service.TypeTotal("Deposit", D("100.00"), D("0.00"))],
        holdings=[statement_service.Holding(title, 12)],
    )


def _units() -> unit_movement_service.UnitStatement:
    labels = list(unit_movement_service.LABELS.values())
    return unit_movement_service.UnitStatement(
        ref="UST-ABCD",
        holder="Sara Rashid",
        email="sara@x.io",
        start=dt.date(2026, 1, 1),
        end=dt.date(2026, 10, 31),
        generated_at=NOW,
        units_in=20,
        units_out=8,
        rows=[
            unit_movement_service.UnitRow(
                at=NOW,
                property_title="Sunset Towers",
                label=labels[i % len(labels)],
                counterparty="a family member" if i % 2 else "",
                units=2 if i % 2 else -1,
                balance=12,
                reference="TR-AB12",
            )
            for i in range(60)
        ],
        properties=[unit_movement_service.PropertyLine("Sunset Towers", 0, 20, 8, 12)],
    )


def _certificate(holder="Sara Rashid") -> bytes:
    return certificate_service.render_certificate_pdf(
        holder=holder,
        property_title="Sunset Towers",
        location="Dubai",
        units=12,
        ownership="0.5%",
        value="$1,200.00",
        spv="Sunset SPV",
        jurisdiction="Dubai",
        cert_ref="PSC-2026-ABCD2345",
        issued=long_date(NOW, "%b %d, %Y"),
        verification_code="AbCdEfGhIjKlMnOpQrStUv",
        verify_url="https://capimaxpropshare.com/verify/AbCdEfGhIjKlMnOpQrStUv",
    )


def _schedule() -> bytes:
    day = long_date(NOW, "%b %d, %Y")
    rows = [
        {
            "label": "Down payment" if i == 0 else f"Month {i}",
            "due": day,
            "base": "$100.00",
            "fee": "$1.00",
            "total": "$101.00",
            "status": ("Paid", "Overdue", "Scheduled", "Pending")[i % 4],
        }
        for i in range(30)
    ]
    rows[-1]["label"] = "Final (Month 29)"
    return installment_pdf.render_schedule_pdf(
        holder="Sara Rashid",
        property_title="Sunset Towers",
        location="Dubai",
        spv="Sunset SPV",
        status="active",
        units_total=12,
        vested_units=3,
        unit_price="$100.00",
        down_payment_pct=20,
        duration_months=24,
        fee_rate="2.5",
        contract_value="$1,200.00",
        total_fees="$30.00",
        grand_total="$1,230.00",
        total_paid="$303.00",
        remaining_balance="$927.00",
        next_due=day,
        plan_ref="CMX-INS-ABCD1234",
        issued=day,
        rows=rows,
    )


def _receipt() -> bytes:
    return receipt_service.render_pdf(
        receipt_service.Receipt(
            number="RCT-ABCD123456",
            at=NOW,
            holder="Sara Rashid",
            email="sara@x.io",
            type_label="Withdrawal",
            description="Withdrawal hold",
            status="Completed",
            amount=D("-250.00"),
            request="WD-2026-0001",
            destination="IBAN ****1234",
            transfer_reference="TT-889",
            issued_at=NOW,
        )
    )


def _estate() -> bytes:
    return estate_certificate.render(
        beneficiary="Layla Hassan",
        holder="Sara Rashid",
        role="Heir",
        designation="as heir, with an allocation of 40%,",
        relationship="Daughter",
        id_type="Passport",
        id_number="A1234567",
        allocation="40%",
        coverage=tr("Full Portfolio"),
        condition="On verified death",
        email="layla@x.io",
        certificate_no="BEN-2026-ABCD",
        issued=long_date(NOW, "%b %d, %Y"),
        version=2,
        claim_url="https://capimaxpropshare.com/estate-claim?certificate=BEN-2026-ABCD",
    )


DOCUMENTS = {
    "certificate": _certificate,
    "schedule": _schedule,
    "statement": lambda: statement_render.render_pdf(_statement()),
    "units": lambda: unit_statement_render.render_pdf(_units()),
    "receipt": _receipt,
    "estate": _estate,
}


@pytest.fixture
def drawn(monkeypatch) -> list[str]:
    """Every string a document asks the canvas to draw, before it is shaped."""
    said: list[str] = []
    for name in ("drawString", "drawRightString", "drawCentredString"):
        original = getattr(DocCanvas, name)

        def record(self, x, y, text, *a, _original=original, **k):
            said.append(str(text))
            return _original(self, x, y, text, *a, **k)

        monkeypatch.setattr(DocCanvas, name, record)
    return said


# --- the dictionary -------------------------------------------------------------------------- #
def test_english_is_untouched_and_an_unknown_language_is_english():
    assert tr("Amount") == "Amount"
    with doc_language("de"):
        assert tr("Amount") == "Amount"
        assert not is_rtl()
    with doc_language(None):
        assert tr("Amount") == "Amount"


def test_exact_text_templates_and_case():
    with doc_language("ar"):
        assert tr("Amount") == "المبلغ"
        assert is_rtl()
        assert tr("Investment in Sunset") == "استثمار في Sunset"
    with doc_language("fr"):
        assert tr("Amount") == "Montant"
        assert tr("AMOUNT") == "MONTANT"  # a label in capitals stays in capitals
        assert tr("as heir, with an allocation of 40%,") == (
            "en tant que héritier, avec une part de 40 %,"  # a known value inside a template
        )
        assert tr("Issued 01 nov. 2026") == "Émis le 01 nov. 2026"
    assert tr("Amount") == "Amount"  # back to English after the block


def test_unknown_text_stays_as_written():
    with doc_language("ar"):
        assert tr("Sunset Towers") == "Sunset Towers"
        assert tr("") == ""
        # no template may catch free text that only happens to contain a common word
        assert tr("Adjustment to balance") == "Adjustment to balance"


def test_every_entry_says_the_same_things_in_each_language():
    placeholder = re.compile(r"\{\d+\}")
    for en, (ar, fr) in TEXT.items():
        wanted = sorted(placeholder.findall(en))
        assert sorted(placeholder.findall(ar)) == wanted, en
        assert sorted(placeholder.findall(fr)) == wanted, en
        assert has_arabic(ar), en
        # the standard PDF fonts draw French; a character outside them would come out as a box
        fr.encode("cp1252")
        # the document font draws vowel marks apart from their letters
        assert not [c for c in ar if unicodedata.category(c) == "Mn"], en


def _ledger_texts() -> set[str]:
    """Every wording a wallet movement is booked with, values replaced by a sample."""

    def texts(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(p.value if isinstance(p, ast.Constant) else "X1" for p in node.values)
        elif isinstance(node, ast.IfExp):
            yield from texts(node.body)
            yield from texts(node.orelse)

    found: set[str] = set()
    for path in SERVICES.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "credit":
                for k in node.keywords:
                    if k.arg == "description":
                        found |= set(texts(k.value))
            # debit lines: (TransactionType.x, amount, "what it says")
            if isinstance(node, ast.Tuple) and len(node.elts) == 3:
                first = node.elts[0]
                if getattr(getattr(first, "value", None), "id", "") == "TransactionType":
                    found |= set(texts(node.elts[2]))
    # built in two steps in the code, so the walk above cannot read it whole
    found.discard("Bank transfer depositX1")
    return found | {"Bank transfer deposit", "Bank transfer deposit — ref X1"}


def test_every_wallet_movement_wording_is_translated():
    texts = _ledger_texts()
    assert len(texts) > 30
    for lang in ("ar", "fr"):
        with doc_language(lang):
            missing = [t for t in sorted(texts) if tr(t) == t]
        assert missing == [], lang


@pytest.mark.parametrize(
    "words",
    [
        statement_service.TYPE_LABELS.values(),
        statement_service.STATUS_LABELS.values(),
        unit_movement_service.LABELS.values(),
        estate_service.ROLES.values(),
        estate_service.SCOPES.values(),
        estate_service.TRIGGERS.values(),
    ],
)
def test_the_fixed_labels_are_translated(words):
    with doc_language("ar"):
        assert [w for w in words if not has_arabic(tr(w))] == []
    with doc_language("fr"):
        assert [w for w in words if tr(w) == w] == []


def test_dates_are_in_the_language_and_english_keeps_its_format():
    assert long_date(NOW) == "01 Nov 2026"
    assert long_date(NOW, "%b %d, %Y") == "Nov 01, 2026"
    assert table_date(NOW) == "01 Nov 2026"
    assert date_range("2026-01-01", "2026-02-01") == "2026-01-01 to 2026-02-01"
    assert status_text("Pending_payment") == "Pending_payment"
    with doc_language("ar"):
        assert long_date(NOW, "%b %d, %Y") == "01 نوفمبر 2026"
        assert table_date(NOW) == "01/11/2026"  # fits its column
        assert status_text("Pending_payment") == "بانتظار الدفع"
    with doc_language("fr"):
        assert long_date(NOW, "%b %d, %Y") == "01 nov. 2026"
    assert all(len(m) == 12 for m in MONTHS.values())


def test_arabic_mirrors_the_page():
    assert mx(100) == 100
    assert mbox(100, 50) == 100
    with doc_language("ar"):
        assert mx(100) == 495
        assert mbox(100, 50) == 445
    with doc_language("fr"):
        assert mx(100) == 100


def test_width_is_measured_as_drawn():
    assert text_width("Total", "Times-Roman", 10) > 0
    # joined letters take less room than the same letters apart, and the font is not Times
    assert 0 < text_width("الإجمالي", "Times-Roman", 10) < 60


# --- the documents ---------------------------------------------------------------------------- #
LATIN_ALLOWED = re.compile(
    r"Capimax PropShare|capimaxpropshare\.com\S*|UTC|USD|Sara Rashid|Layla Hassan"
    r"|Sunset( Towers| SPV)?|Dubai|page \d+|\S+@\S+|[A-Z]+-[\w-]+|AbCd\w+|IBAN|\bC\b"
)


@pytest.mark.parametrize("name", list(DOCUMENTS))
def test_an_arabic_document_leaves_nothing_in_english(name, drawn):
    with doc_language("ar"):
        pdf = DOCUMENTS[name]()
    assert pdf.startswith(b"%PDF")
    assert b"DejaVuSans" in pdf  # the font that has the letters is embedded
    left = sorted({s for s in drawn if re.search(r"[A-Za-z]{3,}", LATIN_ALLOWED.sub("", s))})
    assert left == []


@pytest.mark.parametrize("name", list(DOCUMENTS))
def test_a_french_document_is_french_in_the_standard_fonts(name, drawn):
    pdf = DOCUMENTS[name]()
    english = set(drawn)
    drawn.clear()
    with doc_language("fr"):
        pdf = DOCUMENTS[name]()
    assert pdf.startswith(b"%PDF") and b"DejaVuSans" not in pdf
    # what reads the same in both languages is names, figures and references
    same = {s for s in english & set(drawn) if re.search(r"[a-z]{4,}", LATIN_ALLOWED.sub("", s))}
    assert same <= {"Date", "Type", "Description", "Total", "Parent", "Base"}, same


@pytest.mark.parametrize("name", list(DOCUMENTS))
def test_an_english_document_needs_neither_the_font_nor_the_libraries(name):
    assert b"DejaVuSans" not in DOCUMENTS[name]()


def test_the_title_letter_spacing_does_not_reach_arabic():
    with doc_language("ar"):
        pdf = _certificate()
    assert not re.search(rb"[1-9][\d.]* Tc", pdf)  # spaced-out letters would no longer join
    assert re.search(rb"1\.2 Tc", _certificate())  # English is what it was


def test_a_name_in_arabic_is_drawn_in_any_language():
    english = _certificate(holder="سارة الراشد")
    assert b"DejaVuSans" in english
    assert b"DejaVuSans" not in _certificate(holder="Sara Rashid")


def test_a_long_arabic_value_is_cut_before_it_is_drawn():
    long = "برج " * 80
    with doc_language("ar"):
        clipped = certificate_service._clip(long, "Times-Roman", 12, 120)
    assert clipped.endswith("…") and len(clipped) < len(long)
    assert text_width(clipped, "Times-Roman", 12) <= 120


def test_only_an_arabic_document_keeps_arabic_text():
    assert statement_service.printable("سارة") is None
    assert statement_service.printable("Sara") == "Sara"
    with doc_language("fr"):
        assert statement_service.printable("سارة") is None
    with doc_language("ar"):
        assert statement_service.printable("سارة   الراشد") == "سارة الراشد"
        assert statement_service.printable("Sara") == "Sara"


# --- the spreadsheets ------------------------------------------------------------------------- #
def test_an_arabic_workbook_reads_from_the_right_with_figures_as_figures():
    with doc_language("ar"):
        wb = load_workbook(io.BytesIO(statement_render.render_xlsx(_statement())))
    assert [ws.title for ws in wb.worksheets] == ["كشف الحساب", "ملخص حسب النوع", "الحيازات"]
    assert all(ws.sheet_view.rightToLeft for ws in wb.worksheets)
    ws = wb.worksheets[0]
    cells = [[c.value for c in row] for row in ws.iter_rows()]
    assert ["صاحب الحساب", "Sara Rashid"] == cells[1][:2]
    header = next(r for r in cells if r[0] == "التاريخ (UTC)")
    assert header[:3] == ["التاريخ (UTC)", "النوع", "الوصف"]
    assert isinstance(cells[-1][4], int | float)  # an amount stays a number
    assert isinstance(cells[-1][0], dt.datetime)  # a date stays a date


def test_a_french_workbook_and_an_english_one():
    with doc_language("fr"):
        fr = load_workbook(io.BytesIO(unit_statement_render.render_xlsx(_units())))
    assert fr.worksheets[0].title == "Mouvements de parts"
    assert not fr.worksheets[0].sheet_view.rightToLeft
    assert fr.worksheets[0].cell(row=2, column=1).value == "Titulaire"
    assert fr.worksheets[0].cell(row=5, column=2).value == "du 2026-01-01 au 2026-10-31"
    en = load_workbook(io.BytesIO(unit_statement_render.render_xlsx(_units())))
    assert en.worksheets[0].title == "Unit movements"
    assert not en.worksheets[0].sheet_view.rightToLeft
    assert en.worksheets[0].cell(row=2, column=1).value == "Holder"
