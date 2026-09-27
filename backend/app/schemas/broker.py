"""Broker referral & commission schemas (Phase 11)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class ReferralCodeOut(BaseModel):
    code: str
    share_link: str


class BrokerDashboardOut(BaseModel):
    commission_rate: str  # broker_commission_pct, live from platform_settings
    total_referrals: int
    total_commission: str


class ReferralItemOut(BaseModel):
    referral_id: str
    client_masked: str
    created_at: str
    commission_to_date: str


class ReferralListOut(BaseModel):
    items: list[ReferralItemOut]
    total: int


class CommissionItemOut(BaseModel):
    id: str
    revenue_event_type: str
    revenue_amount: str
    commission_rate: str
    commission_amount: str
    created_at: str


class CommissionListOut(BaseModel):
    items: list[CommissionItemOut]
    total: int


# --- Listings & Referrals: the broker's leads (client feedback #2) ---------------------- #
class ClientInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class BrokerLeadOut(BaseModel):
    id: str
    kind: str  # client | property | project
    status: (
        str  # client: invited|joined|cancelled; listing: new|contacted|listed|declined|withdrawn
    )
    name: str
    email: str | None
    phone: str | None
    details: dict
    documents: list[str]
    admin_note: str | None
    property_id: str | None
    created_at: str | None
    updated_at: str | None


class BrokerLeadListOut(BaseModel):
    items: list[BrokerLeadOut]
    total: int
