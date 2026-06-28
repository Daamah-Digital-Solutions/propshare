"""Broker referral & commission schemas (Phase 11)."""

from __future__ import annotations

from pydantic import BaseModel


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
