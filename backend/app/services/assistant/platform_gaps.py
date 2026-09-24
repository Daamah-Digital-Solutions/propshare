"""What the company's reference library describes but the platform has not built yet.

The library (``knowledge/reference``) is the client's description of the complete target
platform. Left alone, the model relays it: asked "do you do KYB?", it listed the KYB checks
as if they ran today (live check, 2026-09-24). A rule in the system prompt was not enough, so
``search_reference`` now carries the matching lines below next to the passages it returns,
where the model reads them together.

Keep this list true: when a feature ships, delete its line (and the test that pins it).
"""

from __future__ import annotations

import re

_I = re.IGNORECASE

NOT_BUILT: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bkyb\b|beneficial owner|\bubos?\b|signator|business verification", _I),
        "Company (KYB) verification and beneficial-owner or signatory checks are not on the "
        "platform yet: every account is an individual verified through Sumsub.",
    ),
    (
        re.compile(r"institution|professional investor|service partner|account type", _I),
        "Institution and service-partner accounts are not on the platform yet: everyone signs "
        "up as an investor and requests the owner, broker or liquidity-provider role from "
        "account settings.",
    ),
    (
        re.compile(
            r"\bsanction|\bpeps?\b|politically exposed|adverse.media|\baml\b|"
            r"source.of.(funds|wealth)|transaction monitoring",
            _I,
        ),
        "Sanctions or PEP screening, source-of-funds reviews and transaction monitoring are "
        "not separate steps on the platform yet; identity verification runs through Sumsub.",
    ),
    (
        re.compile(r"\bsms\b|text message|mobile (number|verification)|verify (the |a )?phone", _I),
        "Mobile-number verification by text message is not on the platform yet.",
    ),
    (
        re.compile(r"two.factor|\b2fa\b|\bmfa\b|multi.factor|sensitive action", _I),
        "Two-factor authentication is optional and asked at sign-in; it is not required "
        "before withdrawals or bank changes yet.",
    ),
    (
        re.compile(r"paypal|mercury|revolut|\bwise\b", _I),
        "PayPal, Mercury, Revolut Business and Wise Business are not connected to the "
        "platform yet; get_platform_settings shows the live payment methods.",
    ),
    (
        re.compile(r"\brefund", _I),
        "Refunds cannot be requested on the platform yet; they go through support.",
    ),
    (
        re.compile(
            r"e.?signature|electronic.signature|docusign|sign(ed|ing)? (the )?agreement", _I
        ),
        "Signing agreements electronically is not on the platform yet.",
    ),
    (
        re.compile(
            r"holder register|certificate (reference|verification)|verify (a |my |the )?"
            r"certificate|\bcpv\b|capimax pro\b",
            _I,
        ),
        "Checking a certificate by its reference is not on the platform itself yet: the "
        "Verification Center lists the holder's references and links to Capimax's external "
        "verification site. There is no holder register separate from the platform ledger yet.",
    ),
    (
        re.compile(r"liquidity.provider|\blps?\b|lp (quote|route)|time.limited quote", _I),
        "Liquidity providers do not quote their own price yet: the platform prices an exit "
        "request and a provider funds it (live charges come from get_platform_settings).",
    ),
    (
        re.compile(r"seller fee|listing fee|developer fee|uplift|performance (fee|share)", _I),
        "A secondary-market seller fee, a developer listing fee and an uplift or performance "
        "share are not charged by the platform yet; the live fee settings apply.",
    ),
    (
        re.compile(
            r"phased|tranche|shared participation|developer.retain|purchase option|"
            r"forward.(participation|purchase)|future.(participation|property)",
            _I,
        ),
        "Phased funding, developer shared participation, purchase options and future or "
        "forward participation are not open for investment yet.",
    ),
    (
        re.compile(r"record date|waterfall", _I),
        "Distribution record dates and waterfalls are not on the platform yet: distributions "
        "are paid pro rata to current holders.",
    ),
)
MAX_NOTES = 4


def notes_for(query: str, passages: list[str]) -> list[str]:
    """The not-built lines that the question or the returned passages touch: those the
    question names first, then the rest, at most ``MAX_NOTES``."""
    in_query = [note for pattern, note in NOT_BUILT if pattern.search(query)]
    text = "\n".join(passages)
    in_text = [note for pattern, note in NOT_BUILT if note not in in_query and pattern.search(text)]
    return (in_query + in_text)[:MAX_NOTES]
