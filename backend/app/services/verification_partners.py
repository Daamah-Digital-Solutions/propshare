"""Where each kind of Capimax record is verified: the ecosystem's designated partners.

PropShare verifies nothing itself. The client named five services (2026-10-01), each for one
kind of record; the Verification Center page lists them and the assistant sends a user to the
one that matches what they hold, with what to enter there and the link. The wording is the
client's own.

The SPA keeps the same five in ``src/lib/verificationPartners.ts`` (test_verification_services
keeps the two in step), and these URLs are the only links outside the platform the assistant
may hand out.
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


SERVICES: tuple[VerificationService, ...] = (
    VerificationService(
        key="capimax_documents",
        title="Capimax Documents & Investment Certificates",
        provider="CIM Global Financial",
        verifies=(
            "Capimax-issued documents, investment certificates, official records and other "
            "ecosystem documents."
        ),
        how_to_verify=(
            "Enter the Verification Number, Record Number, Certificate Number, or scan the QR "
            "Code to confirm authenticity and current verification status."
        ),
        action="Verify Document / Certificate",
        link_label="Open Capimax Verify — CIM Global Financial",
        url="https://www.cimglobalfinancial.com/capimax-verify",
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

# url -> the label of the first service using it (two services share CIM's Capimax Verify)
LINK_LABELS: dict[str, str] = {s.url: s.link_label for s in reversed(SERVICES)}
URLS: frozenset[str] = frozenset(LINK_LABELS)
