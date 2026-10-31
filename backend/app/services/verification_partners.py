"""Where each kind of Capimax record is verified.

The client named five services (2026-10-01), each for one kind of record; the Verification
Center page lists them and the assistant sends a user to the one that matches what they hold,
with what to enter there and the link. The wording is the client's own.

The first is PropShare's own (client, 2026-10-28, as on Capimax BRX): an investment certificate
carries a QR code that opens its verification page here, ``/verify/{code}``; CIM Global
Financial is no longer the way to verify a certificate. The other four are partners' sites.

The SPA keeps the same five in ``src/lib/verificationPartners.ts`` (test_verification_services
keeps the two in step), and the partners' URLs are the only links outside the platform the
assistant may hand out.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class VerificationService:
    key: str
    title: str
    provider: str
    verifies: str
    how_to_verify: str
    action: str
    link_label: str
    url: str
    # what the partner's page looks like today, for the assistant only (never on the page)
    tip: str | None = None
    # checked on PropShare itself: ``url`` is a path of the site, not a partner's link
    internal: bool = False


SERVICES: tuple[VerificationService, ...] = (
    VerificationService(
        key="capimax_certificates",
        title="Capimax PropShare Investment Certificates",
        provider="Capimax PropShare",
        verifies=(
            "Investment certificates issued on Capimax PropShare: whether a certificate is "
            "authentic and its current status."
        ),
        how_to_verify=(
            "Scan the QR code printed on the certificate with your phone's camera: it opens the "
            "certificate's verification page on Capimax PropShare. Can't scan it? Enter the "
            "verification code shown beside the QR code on the Verification Center."
        ),
        action="Verify Certificate",
        link_label="Verify a certificate",
        url="/verification-center",
        internal=True,
    ),
    VerificationService(
        key="valuation_financial",
        title="Valuation & Financial Document Verification",
        provider="CIM Global Financial",
        verifies=(
            "Property and unit valuation reports, investment studies, financial analyses, "
            "accounting records, financial reports, due diligence reports and other financial "
            "documents associated with Capimax assets and projects."
        ),
        how_to_verify=(
            "Enter the Document Number or Verification ID to authenticate the record and access "
            "available verified documentation."
        ),
        action="Verify Valuation / Financial Report",
        link_label="Verify with CIM Global Financial",
        url="https://www.cimglobalfinancial.com/capimax-verify",
    ),
    VerificationService(
        key="insurance",
        title="Insurance Certificate Verification",
        provider="CoverTech Insurance",
        verifies=(
            "Insurance certificates and insurance-related documents issued for Capimax assets, "
            "investments, platforms and associated risks."
        ),
        how_to_verify=(
            "Use the verification service to confirm the authenticity, coverage information and "
            "current status of the relevant insurance certificate or document."
        ),
        action="Verify Insurance Certificate",
        link_label="Verify with CoverTech Insurance",
        url="https://www.covertechinsurance.com/capimax-ecosystem",
        tip="The link opens CoverTech's Capimax ecosystem page, which leads on to the CoverTech "
        "Verification Center.",
    ),
    VerificationService(
        key="legal",
        title="Legal Document & Agreement Verification",
        provider="LexCrest Global",
        verifies=(
            "Legal documents, agreements, due diligence documents and other legal records "
            "associated with Capimax assets, transactions and platforms."
        ),
        how_to_verify=(
            "Enter the unique Document Number shown on the document to confirm its authenticity. "
            "Where permitted, public documents may also be previewed or downloaded."
        ),
        action="Verify Legal Document",
        link_label="Open LexCrest Document Center",
        url="https://lexcrestlegal.xyz/document-center",
    ),
    VerificationService(
        key="blockchain",
        title="Blockchain, Smart Contract & Digital Asset Verification",
        provider="Proof Anchor",
        verifies=(
            "Blockchain records, smart contracts, tokenized assets, tokens, audit reports and "
            "digital certificates associated with Capimax blockchain-enabled platforms."
        ),
        how_to_verify=(
            "Search using a Certificate Number, Verification Number, Contract Address, Token "
            "Address, Asset ID, or Project Name to access the corresponding verification record."
        ),
        action="Verify Blockchain Record",
        link_label="Verify with Proof Anchor",
        url="https://www.proofanchor.io/verify",
    ),
)

# a partner's url -> its label (the partners' sites only: the certificate check is ours)
LINK_LABELS: dict[str, str] = {s.url: s.link_label for s in reversed(SERVICES) if not s.internal}
URLS: frozenset[str] = frozenset(LINK_LABELS)
BY_KEY: dict[str, VerificationService] = {s.key: s for s in SERVICES}
# how a PropShare investment certificate is verified: its QR code / verification code, here
CERTIFICATES: VerificationService = BY_KEY["capimax_certificates"]
