"""ORM models mirroring the existing Supabase schema (14 tables).

Column types/constraints follow supabase/migrations/* and audit/01-schema.md.
Postgres enum types are referenced with create_type=False / native_enum so
SQLAlchemy never tries to (re)create them — alembic/0001 owns the DDL.
"""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    AppRole,
    Base,
    InvestmentStatus,
    KycStatus,
    PaymentMethod,
    PropertyStatus,
    TransactionType,
)


# Enum column helpers — reference existing PG types by name, never create them here.
# values_callable makes SQLAlchemy persist the enum VALUE (not the member name), so
# e.g. TransactionType.return_ maps to the DB value "return".
def _pg_enum(enum_cls: type[enum.Enum], name: str) -> ENUM:
    return ENUM(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda obj: [e.value for e in obj],
    )


_app_role = _pg_enum(AppRole, "app_role")
_kyc_status = _pg_enum(KycStatus, "kyc_status")
_property_status = _pg_enum(PropertyStatus, "property_status")
_payment_method = _pg_enum(PaymentMethod, "payment_method")
_investment_status = _pg_enum(InvestmentStatus, "investment_status")
_transaction_type = _pg_enum(TransactionType, "transaction_type")

_NOW = func.now()


class Profile(Base):
    __tablename__ = "profiles"
    # NOTE: references auth.users(id) in the current schema; Phase 1 re-points to app users.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="user_roles_user_id_role_key"),)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[AppRole] = mapped_column(_app_role, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    user = relationship(
        "User",
        primaryjoin="foreign(UserRole.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class KycVerification(Base):
    __tablename__ = "kyc_verifications"
    __table_args__ = (UniqueConstraint("user_id", name="kyc_verifications_user_id_key"),)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[KycStatus] = mapped_column(_kyc_status, nullable=False, server_default="pending")
    id_type: Mapped[str | None] = mapped_column(Text)
    id_number: Mapped[str | None] = mapped_column(Text)
    id_document_url: Mapped[str | None] = mapped_column(Text)
    address_document_url: Mapped[str | None] = mapped_column(Text)
    selfie_url: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Phase 2 — provider integration (Sumsub) + manual-review exception flag.
    provider: Mapped[str | None] = mapped_column(Text)
    provider_applicant_id: Mapped[str | None] = mapped_column(Text)
    manual_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    last_review_answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    # View-only link to the user (the FK lives in the DB, not as an ORM FK column)
    # so the admin panel can display the email/name instead of a bare user_id.
    user = relationship(
        "User",
        primaryjoin="foreign(KycVerification.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PropertyStatus] = mapped_column(
        _property_status, nullable=False, server_default="draft"
    )
    # Phase 3 — catalog: ownership model + presentation/metric columns + rich content.
    slug: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default="ready-income")
    subtitle: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    expected_yield: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 2))
    capital_appreciation: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 2))
    total_return: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 2))
    funding_progress: Mapped[decimal.Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default="0"
    )
    investors_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    total_value: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    minimum_investment: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="500"
    )
    target_yield: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2))
    funded_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    available_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    spv_name: Mapped[str | None] = mapped_column(Text)
    spv_registration: Mapped[str | None] = mapped_column(Text)
    legal_structure: Mapped[str | None] = mapped_column(Text)
    expected_completion: Mapped[datetime.date | None] = mapped_column(Date)
    images: Mapped[list[str] | None] = mapped_column(ARRAY(Text), server_default="{}")
    documents: Mapped[object | None] = mapped_column(JSONB, server_default="[]")
    fees: Mapped[object | None] = mapped_column(
        JSONB, server_default='{"platform_fee": 2.5, "management_fee": 1.0}'
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class Investment(Base):
    __tablename__ = "investments"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[InvestmentStatus] = mapped_column(
        _investment_status, nullable=False, server_default="pending"
    )
    payment_method: Mapped[PaymentMethod | None] = mapped_column(_payment_method)
    payment_reference: Mapped[str | None] = mapped_column(Text)
    pronova_discount_applied: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    # Phase 5 — invest engine. amount = unit subtotal (units * unit_price). The fee
    # snapshots freeze the rates/amounts at purchase so a later platform_settings
    # change never rewrites history.
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    reservation_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    unit_price_snapshot: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    platform_fee_amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    platform_fee_rate: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 3))
    management_fee_rate: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 3))
    total_charged: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    fee_settings_snapshot: Mapped[object | None] = mapped_column(JSONB)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_via: Mapped[str | None] = mapped_column(Text)  # wallet | card | crypto
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    user = relationship(
        "User",
        primaryjoin="foreign(Investment.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="wallets_user_id_key"),
        CheckConstraint("balance >= 0", name="wallets_balance_non_negative"),
        CheckConstraint("pending_balance >= 0", name="wallets_pending_non_negative"),
        CheckConstraint("total_invested >= 0", name="wallets_total_invested_non_negative"),
        CheckConstraint("total_returns >= 0", name="wallets_total_returns_non_negative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    balance: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    pending_balance: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_invested: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_returns: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    user = relationship(
        "User",
        primaryjoin="foreign(Wallet.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[TransactionType] = mapped_column(_transaction_type, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(_payment_method)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    user = relationship(
        "User",
        primaryjoin="foreign(Transaction.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class SecondaryListing(Base):
    __tablename__ = "secondary_listings"
    # Phase 8 — property_id keys the listing to the unit ledger; units_remaining is the
    # live counter partial fills decrement (DB CHECK >= 0). investment_id is legacy
    # (nullable). status: active | sold | cancelled.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE")
    )
    investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="CASCADE")
    )
    units_for_sale: Mapped[int] = mapped_column(Integer, nullable=False)
    units_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_unit: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    sold_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    seller = relationship(
        "User",
        primaryjoin="foreign(SecondaryListing.seller_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, server_default="info")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE")
    )
    investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class FamilyGroup(Base):
    __tablename__ = "family_groups"
    __table_args__ = (UniqueConstraint("owner_id", name="family_groups_owner_id_key"),)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    total_invested: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default="0"
    )
    total_returns: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default="0"
    )
    pronova_bonus_rate: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default="2.5"
    )


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    family_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text, nullable=False)
    allocated_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    allocated_returns: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class FamilyTransfer(Base):
    __tablename__ = "family_transfers"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    family_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False
    )
    from_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    to_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="SET NULL")
    )
    # Phase 10 — transfers are property-scoped (the ledger is); idempotency_key guards
    # the money-move replay; materialized_at set when a pending allocation becomes real.
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE")
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    transfer_fee: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default="0"
    )
    # completed (real ledger move done) | pending (awaiting recipient KYC) | cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="completed")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    materialized_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyReturnAllocation(Base):
    __tablename__ = "family_return_allocations"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    family_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    source_investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="SET NULL")
    )
    # Phase 6 — links a family member's recorded share back to the distribution run.
    distribution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("distributions.id", ondelete="SET NULL")
    )
    reinvested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reinvest_discount: Mapped[decimal.Decimal | None] = mapped_column(Numeric, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


# Phase 1 identity tables (app-owned auth). Imported so Base.metadata registers them
# for Alembic autogenerate / app use. DDL is owned by alembic/0002.
# Phase 2 compliance tables (audit log + webhook idempotency). DDL owned by 0003.
from app.models.broker import BrokerCode, BrokerCommission, BrokerReferral  # noqa: E402
from app.models.compliance import AuditLog, KycWebhookEvent  # noqa: E402
from app.models.developer_updates import (  # noqa: E402
    DeveloperUpdate,
    DeveloperUpdateRecipient,
)
from app.models.distributions import Distribution, DistributionItem  # noqa: E402
from app.models.estate import (  # noqa: E402
    EstateBeneficiary,
    EstateEvent,
    EstateTransfer,
)
from app.models.identity import (  # noqa: E402
    EmailToken,
    OAuthIdentity,
    RefreshToken,
    RoleGrantRequest,
    User,
)
from app.models.investments import OwnershipLedger, PlatformSetting  # noqa: E402
from app.models.liquidity import LpExitRequest, LpPoolTier, LpPosition  # noqa: E402
from app.models.milestones import PropertyMilestone  # noqa: E402
from app.models.notifications import EmailOutbox, NotificationPreference  # noqa: E402
from app.models.payment_methods import PaymentCustomer, SavedPaymentMethod  # noqa: E402
from app.models.payments import Payment, PaymentEvent  # noqa: E402
from app.models.secondary import SecondaryTrade  # noqa: E402
from app.models.withdrawals import ConnectAccount, PayoutEvent, Withdrawal  # noqa: E402

__all__ = [
    "Base",
    "Profile",
    "UserRole",
    "KycVerification",
    "Property",
    "Investment",
    "Wallet",
    "Transaction",
    "SecondaryListing",
    "Notification",
    "Document",
    "FamilyGroup",
    "FamilyMember",
    "FamilyTransfer",
    "FamilyReturnAllocation",
    # identity (Phase 1)
    "User",
    "OAuthIdentity",
    "RefreshToken",
    "EmailToken",
    "RoleGrantRequest",
    # compliance (Phase 2)
    "AuditLog",
    "KycWebhookEvent",
    # payments (Phase 4)
    "Payment",
    "PaymentEvent",
    # investments (Phase 5)
    "PlatformSetting",
    "OwnershipLedger",
    # distributions (Phase 6)
    "Distribution",
    "DistributionItem",
    # withdrawals (Phase 7)
    "Withdrawal",
    "PayoutEvent",
    "ConnectAccount",
    # secondary market (Phase 8)
    "SecondaryTrade",
    # liquidity provider (Phase 9)
    "LpPoolTier",
    "LpExitRequest",
    "LpPosition",
    # broker referrals & commissions (Phase 11)
    "BrokerCode",
    "BrokerReferral",
    "BrokerCommission",
    # notifications + email (Phase 12)
    "NotificationPreference",
    "EmailOutbox",
    # property milestones (Phase 15b)
    "PropertyMilestone",
    # investor communications (Phase 15c)
    "DeveloperUpdate",
    "DeveloperUpdateRecipient",
    # saved payment methods (Group 3)
    "PaymentCustomer",
    "SavedPaymentMethod",
    # estate / inheritance (Group 4)
    "EstateBeneficiary",
    "EstateEvent",
    "EstateTransfer",
]
