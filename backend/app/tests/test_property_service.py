"""Phase 3 — DB-free unit tests for property-catalog pure logic.

Covers slug generation, ownership-model validation, and the serialization
helpers (which turn an ORM row into the API DTO shape). The DB-backed flow
(create -> submit -> approve -> public visibility, authz, edit-lock) is exercised
against Postgres via the integration acceptance run.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.models import Property
from app.models.base import PropertyStatus
from app.services import property_service as svc


def test_slugify_is_lowercase_hyphenated_and_unique() -> None:
    a = svc._slugify("Creek Harbour Tower!!")
    b = svc._slugify("Creek Harbour Tower!!")
    assert a.startswith("creek-harbour-tower-")
    assert a != b  # uuid suffix makes repeated calls unique
    assert " " not in a and a == a.lower()


def test_slugify_handles_empty_title() -> None:
    assert svc._slugify("!!!").startswith("property-")


def test_validate_model_accepts_known_and_rejects_unknown() -> None:
    assert svc._validate_model("installment") == "installment"
    with pytest.raises(AppError) as exc:
        svc._validate_model("not-a-model")
    assert exc.value.code == "INVALID_MODEL"


def _make_prop() -> Property:
    return Property(
        id=uuid.uuid4(),
        owner_id=None,
        title="Sample Tower",
        subtitle="A nice tower",
        description="desc",
        location="Dubai, UAE",
        country="UAE",
        city="Dubai",
        property_type="apartment",
        model="ready-income",
        slug="sample-tower-abc123",
        status=PropertyStatus.active,
        total_value=1000000,
        unit_price=100,
        total_units=10000,
        available_units=10000,
        minimum_investment=100,
        target_yield=8,
        expected_yield=8.4,
        capital_appreciation=4.8,
        total_return=13.2,
        funding_progress=62,
        investors_count=218,
        funded_amount=620000,
        images=["https://img/one.jpg", "https://img/two.jpg"],
        content={"developer": {"name": "Elite Gate Properties"}, "badge": "Ready"},
        fees={"platform_fee": 2.5, "management_fee": 1.0},
    )


def test_serialize_summary_shape_and_derived_fields() -> None:
    prop = _make_prop()
    out = svc.serialize_summary(prop, {})
    assert out["status"] == "active"
    assert out["image"] == "https://img/one.jpg"  # first image
    assert out["developer_name"] == "Elite Gate Properties"  # from content
    assert out["total_value"] == 1000000.0 and isinstance(out["total_value"], float)
    assert out["model"] == "ready-income"
    assert out["funding_progress"] == 62.0


def test_developer_name_falls_back_to_owner() -> None:
    prop = _make_prop()
    prop.content = {}
    owner = uuid.uuid4()
    prop.owner_id = owner
    out = svc.serialize_summary(prop, {owner: "Jane Owner"})
    assert out["developer_name"] == "Jane Owner"


def test_serialize_detail_includes_rich_content() -> None:
    prop = _make_prop()
    out = svc.serialize_detail(prop, {})
    assert out["description"] == "desc"
    assert out["images"] == ["https://img/one.jpg", "https://img/two.jpg"]
    assert out["content"]["badge"] == "Ready"
    assert out["fees"] == {"platform_fee": 2.5, "management_fee": 1.0}


def test_summary_image_is_none_when_no_images() -> None:
    prop = _make_prop()
    prop.images = []
    assert svc.serialize_summary(prop, {})["image"] is None
