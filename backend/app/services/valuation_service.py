"""The quarterly valuation of an under-construction listing (client letter, 2026-11-18).

The Investment Model section promises the investor that an under-construction property is
revalued every 3 months after purchase, and that a new valuation moves the unit price, the
value of their investment and the change since they bought. Two things make that true:

* a valuation saved in the Listing Editor can be adopted as the new unit price in the same
  step (``price_service.record_price``: the price history, the repricing and the notice to
  every holder), instead of having to repeat it on the Unit prices page;
* the platform keeps the date of each listing's latest valuation and reminds the admins (in
  the panel and by email) when a published under-construction listing has gone 3 months
  without one. The reminder rides on the hourly installment job, is idempotent, and repeats
  every 14 days while the valuation is still missing.

The latest valuation is the newest of: the day a valuation was saved in the editor
(``content.valuation.recordedOn``), the date of a Valuation Reports document (or the day it was
uploaded), and a unit price recorded as a valuation. A listing that never had one counts from
the day it was created.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Notification, Property, User, UserRole
from app.models.base import AppRole, PropertyStatus
from app.models.prices import PropertyPrice
from app.services import listing_service, notification_service

CYCLE_DAYS = 90  # "a valuation every 3 months"
REPEAT_DAYS = 14  # while it is still missing, remind again after this many days
PRICE_LABEL = "Valuation"  # the label of a unit price adopted from a valuation
NOTICE_TYPE = "valuation_due"
PUBLISHED = (PropertyStatus.active, PropertyStatus.funded)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def is_quarterly(prop: Property) -> bool:
    """Under construction (the Investment Model's quarterly promise), published, and open to
    real investors (a sample listing refuses investments)."""
    return (
        listing_service.profile_of(prop.model) in listing_service.OFFPLAN_PROFILES
        and prop.status in PUBLISHED
        and not (prop.content or {}).get("sample")
    )


def _recorded_on(prop: Property) -> dt.date | None:
    raw = ((prop.content or {}).get("valuation") or {}).get("recordedOn")
    try:
        return dt.date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


async def last_valuations(
    session: AsyncSession, props: list[Property]
) -> dict[uuid.UUID, dt.date | None]:
    """The day of each listing's latest valuation (None: never valued)."""
    ids = [p.id for p in props]
    out: dict[uuid.UUID, dt.date | None] = {p.id: _recorded_on(p) for p in props}
    if not ids:
        return out
    docs = await session.execute(
        select(
            Document.property_id,
            func.max(func.coalesce(Document.issued_on, func.date(Document.created_at))),
        )
        .where(Document.property_id.in_(ids), Document.type == "valuation")
        .group_by(Document.property_id)
    )
    prices = await session.execute(
        select(PropertyPrice.property_id, func.max(func.date(PropertyPrice.created_at)))
        .where(
            PropertyPrice.property_id.in_(ids),
            func.lower(func.coalesce(PropertyPrice.label, "")).like("%valuation%"),
        )
        .group_by(PropertyPrice.property_id)
    )
    for pid, day in [*docs.all(), *prices.all()]:
        if day is not None and (out.get(pid) is None or day > out[pid]):
            out[pid] = day
    return out


def status_of(prop: Property, last: dt.date | None, today: dt.date) -> dict:
    """{last, since, days, due, next_due} for one listing (since = the day the 3 months count
    from: the latest valuation, or the day the listing was created)."""
    since = last or (prop.created_at.date() if prop.created_at else today)
    days = (today - since).days
    return {
        "last": last,
        "since": since,
        "days": days,
        "due": is_quarterly(prop) and days >= CYCLE_DAYS,
        "next_due": since + dt.timedelta(days=CYCLE_DAYS),
    }


async def due_listings(session: AsyncSession, *, today: dt.date | None = None) -> list[dict]:
    """Every published under-construction listing whose quarterly valuation is due."""
    today = today or _utcnow().date()
    props = [
        p
        for p in (await session.execute(select(Property).where(Property.status.in_(PUBLISHED))))
        .scalars()
        .all()
        if is_quarterly(p)
    ]
    last = await last_valuations(session, props)
    out = []
    for p in props:
        st = status_of(p, last.get(p.id), today)
        if st["due"]:
            out.append({"property": p, **st})
    return sorted(out, key=lambda r: -r["days"])


def _notice_type(prop_id: uuid.UUID) -> str:
    return f"{NOTICE_TYPE}:{prop_id}"


async def remind_due(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Tell every admin about each listing whose quarterly valuation is due, at most once per
    ``REPEAT_DAYS`` per listing. Returns how many listings were reminded about."""
    now = now or _utcnow()
    due = await due_listings(session, today=now.date())
    if not due:
        return 0
    admins = (
        (
            await session.execute(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role == AppRole.admin, User.closed_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    if not admins:
        return 0
    cutoff = now - dt.timedelta(days=REPEAT_DAYS)
    reminded = 0
    for row in due:
        prop: Property = row["property"]
        recent = await session.scalar(
            select(func.count(Notification.id)).where(
                Notification.type == _notice_type(prop.id), Notification.created_at >= cutoff
            )
        )
        if recent:
            continue
        title = f"Quarterly valuation due: {prop.title}"
        if row["last"]:
            message = (
                f"{prop.title} is under construction and its last valuation was {row['days']} "
                f"days ago, on {row['last'].isoformat()}. Investors are told it is revalued every "
                "3 months: save the new valuation in the Listing Editor and adopt it as the unit "
                "price if it changes."
            )
        else:
            message = (
                f"{prop.title} is under construction and has had no valuation since it was listed "
                f"{row['days']} days ago. Investors are told it is revalued every 3 months: save "
                "the valuation in the Listing Editor and adopt it as the unit price if it changes."
            )
        for admin_id in admins:
            await notification_service.notify(
                session,
                user_id=admin_id,
                type=_notice_type(prop.id),
                title=title,
                message=message,
                email_category="listing_review",
                force_email=True,
            )
        reminded += 1
    return reminded
