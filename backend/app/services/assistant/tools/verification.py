"""get_verification_services: where each Capimax record is verified, and how.

Asked whether a certificate, a valuation, a policy or an agreement is genuine, the assistant
used to send everyone to the Verification Center in general. This tool hands it the five
designated services (``verification_partners``), so it can name the one that fits, say what to
enter there and link it. The first is PropShare's own: an investment certificate is verified
here by its QR code (a holder's own certificates come from get_my_certificates).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import verification_partners
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import NoArgs, ToolOutput, ToolSpec, register


class VerificationServiceOut(ToolOutput):
    key: str
    title: str
    provider: str
    verifies: str
    how_to_verify: str
    action: str
    url: str  # a partner's link, or (internal) a page of PropShare
    internal: bool
    tip: str | None


class VerificationServicesOut(ToolOutput):
    services: list[VerificationServiceOut]
    note: str


_NOTE = (
    "Send the user to the ONE service that matches what they want to verify, say what to enter "
    "there, and link its url exactly as given, written as [action](url). An investment "
    "certificate is verified on Capimax PropShare itself (internal = true): its QR code opens its "
    "verification page; without a camera, the verification code printed beside the QR is "
    "entered on the Verification Center (that service's url). A signed-in holder's own "
    "certificates, with each one's verification page, are in get_my_certificates. PropShare's "
    "certificates and records are not blockchain records: the blockchain service is for the "
    "ecosystem's blockchain-enabled platforms (Capimax BRX, Capimax RT)."
)


async def _get_verification_services(session: AsyncSession, ctx: AgentContext, args) -> dict:
    return {
        "services": [
            {
                "key": s.key,
                "title": s.title,
                "provider": s.provider,
                "verifies": s.verifies,
                "how_to_verify": s.how_to_verify,
                "action": s.action,
                "url": s.url,
                "internal": s.internal,
                "tip": s.tip,
            }
            for s in verification_partners.SERVICES
        ],
        "note": _NOTE,
    }


register(
    ToolSpec(
        "get_verification_services",
        "Where to verify a Capimax document, certificate or record (authenticity, validity, "
        "current status): investment certificates and Capimax documents, valuation and "
        "financial reports, insurance certificates, legal documents and agreements, and "
        "records of the ecosystem's blockchain-enabled platforms. Each service has its provider, "
        "what to enter there and its link.",
        NoArgs,
        VerificationServicesOut,
        "informational",
        _get_verification_services,
    )
)
