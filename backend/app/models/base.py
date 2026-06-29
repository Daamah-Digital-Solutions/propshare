"""Declarative base + shared types for the ORM models.

These models mirror the EXISTING Supabase schema (see audit/01-schema.md). The
authoritative DDL lives in alembic/versions/0001_initial.py (raw SQL, translated
verbatim from supabase/migrations/*). The ORM models are for application use and
must be kept in sync with that migration.
"""

from __future__ import annotations

import enum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# --- Postgres enum types (already defined in the DB; do not let SQLAlchemy create them) ---
class AppRole(enum.StrEnum):
    investor = "investor"
    owner = "owner"
    broker = "broker"
    liquidity_provider = "liquidity_provider"
    admin = "admin"


class KycStatus(enum.StrEnum):
    pending = "pending"
    submitted = "submitted"
    verified = "verified"
    rejected = "rejected"


class PropertyStatus(enum.StrEnum):
    draft = "draft"
    under_review = "under_review"
    active = "active"
    funded = "funded"
    closed = "closed"


class PaymentMethod(enum.StrEnum):
    visa = "visa"
    mastercard = "mastercard"
    apple_pay = "apple_pay"
    google_pay = "google_pay"
    crypto = "crypto"
    pronova_token = "pronova_token"
    nova_sukuk = "nova_sukuk"


class InvestmentStatus(enum.StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    expired = "expired"  # Phase 5 — a direct-pay reservation that timed out unpaid


class MilestoneStatus(enum.StrEnum):
    planned = "planned"  # Phase 15b — project milestone not yet started
    in_progress = "in_progress"
    completed = "completed"


class TransactionType(enum.StrEnum):
    deposit = "deposit"  # Phase 4 — added to the PG enum in migration 0005
    investment = "investment"
    withdrawal = "withdrawal"
    return_ = "return"
    fee = "fee"
    referral_commission = "referral_commission"
    secondary_sale = "secondary_sale"  # Phase 8 — seller's proceeds from a unit resale
    lp_deposit = "lp_deposit"  # Phase 9 — PASSIVE pool principal in/out
    lp_yield = "lp_yield"  # Phase 9 — PASSIVE fixed interest
    family_allocation = "family_allocation"  # Phase 10 — owner→member returns transfer
    gift = "gift"  # Group 5 — inter-vivos wallet-gift escrow/credit/refund
