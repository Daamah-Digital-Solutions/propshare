"""Client letter (2026-11-18, as on Capimax BRX): a property card shows how many investors hold the
property, counted live: people with units now or an installment plan still running. Someone who
bought twice is one investor; someone who sold everything is none."""

from __future__ import annotations

import uuid

import pytest

from app.tests.test_developer_profile_db import _prop


def _user(db) -> str:
    uid = str(uuid.uuid4())
    db(
        "INSERT INTO users (id, email, full_name) VALUES (:i, :e, 'Investor')",
        i=uid,
        e=f"c-{uid[:8]}@x.com",
    )
    return uid


def _ledger(db, uid: str, pid: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason) "
        "VALUES (:u, :p, :n, 100, :r)",
        u=uid,
        p=pid,
        n=units,
        r="purchase" if units > 0 else "secondary_sale",
    )


@pytest.mark.asyncio
async def test_the_card_counts_the_people_holding_the_property_now(client, db):
    pid = _prop(db, title="Count Tower")
    twice, sold_all, payer = _user(db), _user(db), _user(db)
    _ledger(db, twice, pid, 3)
    _ledger(db, twice, pid, 2)  # bought again: still one investor
    _ledger(db, sold_all, pid, 4)
    _ledger(db, sold_all, pid, -4)  # sold everything: no longer an investor
    db(
        "INSERT INTO installment_plans (investor_id, property_id, units_total, unit_price, "
        "down_payment_pct, duration_months, fee_rate, management_fee_rate, status) "
        "VALUES (:u, :p, 10, 100, 20, 12, 4, 1, 'active')",
        u=payer,
        p=pid,
    )
    db("UPDATE properties SET investors_count = 99 WHERE id = :p", p=pid)  # purchases counted

    items = (await client.get("/api/v1/properties")).json()["items"]
    card = next(i for i in items if i["id"] == pid)
    assert card["investors_count"] == 2
    detail = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert detail["investors_count"] == 2
