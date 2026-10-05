"""Informational tools: public data any visitor may see (plan §4 tool inventory).

Every number comes from the live database or platform settings, never from the knowledge
base, so the assistant cannot quote a stale fee or price.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Document, KbArticle
from app.services import (
    document_service,
    installment_service,
    investment_service,
    listing_service,
    payment_service,
    platform_accounts_service,
    price_service,
    property_service,
    reference_library,
    settings_service,
    withdrawal_service,
)
from app.services.assistant import guard, platform_gaps
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import NoArgs, ToolOutput, ToolSpec, register

_CENTS = decimal.Decimal("0.01")


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


# --------------------------------------------------------------------------- #
# get_platform_settings
# --------------------------------------------------------------------------- #
class Fees(ToolOutput):
    platform_fee_pct: str
    management_fee_pct: str
    installment_fee_pct: str
    secondary_resale_fee_pct: str
    liquidity_discount_pct: str
    liquidity_fee_pct: str


class Discounts(ToolOutput):
    reinvest_discount_pct: str
    pronova_discount_pct: str


class InstallmentTerms(ToolOutput):
    down_pct_by_months: dict[str, int]
    note: str


class DepositRails(ToolOutput):
    card: bool
    crypto: bool
    bank_transfer: bool


class PurchaseMethods(ToolOutput):
    """How units are paid for — the same on every property (0032)."""

    wallet: bool
    card: bool
    apple_pay: bool
    google_pay: bool
    crypto: bool
    pronova: bool
    nova_sukuk: bool
    note: str


class WithdrawalRails(ToolOutput):
    bank: str  # "automatic" (paid through the provider on request) or "reviewed" (by the team)
    crypto: str
    instant_enabled: bool
    instant_fee_pct: str
    instant_max_amount: str
    note: str


class PlatformSettingsOut(ToolOutput):
    fees: Fees
    discounts: Discounts
    installment: InstallmentTerms
    deposit_rails: DepositRails
    purchase_methods: PurchaseMethods
    withdrawal_rails: WithdrawalRails
    currency: str
    as_of: str


async def _get_platform_settings(session: AsyncSession, ctx: AgentContext, args) -> dict:
    from app.core.config import get_settings

    async def g(key: str) -> str:
        return await settings_service.get_setting(session, key)

    banks = await platform_accounts_service.list_active(session)
    return {
        "fees": {
            "platform_fee_pct": await g("platform_fee_pct"),
            "management_fee_pct": await g("management_fee_pct"),
            "installment_fee_pct": await g("installment_fee_pct"),
            "secondary_resale_fee_pct": await g("secondary_resale_fee_pct"),
            "liquidity_discount_pct": await g("liquidity_discount_pct"),
            "liquidity_fee_pct": await g("liquidity_fee_pct"),
        },
        "discounts": {
            "reinvest_discount_pct": await g("reinvest_discount_pct"),
            "pronova_discount_pct": await g("pronova_discount_pct"),
        },
        "installment": {
            "down_pct_by_months": {
                str(m): d for m, d in sorted(installment_service._DOWN_PCT.items())
            },
            "note": (
                "One standard plan for every off-plan listing: the down payment is paid now, "
                "the rest in equal monthly installments; the installment fee applies to the "
                "down payment and each installment; units vest with each payment; a missed "
                "payment is retried with reminders, no late fee, no forfeit."
            ),
        },
        "deposit_rails": {
            "card": payment_service.provider_configured("card"),
            "crypto": payment_service.provider_configured("crypto"),
            "bank_transfer": len(banks) > 0,
        },
        "purchase_methods": _purchase_methods(),
        "withdrawal_rails": await _withdrawal_rails(session),
        "currency": get_settings().wallet_currency,
        "as_of": _now(),
    }


def _purchase_methods() -> dict:
    live = payment_service.purchase_options()
    return {
        "wallet": live["wallet"],
        "card": live["card"],
        "apple_pay": live["apple_pay"],
        "google_pay": live["google_pay"],
        "crypto": live["crypto"],
        "pronova": live["pronova"],
        "nova_sukuk": live["sukuk"],
        "note": (
            "The same methods on every property, for a purchase and for an installment plan's "
            "down payment (the installments then come from the wallet). Card, Apple Pay, Google "
            "Pay and Pronova pay on Stripe's checkout — Pronova takes pronova_discount_pct off "
            "what is paid now; crypto on NOWPayments' page, where the payer picks the coin. A "
            "Nova Sukuk certificate (PDF) is reviewed by the team while the units are held; "
            "approved, the units are the investor's but stay pledged to Nova Finance (not "
            "sellable or transferable) until the team releases the pledge."
        ),
    }


async def _withdrawal_rails(session: AsyncSession) -> dict:
    config = await withdrawal_service.payout_config(session)
    modes = {
        m: "reviewed" if v["mode"] == "manual" else "automatic"
        for m, v in config["methods"].items()
    }
    instant = modes.get("bank") == "automatic" and await withdrawal_service._instant_enabled(
        session
    )
    return {
        "bank": modes.get("bank", "reviewed"),
        "crypto": modes.get("crypto", "reviewed"),
        "instant_enabled": instant,
        "instant_fee_pct": str(await withdrawal_service._instant_fee_pct(session)),
        "instant_max_amount": str(await withdrawal_service._instant_max(session)),
        "note": (
            "Automatic bank withdrawals go to the bank account the investor linked through "
            "Stripe (US, UK, EEA, Canada, Switzerland); others are reviewed and paid by the "
            "team. Instant = to an eligible debit card within minutes for the fee above, "
            "deducted from the amount; whether a given investor can use it is shown on "
            "their wallet page. Reviewed withdrawals are paid after the team's check."
        ),
    }


register(
    ToolSpec(
        "get_platform_settings",
        "Live platform fees, discounts, the standard installment plan terms, which deposit "
        "methods are available and how withdrawals are paid (automatic, reviewed, instant "
        "and its fee) right now. Use this for ANY question about fees, terms or payouts.",
        NoArgs,
        PlatformSettingsOut,
        "informational",
        _get_platform_settings,
    )
)


# --------------------------------------------------------------------------- #
# search_properties / get_property
# --------------------------------------------------------------------------- #
class SearchPropertiesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str | None = Field(default=None, description="Free text: title or location")
    model: str | None = Field(default=None, description="Ownership model key")
    property_type: str | None = None
    city: str | None = None
    country: str | None = None
    min_yield: float | None = Field(default=None, ge=0, le=100)
    max_price: float | None = Field(
        default=None, ge=0, description="Highest value of the WHOLE property, in USD"
    )
    budget: float | None = Field(
        default=None,
        gt=0,
        description="An amount the user has to invest, in USD: only listings they can enter "
        "with it (minimum investment at most this), with the units it buys in each",
    )
    sort: str | None = Field(
        default=None,
        description="newest | yield (highest projected yield first) | price (lowest property "
        "value first) | entry (lowest amount to get in first) | funded; empty = entry with a "
        "budget, else newest",
    )
    limit: int = Field(default=5, ge=1, le=10)


_SORTS = {
    "newest": "newest",
    "yield": "yield-high",
    "price": "price-low",
    "entry": "entry-low",
    "funded": "funded",
}


class PropertyCard(ToolOutput):
    id: str
    slug: str | None
    title: str
    location: str
    country: str | None
    city: str | None
    model: str
    model_label: str
    property_type: str
    status: str
    unit_price: float | None
    minimum_investment: float | None
    total_value: float | None  # the whole property at today's unit price
    target_yield: float | None
    expected_yield: float | None
    capital_appreciation: float | None
    total_return: float | None
    funding_progress: float | None
    available_units: int
    developer_name: str | None
    developer_slug: str | None
    image: str | None  # platform-relative file URL, for the chat card thumbnail
    # how units are bought: full (paid at once) | installments (the plan) | both
    payment: str = "full"
    # unit_price is the CURRENT price; a listing under construction gets a new one as it is
    # revalued or a sales phase opens: where it started and how far it has moved since
    launch_price: float | None = None
    price_change_pct: float | None = None
    price_updated_at: str | None = None
    # with a budget: the least that gets you in, and the whole units the budget buys here
    entry_amount: float | None = None
    units_for_budget: int | None = None


class SearchPropertiesOut(ToolOutput):
    items: list[PropertyCard]
    total: int
    # with a budget: the smallest amount that gets into ANY listing (when nothing fits the
    # budget, say so and give this)
    lowest_entry: float | None = None
    as_of: str


def _card(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "title": row["title"],
        "location": row["location"],
        "country": row["country"],
        "city": row["city"],
        "model": row["model"],
        "model_label": listing_service.purchase_label(row["model"], row.get("offplan_payment")),
        "property_type": row["property_type"],
        "status": row["status"],
        "unit_price": row["unit_price"],
        "minimum_investment": row["minimum_investment"],
        "total_value": _asset_value(row),
        "target_yield": row["target_yield"],
        "expected_yield": row["expected_yield"],
        "capital_appreciation": row["capital_appreciation"],
        "total_return": row["total_return"],
        "funding_progress": row["funding_progress"],
        "available_units": row["available_units"],
        "developer_name": row["developer_name"],
        "developer_slug": row.get("developer_slug"),
        "image": row.get("image"),
        "payment": _payment(row["model"], row.get("offplan_payment")),
    }


def _asset_value(row: dict) -> float | None:
    """All the units at today's unit price. The listing's own ``total_value`` is the offering's
    total: what was paid for the units already sold plus the rest at today's price, so after a
    price change it is not what the property is worth."""
    units, price = row.get("total_units"), row.get("unit_price")
    if row.get("launch_price") is not None and units and price:  # the price has moved
        return float(decimal.Decimal(str(price)) * int(units))
    return row.get("total_value")


def _payment(model: str | None, offplan_payment: str | None) -> str:
    """full | installments | both: a ready listing is paid in full; one under construction
    says which (the listing's own choice)."""
    if listing_service.profile_of(model) not in listing_service.OFFPLAN_PROFILES:
        return "full"
    return offplan_payment or "installments"


async def _with_prices(session: AsyncSession, cards: list[dict]) -> list[dict]:
    """Add each card's price line: the launch price, the move since, the last change."""
    ids = [uuid.UUID(c["id"]) for c in cards]
    summaries = await price_service.summaries(session, ids)
    for card in cards:
        info = summaries.get(uuid.UUID(card["id"]))
        price = card["unit_price"]
        if info is None or price is None:
            card["launch_price"] = price
            card["price_change_pct"] = 0.0 if price is not None else None
            continue
        launch = decimal.Decimal(info["launch_price"])
        card["launch_price"] = float(launch)
        card["price_change_pct"] = float(
            price_service.change_pct(launch, decimal.Decimal(str(price)))
        )
        card["price_updated_at"] = info["updated_at"].date().isoformat()
    return cards


def _budget_fit(card: dict, budget: float | None) -> dict:
    """The least that gets into this listing and the whole units ``budget`` buys in it."""
    price = card["unit_price"]
    entry = card["minimum_investment"] or price
    card["entry_amount"] = entry
    if budget is not None and price:
        card["units_for_budget"] = min(int(budget // price), card["available_units"])
    return card


async def _search_properties(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: SearchPropertiesIn = args
    rows, total = await property_service.list_public(
        session,
        model=a.model,
        property_type=a.property_type,
        country=a.country,
        city=a.city,
        min_yield=a.min_yield,
        max_price=a.max_price,
        max_entry=a.budget,
        search=a.search,
        sort=_SORTS.get(a.sort or "", "entry-low" if a.budget else "newest"),
        limit=a.limit,
        offset=0,
    )
    names = await property_service._owner_names(session, rows)
    cards = [
        _budget_fit(_card(property_service.serialize_summary(p, names)), a.budget) for p in rows
    ]
    return {
        "items": await _with_prices(session, cards),
        "total": int(total),
        "lowest_entry": await property_service.lowest_entry(session) if a.budget else None,
        "as_of": _now(),
    }


register(
    ToolSpec(
        "search_properties",
        "Search the marketplace (published listings only). Returns up to 10 property cards "
        "with live prices, yields and availability, how each is bought (payment: full, "
        "installments or both) and how far its unit price has moved since launch. When the "
        "user mentions an amount they have or want to invest, pass it as budget: you get only "
        "the listings it can enter, the units it buys in each and the lowest entry anywhere.",
        SearchPropertiesIn,
        SearchPropertiesOut,
        "informational",
        _search_properties,
    )
)


class GetPropertyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_or_slug: str = Field(min_length=1, max_length=160)


class MilestoneOut(ToolOutput):
    title: str
    status: str
    target_date: str | None
    progress_pct: int | None


class DocumentOut(ToolOutput):
    title: str
    category: str


class PricePointOut(ToolOutput):
    date: str
    price: float
    change_pct: float  # the move this change made
    label: str | None  # a sales phase or stage this price opened
    note: str | None


class PropertyDetailOut(PropertyCard):
    # the unit price over time: the launch price, then each change recorded since (newest
    # last, at most the 12 latest)
    price_history: list[PricePointOut]
    phase: str | None  # the sales phase the latest price opened, when it named one
    description: str | None
    subtitle: str | None
    expected_completion: str | None
    construction_progress: int
    spv_name: str | None
    legal_structure: str | None
    listing_fees: dict[str, float]
    terms: dict[str, str]
    amenities: list[str]
    milestones: list[MilestoneOut]
    documents: list[DocumentOut]
    page_path: str
    as_of: str


async def _get_property(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: GetPropertyIn = args
    prop = await property_service.get_public_detail(session, a.id_or_slug)
    names = await property_service._owner_names(session, [prop])
    card = (await _with_prices(session, [_card(property_service.serialize_summary(prop, names))]))[
        0
    ]
    line = await price_service.history(session, prop)
    milestones = await listing_service.list_milestones(session, prop.id)
    docs = await document_service.list_property_documents(session, a.id_or_slug)
    content = prop.content if isinstance(prop.content, dict) else {}
    fees = content.get("fees") or {}
    terms = content.get("terms") or {}
    details = content.get("details") or {}
    return {
        **card,
        "price_history": [
            {
                "date": pt["at"].date().isoformat() if pt["at"] else "",
                "price": float(pt["price"]),
                "change_pct": float(pt["change_pct"]),
                "label": pt["label"],
                "note": pt["note"],
            }
            for pt in line["points"][-12:]
        ],
        "phase": line["phase"],
        "description": prop.description,
        "subtitle": prop.subtitle,
        "expected_completion": _s(prop.expected_completion),
        "construction_progress": listing_service.construction_progress(milestones),
        "spv_name": prop.spv_name,
        "legal_structure": prop.legal_structure,
        "listing_fees": {k: float(v) for k, v in fees.items() if isinstance(v, int | float)},
        "terms": {k: str(v) for k, v in terms.items() if v},
        "amenities": [str(x) for x in (details.get("amenities") or [])],
        "milestones": [
            {
                "title": m.title,
                "status": str(m.status),
                "target_date": _s(m.target_date),
                "progress_pct": m.progress_pct,
            }
            for m in milestones
        ],
        "documents": [{"title": d.title, "category": d.type} for d in docs],
        "page_path": f"/property/{prop.slug or prop.id}",
        "as_of": _now(),
    }


register(
    ToolSpec(
        "get_property",
        "Full public details of one published listing by id or slug: numbers, description, "
        "milestones, document titles and the page link, plus how it is bought (payment) and "
        "its unit price over time (price_history: the launch price, then each new price the "
        "platform recorded; unit_price is the price now). Never invent a property.",
        GetPropertyIn,
        PropertyDetailOut,
        "informational",
        _get_property,
    )
)


# --------------------------------------------------------------------------- #
# compare_properties
# --------------------------------------------------------------------------- #
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


class CompareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    properties: list[str] = Field(
        description="2 to 4 published properties to compare: slug, id or name"
    )


class CompareItem(ToolOutput):
    title: str
    slug: str | None
    city: str | None
    country: str | None
    model_label: str
    property_type: str
    status: str
    purchase: str  # direct | installment | either (the investor chooses)
    unit_price: float | None
    minimum_investment: float | None
    expected_yield: float | None
    capital_appreciation: float | None
    total_return: float | None
    funding_progress: float | None
    available_units: int
    expected_completion: str | None
    exit_options: list[str]
    exit_fee_pct: float | None
    risks: list[str]  # "label: level", from the listing's risk disclosures
    highest_risk: str | None  # low | medium | high
    developer_name: str | None
    image: str | None
    page_path: str


class CompareOut(ToolOutput):
    items: list[CompareItem]
    not_found: list[str]
    platform_fee_pct: str
    note: str
    as_of: str


async def _find_public(session: AsyncSession, ref: str):
    """A published listing by id or slug, else by name (title or location)."""
    try:
        return await property_service.get_public_detail(session, ref)
    except AppError:
        rows, _total = await property_service.list_public(session, search=ref, limit=1, offset=0)
        return rows[0] if rows else None


async def _compare_properties(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: CompareIn = args
    refs = list(dict.fromkeys(r.strip() for r in a.properties if r.strip()))[:4]
    found, missing, seen = [], [], set()
    for ref in refs:
        prop = await _find_public(session, ref[:160])
        if prop is None:
            missing.append(ref[:80])
        elif prop.id not in seen:
            seen.add(prop.id)
            found.append(prop)
    if len(found) < 2:
        raise AppError(
            "NEED_TWO",
            "Comparing needs at least two published properties"
            + (f"; not found: {', '.join(missing)}." if missing else "."),
            status_code=422,
        )
    names = await property_service._owner_names(session, found)
    items = []
    for prop in found:
        card = _card(property_service.serialize_summary(prop, names))
        content = prop.content if isinstance(prop.content, dict) else {}
        risks = [r for r in content.get("risks") or [] if isinstance(r, dict) and r.get("label")]
        levels = [str(r.get("level")) for r in risks if r.get("level") in _RISK_ORDER]
        exits = [
            str(m["name"])
            for m in content.get("exitMechanisms") or []
            if isinstance(m, dict) and m.get("name")
        ]
        if not exits and (content.get("terms") or {}).get("exitOptions"):
            exits = [str(content["terms"]["exitOptions"])]
        exit_fee = (content.get("fees") or {}).get("exit")
        items.append(
            {
                **{k: card[k] for k in CompareItem.model_fields if k in card},
                "purchase": {"full": "direct", "installments": "installment"}.get(
                    card["payment"], "either"
                ),
                "expected_completion": _s(prop.expected_completion),
                "exit_options": exits[:4],
                "exit_fee_pct": float(exit_fee) if isinstance(exit_fee, int | float) else None,
                "risks": [
                    f"{r['label']}: {r['level']}" if r.get("level") else str(r["label"])
                    for r in risks[:4]
                ],
                "highest_risk": max(levels, key=_RISK_ORDER.get) if levels else None,
                "page_path": f"/property/{prop.slug or prop.id}",
            }
        )
    rates = await settings_service.get_fee_rates(session)
    return {
        "items": items,
        "not_found": missing,
        "platform_fee_pct": f"{rates['platform_fee_pct'].normalize():f}",
        "note": "Yields and returns are the listings' projections, not promises. The comparison "
        "is information, not a recommendation.",
        "as_of": _now(),
    }


register(
    ToolSpec(
        "compare_properties",
        "Compare 2 to 4 published properties side by side (by slug, id or name): price, "
        "minimum, projected yield and return, stage and how it is bought, funding, completion, "
        "exit options and fee, and the listed risk disclosures. The user sees a comparison "
        "table card.",
        CompareIn,
        CompareOut,
        "informational",
        _compare_properties,
    )
)


# --------------------------------------------------------------------------- #
# search_kb (approved articles only)
# --------------------------------------------------------------------------- #
class SearchKbIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)
    lang: str = Field(default="en", pattern="^(en|ar)$")
    limit: int = Field(default=3, ge=1, le=5)


class KbHit(ToolOutput):
    slug: str
    title: str
    snippet: dict[str, str]  # {"untrusted_text": ...}
    lang: str
    updated_at: str


class SearchKbOut(ToolOutput):
    items: list[KbHit]


async def _search_kb(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: SearchKbIn = args
    words = [w for w in a.query.lower().split() if len(w) > 2][:6]
    stmt = select(KbArticle).where(
        KbArticle.status == "approved",
        KbArticle.lang == a.lang,
        KbArticle.audience != reference_library.REFERENCE_AUDIENCE,
    )
    if words:
        stmt = stmt.where(
            or_(
                *[KbArticle.title.ilike(f"%{w}%") for w in words],
                *[KbArticle.body_md.ilike(f"%{w}%") for w in words],
            )
        )
    rows = (await session.execute(stmt.order_by(KbArticle.priority).limit(a.limit))).scalars().all()
    return {
        "items": [
            {
                "slug": r.slug,
                "title": r.title,
                "snippet": guard.wrap_untrusted(r.body_md[:600]),
                "lang": r.lang,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }


register(
    ToolSpec(
        "search_kb",
        "Search the approved help articles (how things work, policies). Never contains "
        "numbers: use get_platform_settings or get_property for figures.",
        SearchKbIn,
        SearchKbOut,
        "informational",
        _search_kb,
    )
)


# --------------------------------------------------------------------------- #
# search_reference (the company's own reference documents)
# --------------------------------------------------------------------------- #
class SearchReferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        min_length=2,
        max_length=200,
        description="Keywords, best in English (the library is mostly English), e.g. "
        "'Nova financing', 'LexCrest legal due diligence', 'insurance partners'",
    )
    limit: int = Field(default=3, ge=1, le=4)


class ReferenceHit(ToolOutput):
    source: str
    section: str
    lang: str
    text: dict[str, str]  # {"untrusted_text": ...}


class SearchReferenceOut(ToolOutput):
    items: list[ReferenceHit]
    # what these passages describe that the platform does not do yet: overrides the passages
    not_on_platform_yet: list[str]
    note: str


async def _search_reference(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: SearchReferenceIn = args
    rows = await reference_library.search(session, a.query, a.limit)
    return {
        "items": [
            {
                "source": (r.source_ref or "").split(" | ")[-1],
                "section": r.title,
                "lang": r.lang,
                "text": guard.wrap_untrusted(r.body_md),
            }
            for r in rows
        ],
        "not_on_platform_yet": platform_gaps.notes_for(a.query, [r.body_md for r in rows]),
        "note": (
            "Company reference material describing the complete target platform. Anything "
            "listed in not_on_platform_yet is not available today: say so first, plainly, and "
            "never present it as available. Fees, installment terms, payment methods and what "
            "the user can do right now come from the live tools; where they differ, the live "
            "tools apply."
        ),
    }


register(
    ToolSpec(
        "search_reference",
        "Search the company's approved reference library: what PropShare is, the Capimax "
        "ecosystem (Group, One, Assets, BRX, RT, Pro/CPV, Nova Digital Finance, Pronova/PRN), "
        "partners and service providers (payments, banking, KYC, valuation, legal, insurance, "
        "developers, hotel/property/facility operators), the operating model, participant "
        "journeys, policies, disclosures and the FAQ. Returns the best-matching passages.",
        SearchReferenceIn,
        SearchReferenceOut,
        "informational",
        _search_reference,
    )
)


# --------------------------------------------------------------------------- #
# prepare_deep_link
# --------------------------------------------------------------------------- #
class DeepLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: str = Field(description="One of: " + ", ".join(sorted(guard.DEEP_LINKS)))
    slug: str | None = Field(
        default=None,
        description="Property slug (route_id=property) or developer slug (route_id=developer)",
    )


class DeepLinkOut(ToolOutput):
    route_id: str
    path: str
    label: str


async def _prepare_deep_link(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: DeepLinkIn = args
    return guard.make_link(a.route_id, a.slug)


register(
    ToolSpec(
        "prepare_deep_link",
        "Get the in-app link for a screen (wallet, deposit, KYC, a property page...). Only "
        "these links may be shown to the user.",
        DeepLinkIn,
        DeepLinkOut,
        "informational",
        _prepare_deep_link,
    )
)


# --------------------------------------------------------------------------- #
# quote_investment (prepare only: same eligibility as the invest endpoint)
# --------------------------------------------------------------------------- #
class QuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_or_slug: str = Field(min_length=1, max_length=160)
    units: int | None = Field(
        default=None, ge=1, le=1_000_000, description="Whole units wanted (preferred)"
    )
    amount: float | None = Field(
        default=None, gt=0, le=100_000_000, description="Or: an amount to spend, in USD"
    )
    duration_months: int | None = Field(
        default=None, description="Installment plan length for off-plan listings"
    )
    pay: str | None = Field(
        default=None,
        pattern="^(full|installments)$",
        description="For a listing that can be bought both ways: full = pay at once, "
        "installments = the plan. Empty: the plan when a duration is given, else full payment",
    )


class ScheduleRow(ToolOutput):
    seq: int
    kind: str
    base_amount: str
    fee_amount: str
    total_amount: str


class QuoteOut(ToolOutput):
    property_title: str
    slug: str | None
    duration_months: int | None
    ready_to_pay: bool  # no blocking eligibility note: the checkout can go straight to payment
    model: str
    units: int
    unit_price: str
    subtotal: str
    platform_fee_pct: str
    platform_fee: str
    total_now: str
    minimum_investment: str
    purchase_type: str  # direct | installment
    payment_options: list[str]  # how this listing can be bought: full and/or installments
    down_payment_pct: int | None
    installment_fee_pct: str | None
    schedule: list[ScheduleRow]
    eligibility_notes: list[str]
    as_of: str


async def _quote_investment(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: QuoteIn = args
    prop = await property_service.get_public_detail(session, a.id_or_slug)
    unit = decimal.Decimal(prop.unit_price)
    if a.units is not None:
        units = a.units
    elif a.amount is not None:
        units = int(decimal.Decimal(str(a.amount)).quantize(_CENTS) // unit)
    else:
        raise AppError("BAD_QUOTE", "Give a number of units or an amount.", status_code=422)
    notes: list[str] = []
    blocking = False
    if str(prop.status) != "active":
        notes.append("This listing is not open for investment right now.")
        blocking = True
    if units < 1 or unit * units < decimal.Decimal(prop.minimum_investment):
        blocking = True
        notes.append(
            f"The minimum for this listing is {prop.minimum_investment} "
            f"(whole units of {prop.unit_price}); amounts are rounded down to whole units."
        )
    if units > prop.available_units:
        notes.append(f"Only {prop.available_units} units are still available.")
        blocking = True
    if ctx.is_visitor:
        notes.append("Sign in and complete identity verification before investing.")
        blocking = True
    elif ctx.kyc_status != "verified":
        notes.append("Identity verification must be approved before investing.")
        blocking = True
    modes = investment_service.payment_modes(prop)
    # by the plan when the listing offers nothing else, or the user asked for it (a duration
    # is asking for it); in full otherwise
    by_plan = "installments" in modes and (
        "full" not in modes or a.pay == "installments" or (a.pay is None and a.duration_months)
    )
    if a.pay == "full" and "full" not in modes:
        notes.append("This listing is bought through its installment plan, not paid in full.")
    if (a.pay == "installments" or a.duration_months) and "installments" not in modes:
        notes.append("This listing is paid in full: it has no installment plan.")
    months: int | None = None
    subtotal = (unit * units).quantize(_CENTS)
    rates = await settings_service.get_fee_rates(session)
    platform_pct = rates["platform_fee_pct"]
    schedule: list[dict] = []
    down_pct = None
    inst_fee = None
    if by_plan:
        months = a.duration_months or 12
        table = installment_service._DOWN_PCT
        if months not in table:
            notes.append(
                f"Installment plans run {', '.join(str(m) for m in sorted(table))} months."
            )
            months = 12
        down_pct = table[months]
        fee_pct = await settings_service.get_installment_fee_pct(session)
        inst_fee = f"{fee_pct.normalize():f}"
        # the platform's own split: down payment + (months - 1) installments, as a plan is made
        bases = installment_service.schedule_bases(subtotal, months)
        for i, base in enumerate(bases):
            kind = "down_payment" if i == 0 else "final" if i == len(bases) - 1 else "installment"
            fee = installment_service.fee_for(base, fee_pct)
            schedule.append(
                {
                    "seq": i,
                    "kind": kind,
                    "base_amount": f"{base:.2f}",
                    "fee_amount": f"{fee:.2f}",
                    "total_amount": f"{(base + fee):.2f}",
                }
            )
        platform_fee = decimal.Decimal(0)
        total_now = decimal.Decimal(schedule[0]["total_amount"]) if schedule else decimal.Decimal(0)
        if "full" in modes:
            notes.append("This listing can also be paid in full, at once.")
        else:
            notes.append("Off-plan listings are bought through the standard installment plan.")
    else:
        platform_fee = (subtotal * platform_pct / 100).quantize(_CENTS)
        total_now = subtotal + platform_fee
        if "installments" in modes:
            notes.append(
                "This listing can also be bought through the installment plan: a down payment "
                "now, then monthly installments."
            )
    return {
        "property_title": prop.title,
        "slug": prop.slug,
        "duration_months": months,
        "ready_to_pay": not blocking,
        "model": prop.model,
        "units": units,
        "unit_price": f"{unit:.2f}",
        "subtotal": f"{subtotal:.2f}",
        "platform_fee_pct": f"{platform_pct.normalize():f}",
        "platform_fee": f"{platform_fee:.2f}",
        "total_now": f"{total_now:.2f}",
        "minimum_investment": f"{decimal.Decimal(prop.minimum_investment):.2f}",
        "purchase_type": "installment" if by_plan else "direct",
        "payment_options": list(modes),
        "down_payment_pct": down_pct,
        "installment_fee_pct": inst_fee,
        "schedule": schedule[:25],
        "eligibility_notes": notes,
        "as_of": _now(),
    }


register(
    ToolSpec(
        "quote_investment",
        "Prepare an order on a listing, from a number of units (preferred) or an amount: whole "
        "units, fees, total payable now, and for a purchase by installments the schedule. A "
        "listing under construction is bought by its installment plan, in full, or either "
        "(payment_options says which; pay chooses when both are offered). The user then sees "
        "an order card whose button opens the checkout pre-filled, stopping at payment. "
        "Prepares only; nothing is bought or charged.",
        QuoteIn,
        QuoteOut,
        "prepare_only",
        _quote_investment,
    )
)


def _unused(*_: Any) -> None:  # keeps AppError/Document imports meaningful for type checkers
    return None


_unused(AppError, Document)
