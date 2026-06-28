"""Minimal transactional email (Phase 1: verification + password reset ONLY).

Provider is chosen by ``EMAIL_PROVIDER``:
  * "console" (default, dev) — logs the message + link; never fails a flow.
  * "resend"  — POST to the Resend API via httpx.
  * "smtp"    — send via SMTP (run in a thread; smtplib is blocking).

The full notifications/comms system (in-app feed, SMS, WhatsApp, templates) is
Phase 12. This module is intentionally tiny and single-purpose.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import get_settings

logger = logging.getLogger("capimax.email")


async def send_email(*, to: str, subject: str, text: str) -> None:
    """Send a plain-text email via the configured provider. Best-effort: a
    provider error is logged and raised so the caller can decide, except the
    console provider which never raises."""
    settings = get_settings()
    provider = settings.email_provider.lower()

    if provider == "console":
        logger.info("[email:console] to=%s subject=%r\n%s", to, subject, text)
        return

    if provider == "resend":
        if not settings.resend_api_key:
            logger.warning("[email:resend] RESEND_API_KEY missing; falling back to console")
            logger.info("[email:console] to=%s subject=%r\n%s", to, subject, text)
            return
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to], "subject": subject, "text": text},
            )
            resp.raise_for_status()
        return

    if provider == "smtp":
        await asyncio.to_thread(_send_smtp, to, subject, text)
        return

    raise ValueError(f"Unknown EMAIL_PROVIDER: {settings.email_provider!r}")


def _send_smtp(to: str, subject: str, text: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def build_link(path: str, token: str) -> str:
    """Build a frontend link for an email action, e.g. /verify-email?token=…"""
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}{path}?token={token}"
