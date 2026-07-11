"""Manual payout / deposit-destination models (Task 3) — DDL owned by alembic/0021.

Introduced when the owner chose MANUAL, admin-settled money-out (no Stripe Connect):

  * ``user_bank_accounts``  — an investor's own saved bank account (a withdrawal
    destination). Unlike the tokenized Connect flow, the details are stored so an
    admin can pay out by hand. At most one default per user (partial unique index).
  * ``user_crypto_wallets`` — an investor's own saved crypto payout address.
  * ``platform_bank_accounts`` — the PLATFORM's receiving accounts, admin-managed;
    shown to users for bank-transfer deposits (the accounts they transfer *to*).

These hold bank/crypto identifiers (not card PANs), so no PCI scope. Balances are
never touched here — only wallet_service moves money.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class UserBankAccount(Base):
    __tablename__ = "user_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text)
    account_holder: Mapped[str] = mapped_column(Text, nullable=False)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    iban: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    swift_bic: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class UserCryptoWallet(Base):
    __tablename__ = "user_crypto_wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text)
    network: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. USDT-TRC20, USDT-ERC20, BTC
    address: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class PlatformBankAccount(Base):
    __tablename__ = "platform_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_holder: Mapped[str] = mapped_column(Text, nullable=False)
    iban: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    swift_bic: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    country: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
