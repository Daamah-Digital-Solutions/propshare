"""Server-rendered admin panel (SQLAdmin), mounted at /admin.

Security: gated by ``AdminAuth`` — login requires valid credentials AND the
``admin`` role (verified against the DB). The panel is never public; an
unauthenticated visitor is redirected to /admin/login. This gives the owner a
real UI to approve properties and inspect data instead of calling /docs by hand.

Mutation safety: money tables (investments, wallets, transactions) are
READ-ONLY here — they must only ever change through the audited service layer
(Phase 4+), never by hand from a CRUD form.
"""

from __future__ import annotations

import html as _html
import uuid

from sqladmin import Admin, BaseView, ModelView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.core.config import get_settings
from app.core.db import get_engine, session_scope
from app.core.errors import AppError
from app.models import (
    BrokerCode,
    BrokerCommission,
    BrokerReferral,
    ConnectAccount,
    DeveloperUpdate,
    DeveloperUpdateRecipient,
    Distribution,
    DistributionItem,
    Document,
    EmailOutbox,
    EstateBeneficiary,
    EstateEvent,
    EstateTransfer,
    FamilyGroup,
    FamilyMember,
    FamilyTransfer,
    InstallmentPayment,
    InstallmentPlan,
    Investment,
    KycVerification,
    LpExitRequest,
    LpPoolTier,
    LpPosition,
    NotificationPreference,
    OwnershipLedger,
    Payment,
    PaymentCustomer,
    PlatformBankAccount,
    PlatformSetting,
    Property,
    PropertyMilestone,
    SavedPaymentMethod,
    ScheduledGift,
    SecondaryListing,
    SecondaryTrade,
    Transaction,
    UserBankAccount,
    UserCryptoWallet,
    UserRole,
    Wallet,
    Withdrawal,
)
from app.models.identity import User
from app.services import (
    auth_service,
    distribution_service,
    document_service,
    kyc_service,
    manual_deposit_service,
    property_service,
    withdrawal_service,
)


class AdminAuth(AuthenticationBackend):
    """Form login that only admits users holding the ``admin`` role."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", "")).strip().lower()
        password = str(form.get("password", ""))
        async with session_scope() as session:
            try:
                user = await auth_service.authenticate(session, email=email, password=password)
            except Exception:
                return False
            if not await auth_service.has_role(session, user.id, "admin"):
                return False
            request.session.update({"admin_id": str(user.id), "admin_email": user.email})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_id" in request.session


def _back(request: Request) -> RedirectResponse:
    return RedirectResponse(request.headers.get("referer") or "/admin", status_code=302)


class PropertyAdmin(ModelView, model=Property):
    name = "Property"
    name_plural = "Properties"
    icon = "fa-solid fa-building"
    column_list = [
        Property.id,
        Property.title,
        Property.model,
        Property.status,
        Property.total_value,
        Property.funding_progress,
        Property.owner_id,
        Property.created_at,
    ]
    column_searchable_list = [Property.title, Property.slug]
    column_sortable_list = [Property.created_at, Property.status, Property.total_value]
    column_default_sort = [(Property.created_at, True)]
    can_create = False
    can_edit = True
    can_delete = False

    async def _moderate(self, request: Request, what: str) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                await property_service.admin_moderate(
                    session,
                    actor_id=actor_uuid,
                    prop_id=uuid.UUID(pk),
                    action=what,
                )
        return _back(request)

    @action(
        name="approve",
        label="Approve (→ active)",
        confirmation_message="Approve and publish the selected property?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def approve(self, request: Request) -> RedirectResponse:
        return await self._moderate(request, "approve")

    @action(
        name="reject",
        label="Reject (→ draft)",
        confirmation_message="Send the selected property back to draft?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reject(self, request: Request) -> RedirectResponse:
        return await self._moderate(request, "reject")

    @action(
        name="close",
        label="Close",
        confirmation_message="Close the selected property?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def close(self, request: Request) -> RedirectResponse:
        return await self._moderate(request, "close")


class PropertyMilestoneAdmin(ModelView, model=PropertyMilestone):
    name = "Property Milestone"
    icon = "fa-solid fa-flag-checkered"
    # Content table (Phase 15b) — editable here for hands-on correction; the same
    # rows the developer manages from the dashboard and investors read on the
    # property page. Not money, so create/edit/delete are allowed.
    column_list = [
        PropertyMilestone.property_id,
        PropertyMilestone.sort_index,
        PropertyMilestone.title,
        PropertyMilestone.status,
        PropertyMilestone.progress_pct,
        PropertyMilestone.value_index,
        PropertyMilestone.target_date,
        PropertyMilestone.completed_at,
    ]
    column_sortable_list = [PropertyMilestone.sort_index, PropertyMilestone.target_date]
    column_default_sort = [
        (PropertyMilestone.property_id, False),
        (PropertyMilestone.sort_index, False),
    ]
    form_columns = [
        PropertyMilestone.property_id,
        PropertyMilestone.title,
        PropertyMilestone.description,
        PropertyMilestone.status,
        PropertyMilestone.progress_pct,
        PropertyMilestone.value_index,
        PropertyMilestone.target_date,
        PropertyMilestone.completed_at,
        PropertyMilestone.sort_index,
    ]
    can_create = True
    can_edit = True
    can_delete = True


class UserAdmin(ModelView, model=User):
    name = "User"
    icon = "fa-solid fa-user"
    column_list = [
        User.id,
        User.email,
        User.full_name,
        User.active_role,
        User.email_verified,
        User.created_at,
    ]
    column_searchable_list = [User.email]
    column_sortable_list = [User.email, User.created_at]
    can_create = False
    can_edit = True  # admin may flip active_role / email_verified
    can_delete = False

    async def _kyc_decide(self, request: Request, approve: bool) -> RedirectResponse:
        # The User pk IS the user_id, so we can verify/reject KYC straight from here.
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                try:
                    await kyc_service.admin_decide(
                        session,
                        user_id=uuid.UUID(pk),
                        approve=approve,
                        actor_id=actor_uuid,
                        reason=None,
                    )
                except AppError:
                    continue  # e.g. user without a KYC row — skip, don't fail the batch
        return _back(request)

    @action(
        name="verify_kyc",
        label="Verify KYC (→ verified)",
        confirmation_message="Mark the selected user(s) as KYC-verified?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def verify_kyc(self, request: Request) -> RedirectResponse:
        return await self._kyc_decide(request, True)

    @action(
        name="reject_kyc",
        label="Reject KYC (→ rejected)",
        confirmation_message="Reject the selected user(s)' KYC?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reject_kyc(self, request: Request) -> RedirectResponse:
        return await self._kyc_decide(request, False)


class UserRoleAdmin(ModelView, model=UserRole):
    name = "User Role"
    icon = "fa-solid fa-user-shield"
    column_list = [UserRole.user, UserRole.role, UserRole.created_at]
    column_labels = {UserRole.user: "User"}
    column_searchable_list = [User.email]
    can_create = True  # grant a role
    can_edit = False
    can_delete = True  # revoke a role


class KycAdmin(ModelView, model=KycVerification):
    name = "KYC Verification"
    icon = "fa-solid fa-id-card"
    # Show the user (email) instead of a bare user_id so rows are identifiable.
    column_list = [
        KycVerification.user,
        KycVerification.status,
        KycVerification.manual_review_required,
        KycVerification.provider,
        KycVerification.submitted_at,
        KycVerification.verified_at,
    ]
    column_labels = {KycVerification.user: "User"}
    column_searchable_list = [User.email]
    column_sortable_list = [KycVerification.status, KycVerification.submitted_at]
    can_create = False
    can_edit = True  # exception override of provider-flagged cases
    can_delete = False

    async def _decide(self, request: Request, approve: bool) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                kyc = await session.get(KycVerification, uuid.UUID(pk))
                if kyc is not None:
                    await kyc_service.admin_decide(
                        session,
                        user_id=kyc.user_id,
                        approve=approve,
                        actor_id=actor_uuid,
                        reason=None,
                    )
        return _back(request)

    @action(
        name="verify",
        label="Verify (→ verified)",
        confirmation_message="Mark the selected user(s) as KYC-verified?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def verify(self, request: Request) -> RedirectResponse:
        return await self._decide(request, True)

    @action(
        name="reject",
        label="Reject (→ rejected)",
        confirmation_message="Reject the selected KYC verification(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reject(self, request: Request) -> RedirectResponse:
        return await self._decide(request, False)


class InvestmentAdmin(ModelView, model=Investment):
    name = "Investment"
    icon = "fa-solid fa-coins"
    column_list = [
        Investment.user,
        Investment.property_id,
        Investment.units,
        Investment.amount,
        Investment.status,
        Investment.created_at,
    ]
    column_labels = {Investment.user: "User"}
    column_searchable_list = [User.email]
    can_create = False
    can_edit = False
    can_delete = False  # money — read-only; changes go through the audited service layer


class WalletAdmin(ModelView, model=Wallet):
    name = "Wallet"
    icon = "fa-solid fa-wallet"
    column_list = [
        Wallet.user,
        Wallet.balance,
        Wallet.pending_balance,
        Wallet.total_invested,
        Wallet.total_returns,
    ]
    column_labels = {Wallet.user: "User"}
    column_searchable_list = [User.email]
    can_create = False
    can_edit = False
    can_delete = False  # money — read-only


class TransactionAdmin(ModelView, model=Transaction):
    name = "Transaction"
    icon = "fa-solid fa-receipt"
    column_list = [
        Transaction.user,
        Transaction.type,
        Transaction.amount,
        Transaction.status,
        Transaction.created_at,
    ]
    column_labels = {Transaction.user: "User"}
    column_searchable_list = [User.email]
    can_create = False
    can_edit = False
    can_delete = False  # ledger — append-only, read-only here


class PlatformSettingAdmin(ModelView, model=PlatformSetting):
    name = "Platform Setting"
    icon = "fa-solid fa-sliders"
    # The owner edits fee rates here (e.g. platform_fee_pct, management_fee_pct) —
    # the investment engine READS these, so a change takes effect with no deploy.
    column_list = [
        PlatformSetting.key,
        PlatformSetting.value,
        PlatformSetting.description,
        PlatformSetting.updated_at,
    ]
    column_searchable_list = [PlatformSetting.key]
    can_create = True
    can_edit = True  # change a rate
    can_delete = False

    async def on_model_change(self, data, model, is_created, request) -> None:
        # Phase 13: reject malformed/out-of-range values (no silent fallback). The
        # lp_passive_enabled flag is hard-locked to false here too.
        from app.services import settings_service

        key = (data.get("key") or getattr(model, "key", "") or "").strip()
        value = data.get("value")
        if value is None:
            value = getattr(model, "value", "")
        try:
            settings_service.validate_setting(key, str(value))
        except AppError as exc:
            raise ValueError(exc.message) from exc


class OwnershipLedgerAdmin(ModelView, model=OwnershipLedger):
    name = "Ownership Ledger"
    icon = "fa-solid fa-list-check"
    column_list = [
        OwnershipLedger.user_id,
        OwnershipLedger.property_id,
        OwnershipLedger.units,
        OwnershipLedger.unit_price,
        OwnershipLedger.reason,
        OwnershipLedger.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False  # append-only — units are issued only by the audited service layer


class DistributionAdmin(ModelView, model=Distribution):
    name = "Distribution"
    name_plural = "Distributions"
    icon = "fa-solid fa-money-bill-trend-up"
    # Filling this create form TRIGGERS a real pro-rata distribution run (atomic,
    # idempotent on property+period) — it is not a plain insert.
    column_list = [
        Distribution.property_id,
        Distribution.kind,
        Distribution.period_key,
        Distribution.period_start,
        Distribution.period_end,
        Distribution.gross_pool,
        Distribution.total_net,
        Distribution.total_management_fee,
        Distribution.status,
        Distribution.created_at,
    ]
    column_default_sort = [(Distribution.created_at, True)]
    form_columns = [
        Distribution.property_id,
        Distribution.kind,
        Distribution.period_key,
        Distribution.period_start,
        Distribution.period_end,
        Distribution.gross_pool,
    ]
    can_create = True
    can_edit = False
    can_delete = False

    async def insert_model(self, request: Request, data: dict):
        import decimal

        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            try:
                result = await distribution_service.run_distribution(
                    session,
                    property_id=uuid.UUID(str(data["property_id"])),
                    kind=str(data.get("kind") or "rental"),
                    period_key=str(data["period_key"]),
                    period_start=data["period_start"],
                    period_end=data["period_end"],
                    gross_pool=decimal.Decimal(str(data["gross_pool"])),
                    created_by=actor_uuid,
                    idempotency_key=None,
                )
            except AppError as exc:
                # Surface a clean message in the admin form instead of a 500.
                raise ValueError(exc.message) from exc
            # expire_on_commit=False -> the fetched row stays usable after commit.
            return await session.get(Distribution, result["distribution_id"])


class DistributionItemAdmin(ModelView, model=DistributionItem):
    name = "Distribution Item"
    icon = "fa-solid fa-list-ol"
    column_list = [
        DistributionItem.distribution_id,
        DistributionItem.user_id,
        DistributionItem.units,
        DistributionItem.gross_amount,
        DistributionItem.management_fee,
        DistributionItem.net_amount,
        DistributionItem.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False  # audit of who got paid what — read-only


class WithdrawalAdmin(ModelView, model=Withdrawal):
    name = "Withdrawal"
    icon = "fa-solid fa-money-bill-transfer"
    column_list = [
        Withdrawal.user,
        Withdrawal.amount,
        Withdrawal.method,
        Withdrawal.status,
        Withdrawal.provider,
        Withdrawal.destination,
        Withdrawal.failure_reason,
        Withdrawal.created_at,
        Withdrawal.completed_at,
    ]
    column_labels = {Withdrawal.user: "User", Withdrawal.destination: "Pay to"}
    column_searchable_list = [User.email]
    column_sortable_list = [Withdrawal.created_at, Withdrawal.status, Withdrawal.amount]
    column_default_sort = [(Withdrawal.created_at, True)]
    can_create = False
    can_edit = False  # state changes go through the audited service layer only
    can_delete = False

    async def _decide(self, request: Request, approve: bool) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                try:
                    await withdrawal_service.admin_review(
                        session,
                        withdrawal_id=uuid.UUID(pk),
                        approve=approve,
                        actor_id=actor_uuid,
                        reason=None if approve else "Rejected by reviewer",
                    )
                except AppError:
                    continue  # not in pending_review — skip, don't fail the batch
        return _back(request)

    @action(
        name="approve_withdrawal",
        label="Approve (automated payout path)",
        confirmation_message="Approve the selected withdrawal(s) for the automated payout path?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def approve_withdrawal(self, request: Request) -> RedirectResponse:
        return await self._decide(request, True)

    @action(
        name="mark_paid_withdrawal",
        label="Mark paid (manual payout)",
        confirmation_message=(
            "Confirm you have sent this payout by hand? This clears the hold and completes "
            "the withdrawal (the funds have already left the wallet at request time)."
        ),
        add_in_detail=True,
        add_in_list=True,
    )
    async def mark_paid_withdrawal(self, request: Request) -> RedirectResponse:
        """Manual settlement: the admin sent the money by hand (bank transfer / on-chain send)."""
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                try:
                    await withdrawal_service.admin_mark_paid(
                        session, withdrawal_id=uuid.UUID(pk), actor_id=actor_uuid
                    )
                except AppError:
                    continue  # not in a payable state — skip, don't fail the batch
        return _back(request)

    @action(
        name="reject_withdrawal",
        label="Reject (→ refund wallet)",
        confirmation_message="Reject the selected withdrawal(s) and return funds to the wallet?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reject_withdrawal(self, request: Request) -> RedirectResponse:
        return await self._decide(request, False)


class PlatformBankAccountAdmin(ModelView, model=PlatformBankAccount):
    name = "Platform Bank Account"
    icon = "fa-solid fa-building-columns"
    # The RECEIVING accounts users transfer to for bank-transfer deposits. The owner
    # adds / edits / removes these freely; the ACTIVE ones are shown to depositing users.
    column_list = [
        PlatformBankAccount.bank_name,
        PlatformBankAccount.account_holder,
        PlatformBankAccount.iban,
        PlatformBankAccount.account_number,
        PlatformBankAccount.currency,
        PlatformBankAccount.is_active,
        PlatformBankAccount.sort_order,
    ]
    column_searchable_list = [PlatformBankAccount.bank_name, PlatformBankAccount.account_holder]
    column_default_sort = [(PlatformBankAccount.sort_order, False)]
    form_columns = [
        PlatformBankAccount.bank_name,
        PlatformBankAccount.account_holder,
        PlatformBankAccount.iban,
        PlatformBankAccount.account_number,
        PlatformBankAccount.swift_bic,
        PlatformBankAccount.currency,
        PlatformBankAccount.country,
        PlatformBankAccount.instructions,
        PlatformBankAccount.is_active,
        PlatformBankAccount.sort_order,
    ]
    can_create = True
    can_edit = True
    can_delete = True


class BankDepositClaimAdmin(ModelView, model=Payment):
    name = "Bank Deposit Claim"
    icon = "fa-solid fa-money-check-dollar"
    # Manual bank-transfer deposit CLAIMS (provider='manual_bank'). Confirm → the wallet is
    # credited via the audited service layer (never by hand). Card/crypto deposits are
    # auto-credited by webhook and are intentionally not shown here.
    column_list = [
        Payment.user_id,
        Payment.amount,
        Payment.status,
        Payment.raw_payload,
        Payment.created_at,
    ]
    column_labels = {Payment.raw_payload: "Reference / account", Payment.user_id: "User"}
    column_sortable_list = [Payment.created_at, Payment.status, Payment.amount]
    column_default_sort = [(Payment.created_at, True)]
    can_create = False
    can_edit = False  # money — credited only through the audited service layer
    can_delete = False

    def list_query(self, request: Request):
        return select(Payment).where(Payment.provider == "manual_bank")

    @action(
        name="confirm_deposit",
        label="Confirm (→ credit wallet)",
        confirmation_message=(
            "Confirm the bank transfer arrived? This credits the user's wallet. Only a pending "
            "claim is affected."
        ),
        add_in_detail=True,
        add_in_list=True,
    )
    async def confirm_deposit(self, request: Request) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                try:
                    await manual_deposit_service.admin_confirm(
                        session, payment_id=uuid.UUID(pk), actor_id=actor_uuid
                    )
                except AppError:
                    continue  # not a pending bank claim — skip, don't fail the batch
        return _back(request)

    @action(
        name="reject_deposit",
        label="Reject claim",
        confirmation_message="Reject the selected bank-transfer claim(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reject_deposit(self, request: Request) -> RedirectResponse:
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        actor = request.session.get("admin_id")
        actor_uuid = uuid.UUID(actor) if actor else None
        async with session_scope() as session:
            for pk in pks:
                try:
                    await manual_deposit_service.admin_reject(
                        session,
                        payment_id=uuid.UUID(pk),
                        actor_id=actor_uuid,
                        reason="Rejected by admin",
                    )
                except AppError:
                    continue
        return _back(request)


class UserBankAccountAdmin(ModelView, model=UserBankAccount):
    name = "User Bank Account"
    icon = "fa-solid fa-piggy-bank"
    column_list = [
        UserBankAccount.user_id,
        UserBankAccount.account_holder,
        UserBankAccount.bank_name,
        UserBankAccount.iban,
        UserBankAccount.is_default,
        UserBankAccount.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class UserCryptoWalletAdmin(ModelView, model=UserCryptoWallet):
    name = "User Crypto Wallet"
    icon = "fa-solid fa-wallet"
    column_list = [
        UserCryptoWallet.user_id,
        UserCryptoWallet.network,
        UserCryptoWallet.address,
        UserCryptoWallet.is_default,
        UserCryptoWallet.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class SecondaryListingAdmin(ModelView, model=SecondaryListing):
    name = "Secondary Listing"
    icon = "fa-solid fa-tags"
    column_list = [
        SecondaryListing.seller,
        SecondaryListing.property_id,
        SecondaryListing.units_for_sale,
        SecondaryListing.units_remaining,
        SecondaryListing.price_per_unit,
        SecondaryListing.status,
        SecondaryListing.created_at,
    ]
    column_labels = {SecondaryListing.seller: "Seller"}
    column_searchable_list = [User.email]
    column_sortable_list = [SecondaryListing.created_at, SecondaryListing.status]
    column_default_sort = [(SecondaryListing.created_at, True)]
    can_create = False
    can_edit = False  # units move only through the audited service layer
    can_delete = False


class SecondaryTradeAdmin(ModelView, model=SecondaryTrade):
    name = "Secondary Trade"
    icon = "fa-solid fa-right-left"
    column_list = [
        SecondaryTrade.buyer,
        SecondaryTrade.seller_id,
        SecondaryTrade.property_id,
        SecondaryTrade.units,
        SecondaryTrade.gross,
        SecondaryTrade.resale_fee,
        SecondaryTrade.total_charged,
        SecondaryTrade.created_at,
    ]
    column_labels = {SecondaryTrade.buyer: "Buyer"}
    column_sortable_list = [SecondaryTrade.created_at]
    column_default_sort = [(SecondaryTrade.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False  # executed trades — append-only audit


class LpPoolTierAdmin(ModelView, model=LpPoolTier):
    name = "LP Pool Tier"
    icon = "fa-solid fa-layer-group"
    # PASSIVE config — admin-editable term/APY/minimum (the real, single source).
    column_list = [
        LpPoolTier.period_months,
        LpPoolTier.apy_pct,
        LpPoolTier.min_amount,
        LpPoolTier.active,
    ]
    can_create = True
    can_edit = True
    can_delete = False


class LpExitRequestAdmin(ModelView, model=LpExitRequest):
    name = "LP Exit Request"
    icon = "fa-solid fa-right-from-bracket"
    column_list = [
        LpExitRequest.seller,
        LpExitRequest.property_id,
        LpExitRequest.units,
        LpExitRequest.units_remaining,
        LpExitRequest.lp_price,
        LpExitRequest.seller_net,
        LpExitRequest.status,
        LpExitRequest.created_at,
    ]
    column_labels = {LpExitRequest.seller: "Seller"}
    column_searchable_list = [User.email]
    column_sortable_list = [LpExitRequest.created_at, LpExitRequest.status]
    column_default_sort = [(LpExitRequest.created_at, True)]
    can_create = False
    can_edit = False  # pricing/units move only through the audited service layer
    can_delete = False


class LpPositionAdmin(ModelView, model=LpPosition):
    name = "LP Position"
    icon = "fa-solid fa-droplet"
    # Append-only audit of committed LP capital; holdings live in ownership_ledger.
    column_list = [
        LpPosition.lp_user,
        LpPosition.classification,
        LpPosition.principal_amount,
        LpPosition.property_id,
        LpPosition.units,
        LpPosition.status,
        LpPosition.created_at,
    ]
    column_labels = {LpPosition.lp_user: "Liquidity Provider"}
    column_sortable_list = [LpPosition.created_at, LpPosition.classification]
    column_default_sort = [(LpPosition.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class ConnectAccountAdmin(ModelView, model=ConnectAccount):
    name = "Connect Account"
    icon = "fa-solid fa-building-columns"
    column_list = [
        ConnectAccount.user_id,
        ConnectAccount.stripe_account_id,
        ConnectAccount.payouts_enabled,
        ConnectAccount.details_submitted,
        ConnectAccount.status,
        ConnectAccount.updated_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class FamilyGroupAdmin(ModelView, model=FamilyGroup):
    name = "Family Group"
    icon = "fa-solid fa-people-roof"
    column_list = [
        FamilyGroup.owner_id,
        FamilyGroup.name,
        FamilyGroup.total_returns,
        FamilyGroup.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class FamilyMemberAdmin(ModelView, model=FamilyMember):
    name = "Family Member"
    icon = "fa-solid fa-user-group"
    column_list = [
        FamilyMember.family_group_id,
        FamilyMember.name,
        FamilyMember.relationship,
        FamilyMember.user_id,
        FamilyMember.is_verified,
        FamilyMember.allocated_units,
        FamilyMember.allocated_returns,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class FamilyTransferAdmin(ModelView, model=FamilyTransfer):
    name = "Family Transfer"
    icon = "fa-solid fa-arrow-right-arrow-left"
    column_list = [
        FamilyTransfer.from_member_id,
        FamilyTransfer.to_member_id,
        FamilyTransfer.property_id,
        FamilyTransfer.units,
        FamilyTransfer.status,
        FamilyTransfer.created_at,
        FamilyTransfer.materialized_at,
    ]
    column_default_sort = [(FamilyTransfer.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class BrokerCodeAdmin(ModelView, model=BrokerCode):
    name = "Broker Code"
    icon = "fa-solid fa-ticket"
    column_list = [BrokerCode.broker_id, BrokerCode.code, BrokerCode.created_at]
    can_create = False
    can_edit = False
    can_delete = False


class BrokerReferralAdmin(ModelView, model=BrokerReferral):
    name = "Broker Referral"
    icon = "fa-solid fa-user-plus"
    column_list = [
        BrokerReferral.broker_id,
        BrokerReferral.client_id,
        BrokerReferral.code_id,
        BrokerReferral.created_at,
    ]
    column_default_sort = [(BrokerReferral.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class BrokerCommissionAdmin(ModelView, model=BrokerCommission):
    name = "Broker Commission"
    icon = "fa-solid fa-hand-holding-dollar"
    column_list = [
        BrokerCommission.broker_id,
        BrokerCommission.client_id,
        BrokerCommission.revenue_event_type,
        BrokerCommission.revenue_amount,
        BrokerCommission.commission_rate,
        BrokerCommission.commission_amount,
        BrokerCommission.created_at,
    ]
    column_default_sort = [(BrokerCommission.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class NotificationPreferenceAdmin(ModelView, model=NotificationPreference):
    name = "Notification Preference"
    icon = "fa-solid fa-sliders"
    column_list = [
        NotificationPreference.user_id,
        NotificationPreference.email_investment_updates,
        NotificationPreference.email_returns,
        NotificationPreference.email_security_alerts,
        NotificationPreference.email_new_properties,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class SavedPaymentMethodAdmin(ModelView, model=SavedPaymentMethod):
    name = "Saved Payment Method"
    icon = "fa-solid fa-credit-card"
    # PCI-safe: tokens + safe display metadata only (never card data). Read-only here —
    # add/remove flows through the audited service so Stripe stays in sync.
    column_list = [
        SavedPaymentMethod.user_id,
        SavedPaymentMethod.type,
        SavedPaymentMethod.brand,
        SavedPaymentMethod.last4,
        SavedPaymentMethod.exp_month,
        SavedPaymentMethod.exp_year,
        SavedPaymentMethod.is_default,
        SavedPaymentMethod.created_at,
    ]
    column_default_sort = [(SavedPaymentMethod.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class PaymentCustomerAdmin(ModelView, model=PaymentCustomer):
    name = "Payment Customer"
    icon = "fa-solid fa-id-card-clip"
    column_list = [
        PaymentCustomer.user_id,
        PaymentCustomer.provider,
        PaymentCustomer.customer_id,
        PaymentCustomer.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class EstateBeneficiaryAdmin(ModelView, model=EstateBeneficiary):
    name = "Estate Beneficiary"
    icon = "fa-solid fa-people-arrows"
    column_list = [
        EstateBeneficiary.owner_id,
        EstateBeneficiary.full_name,
        EstateBeneficiary.relationship,
        EstateBeneficiary.allocation_pct,
        EstateBeneficiary.status,
        EstateBeneficiary.beneficiary_user_id,
        EstateBeneficiary.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class EstateEventAdmin(ModelView, model=EstateEvent):
    name = "Estate Event (Death)"
    icon = "fa-solid fa-file-shield"
    # Audit of admin-verified deaths + execution status (manual-admin only).
    column_list = [
        EstateEvent.subject_user_id,
        EstateEvent.status,
        EstateEvent.death_certificate_document_id,
        EstateEvent.verified_by,
        EstateEvent.verified_at,
        EstateEvent.executed_at,
    ]
    column_default_sort = [(EstateEvent.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class EstateTransferAdmin(ModelView, model=EstateTransfer):
    name = "Estate Transfer"
    icon = "fa-solid fa-right-left"
    column_list = [
        EstateTransfer.estate_event_id,
        EstateTransfer.beneficiary_id,
        EstateTransfer.property_id,
        EstateTransfer.units,
        EstateTransfer.status,
        EstateTransfer.materialized_at,
        EstateTransfer.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class ScheduledGiftAdmin(ModelView, model=ScheduledGift):
    name = "Scheduled Gift"
    icon = "fa-solid fa-gift"
    # Inter-vivos gifts (Group 5) — append-only-ish audit of scheduled/executed transfers.
    column_list = [
        ScheduledGift.giver_id,
        ScheduledGift.recipient_name,
        ScheduledGift.recipient_user_id,
        ScheduledGift.asset_type,
        ScheduledGift.units,
        ScheduledGift.amount,
        ScheduledGift.scheduled_for,
        ScheduledGift.recurring,
        ScheduledGift.status,
        ScheduledGift.failure_reason,
    ]
    column_default_sort = [(ScheduledGift.scheduled_for, True)]
    can_create = False
    can_edit = False
    can_delete = False


class InstallmentPlanAdmin(ModelView, model=InstallmentPlan):
    name = "Installment Plan"
    icon = "fa-solid fa-calendar-days"
    column_list = [
        InstallmentPlan.investor_id,
        InstallmentPlan.property_id,
        InstallmentPlan.units_total,
        InstallmentPlan.vested_units,
        InstallmentPlan.down_payment_pct,
        InstallmentPlan.duration_months,
        InstallmentPlan.fee_rate,
        InstallmentPlan.status,
        InstallmentPlan.created_at,
        InstallmentPlan.completed_at,
    ]
    column_default_sort = [(InstallmentPlan.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class InstallmentPaymentAdmin(ModelView, model=InstallmentPayment):
    name = "Installment Payment"
    icon = "fa-solid fa-money-check-dollar"
    column_list = [
        InstallmentPayment.plan_id,
        InstallmentPayment.seq,
        InstallmentPayment.kind,
        InstallmentPayment.due_date,
        InstallmentPayment.total_amount,
        InstallmentPayment.vest_units,
        InstallmentPayment.status,
        InstallmentPayment.paid_at,
    ]
    column_default_sort = [(InstallmentPayment.due_date, False)]
    can_create = False
    can_edit = False
    can_delete = False


class DocumentAdmin(ModelView, model=Document):
    name = "Document"
    icon = "fa-solid fa-file-lines"
    # Property/user documents (storage seam). Read-only here — files live in the
    # storage provider; uploads go through the audited service/route.
    column_list = [
        Document.property_id,
        Document.user_id,
        Document.title,
        Document.type,
        Document.file_url,
        Document.created_at,
    ]
    column_default_sort = [(Document.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = True  # allow removing a stale/incorrect document row


class DeveloperUpdateAdmin(ModelView, model=DeveloperUpdate):
    name = "Investor Update"
    icon = "fa-solid fa-bullhorn"
    # Sent investor communications (Phase 15c) — append-only audit of what went out.
    column_list = [
        DeveloperUpdate.property_id,
        DeveloperUpdate.subject,
        DeveloperUpdate.recipient_count,
        DeveloperUpdate.created_by,
        DeveloperUpdate.created_at,
    ]
    column_default_sort = [(DeveloperUpdate.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


class DeveloperUpdateRecipientAdmin(ModelView, model=DeveloperUpdateRecipient):
    name = "Investor Update Recipient"
    icon = "fa-solid fa-users-line"
    column_list = [
        DeveloperUpdateRecipient.update_id,
        DeveloperUpdateRecipient.user_id,
        DeveloperUpdateRecipient.notification_id,
        DeveloperUpdateRecipient.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class EmailOutboxAdmin(ModelView, model=EmailOutbox):
    name = "Email Outbox"
    icon = "fa-solid fa-envelope"
    column_list = [
        EmailOutbox.to_email,
        EmailOutbox.category,
        EmailOutbox.subject,
        EmailOutbox.status,
        EmailOutbox.attempts,
        EmailOutbox.created_at,
        EmailOutbox.sent_at,
    ]
    column_default_sort = [(EmailOutbox.created_at, True)]
    can_create = False
    can_edit = False
    can_delete = False


_DOC_CATEGORIES = [
    ("spv", "SPV Documents"),
    ("valuation", "Valuation Reports"),
    ("financial", "Financial & Investment Studies"),
    ("agreement", "Agreements"),
    ("legal", "Legal Documents"),
    ("insurance", "Insurance Certificates"),
    ("audit", "Smart Contract Audit Reports"),
    ("other", "Other Documents"),
]

_UPLOAD_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Upload Document - CapiMax Admin</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
   background:#f4f5f3;margin:0;padding:32px;color:#23302a}}
 .card{{max-width:560px;margin:0 auto;background:#fff;border:1px solid #e8e6e1;
   border-radius:14px;padding:28px 32px;box-shadow:0 6px 22px rgba(20,40,30,.06)}}
 h1{{font-size:20px;margin:0 0 4px}}
 p.sub{{color:#6b726c;margin:0 0 20px;font-size:14px}}
 label{{display:block;font-weight:600;font-size:13px;margin:14px 0 5px}}
 input,select{{width:100%;box-sizing:border-box;padding:10px 12px;
   border:1px solid #d9dcd8;border-radius:8px;font-size:14px}}
 button{{margin-top:22px;width:100%;padding:12px;border:0;border-radius:9px;
   background:#198653;color:#fff;font-weight:600;font-size:15px;cursor:pointer}}
 a.back{{display:inline-block;margin-top:16px;color:#198653;
   font-size:13px;text-decoration:none}}
 .ok{{background:#e7f5ec;border:1px solid #b7e0c6;color:#0f6e4e;padding:10px 12px;
   border-radius:8px;margin-bottom:16px;font-size:14px}}
 .err{{background:#fdeaea;border:1px solid #f2c2c2;color:#b00;padding:10px 12px;
   border-radius:8px;margin-bottom:16px;font-size:14px}}
</style></head><body>
<div class="card">
 <h1>Upload Property Document</h1>
 <p class="sub">Add SPV papers, valuations, agreements, insurance, audit reports, etc. for
   any property. It appears in the investor Documents Center and on the public property page.</p>
 {message}
 <form method="post" enctype="multipart/form-data">
  <label>Property</label>
  <select name="property_id" required>{options}</select>
  <label>Document title</label>
  <input name="title" placeholder="e.g. SPV Shareholders Agreement" required>
  <label>Category</label>
  <select name="doc_type">{cats}</select>
  <label>File</label>
  <input type="file" name="file" required>
  <button type="submit">Upload document</button>
 </form>
 <a class="back" href="/admin">&larr; Back to admin</a>
</div></body></html>"""


class DocumentUploadView(BaseView):
    """Upload a property document (SPV, valuation, agreement, insurance, audit, …) for ANY
    property, straight from the admin panel — no owner account needed. Admin-gated like the
    rest of /admin; the file lands in the storage seam via the audited service layer."""

    name = "Upload Document"
    icon = "fa-solid fa-file-arrow-up"

    @expose("/upload-document", methods=["GET", "POST"])
    async def upload(self, request: Request):
        if not request.session.get("admin_id"):
            return RedirectResponse("/admin/login", status_code=302)
        message = ""
        if request.method == "POST":
            form = await request.form()
            prop_id = str(form.get("property_id") or "").strip()
            title = str(form.get("title") or "").strip()
            doc_type = str(form.get("doc_type") or "other").strip()
            upload = form.get("file")
            try:
                if not prop_id or not title or upload is None or not hasattr(upload, "read"):
                    raise ValueError("Property, title and a file are all required.")
                data = await upload.read()
                if not data:
                    raise ValueError("The uploaded file is empty.")
                async with session_scope() as session:
                    await document_service.admin_create_property_document(
                        session,
                        prop_id=uuid.UUID(prop_id),
                        title=title,
                        doc_type=doc_type,
                        filename=getattr(upload, "filename", "file") or "file",
                        data=data,
                    )
                message = (
                    f'<div class="ok">Uploaded <b>{_html.escape(title)}</b> '
                    f"({_html.escape(doc_type)}).</div>"
                )
            except (ValueError, AppError) as exc:
                msg = getattr(exc, "message", None) or str(exc)
                message = f'<div class="err">Upload failed: {_html.escape(msg)}</div>'

        async with session_scope() as session:
            rows = (
                await session.execute(select(Property.id, Property.title).order_by(Property.title))
            ).all()
        options = "".join(
            f'<option value="{r[0]}">{_html.escape(r[1] or str(r[0]))}</option>' for r in rows
        )
        cats = "".join(
            f'<option value="{v}">{_html.escape(label)}</option>' for v, label in _DOC_CATEGORIES
        )
        return HTMLResponse(_UPLOAD_PAGE.format(message=message, options=options, cats=cats))


def setup_admin(app) -> Admin:
    backend = AdminAuth(secret_key=get_settings().jwt_secret)
    admin = Admin(
        app,
        engine=get_engine(),
        authentication_backend=backend,
        base_url="/admin",
        title="CapiMax Admin",
    )
    for view in (
        PropertyAdmin,
        PropertyMilestoneAdmin,
        UserAdmin,
        UserRoleAdmin,
        KycAdmin,
        InvestmentAdmin,
        WalletAdmin,
        TransactionAdmin,
        PlatformSettingAdmin,
        OwnershipLedgerAdmin,
        DistributionAdmin,
        DistributionItemAdmin,
        WithdrawalAdmin,
        PlatformBankAccountAdmin,
        BankDepositClaimAdmin,
        UserBankAccountAdmin,
        UserCryptoWalletAdmin,
        ConnectAccountAdmin,
        SecondaryListingAdmin,
        SecondaryTradeAdmin,
        LpPoolTierAdmin,
        LpExitRequestAdmin,
        LpPositionAdmin,
        FamilyGroupAdmin,
        FamilyMemberAdmin,
        FamilyTransferAdmin,
        BrokerCodeAdmin,
        BrokerReferralAdmin,
        BrokerCommissionAdmin,
        NotificationPreferenceAdmin,
        EmailOutboxAdmin,
        DeveloperUpdateAdmin,
        DeveloperUpdateRecipientAdmin,
        DocumentAdmin,
        SavedPaymentMethodAdmin,
        PaymentCustomerAdmin,
        EstateBeneficiaryAdmin,
        EstateEventAdmin,
        EstateTransferAdmin,
        ScheduledGiftAdmin,
        InstallmentPlanAdmin,
        InstallmentPaymentAdmin,
        DocumentUploadView,
    ):
        admin.add_view(view)
    return admin
