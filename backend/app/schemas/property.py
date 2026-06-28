"""Property catalog DTOs (Phase 3).

Money/metric fields are returned as plain numbers for catalog display (these are
listing attributes, not user balances — the money-rules ledger arrives in Phase
4+). Amounts the client sends on create/update are validated but the SERVER is
authoritative on status (always starts ``draft``), owner_id, funded_amount,
funding_progress and investors_count — the client cannot set those.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.milestone import MilestoneOut

# The 7 ownership models the SPA renders (mirror of the frontend SampleOwnershipModel).
OWNERSHIP_MODELS = (
    "ready-income",
    "installment",
    "future",
    "option",
    "shared-development",
    "ready-portfolio",
    "construction-portfolio",
)


class PropertyCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    property_type: str = Field(min_length=2, max_length=60)
    location: str = Field(min_length=2, max_length=200)
    description: str | None = None
    total_value: float = Field(gt=0)
    unit_price: float = Field(gt=0)
    total_units: int = Field(default=100, gt=0)
    minimum_investment: float = Field(default=500, ge=0)
    target_yield: float | None = Field(default=None, ge=0, le=100)
    expected_completion: dt.date | None = None
    spv_name: str | None = None
    spv_registration: str | None = None
    legal_structure: str | None = None
    # Catalog presentation
    model: str = "ready-income"
    subtitle: str | None = None
    country: str | None = None
    city: str | None = None
    expected_yield: float | None = Field(default=None, ge=0, le=100)
    capital_appreciation: float | None = Field(default=None, ge=-100, le=1000)
    total_return: float | None = Field(default=None, ge=-100, le=1000)
    images: list[str] = Field(default_factory=list)
    # Rich, model-specific content (ownership/investment structure, timeline,
    # scenarios, risks, exit mechanisms, model terms, spv detail, amenities...).
    content: dict = Field(default_factory=dict)


class PropertyUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    property_type: str | None = None
    location: str | None = None
    description: str | None = None
    total_value: float | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, gt=0)
    total_units: int | None = Field(default=None, gt=0)
    minimum_investment: float | None = Field(default=None, ge=0)
    target_yield: float | None = Field(default=None, ge=0, le=100)
    expected_completion: dt.date | None = None
    spv_name: str | None = None
    spv_registration: str | None = None
    legal_structure: str | None = None
    model: str | None = None
    subtitle: str | None = None
    country: str | None = None
    city: str | None = None
    expected_yield: float | None = Field(default=None, ge=0, le=100)
    capital_appreciation: float | None = Field(default=None, ge=-100, le=1000)
    total_return: float | None = Field(default=None, ge=-100, le=1000)
    images: list[str] | None = None
    content: dict | None = None


class PropertyModerateIn(BaseModel):
    reason: str | None = None


class PropertySummaryOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    slug: str | None
    title: str
    subtitle: str | None
    location: str
    country: str | None
    city: str | None
    model: str
    property_type: str
    status: str
    image: str | None
    total_value: float
    minimum_investment: float
    unit_price: float
    target_yield: float | None
    expected_yield: float | None
    capital_appreciation: float | None
    total_return: float | None
    funded_amount: float
    funding_progress: float
    total_units: int
    available_units: int
    investors_count: int
    developer_name: str | None


class PropertyDetailOut(PropertySummaryOut):
    description: str | None
    images: list[str]
    expected_completion: dt.date | None
    spv_name: str | None
    spv_registration: str | None
    legal_structure: str | None
    fees: dict | None
    content: dict
    owner_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    # Phase 15b — real milestones (replaces the content.timeline blob / fake PropertyTimeline)
    # + the construction % computed from them (no stored scalar that can drift).
    milestones: list[MilestoneOut] = Field(default_factory=list)
    construction_progress: int = 0


class OwnerPropertyOut(PropertyDetailOut):
    """Owner-facing view (all statuses, includes funding stats already above)."""


class PropertyListOut(BaseModel):
    items: list[PropertySummaryOut]
    total: int
    limit: int
    offset: int
