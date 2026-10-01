"""get_verification_services: which partner verifies which Capimax record, and how.

PropShare verifies nothing itself. Asked whether a certificate, a valuation, a policy or an
agreement is genuine, the assistant used to send everyone to the Verification Center in
general. This tool hands it the five designated services (``verification_partners``), so it
can name the one that fits, say what to enter there and link it. A holder's own certificate
references come from get_my_holdings.
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
    url: str
    tip: str | None


class VerificationServicesOut(ToolOutput):
    services: list[VerificationServiceOut]
    note: str


_NOTE = (
    "Send the user to the ONE service that matches what they want to verify, say what to enter "
    "there, and link its url exactly as given, written as [action](url). An investment "
    "certificate is checked at Capimax Verify with the reference printed on it (a signed-in "
    "holder's references are in get_my_holdings). PropShare itself verifies nothing, and its own "
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
