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
import datetime as dt
import html as htmllib
import logging
import re
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import get_settings

logger = logging.getLogger("capimax.email")

# --------------------------------------------------------------------------- #
# Branded HTML email template (professional, responsive, email-client-safe).
# Table-based layout + inline styles only (no <style>/flex/grid — Outlook/Gmail
# strip those). Every email (verification, password reset, and all notification
# emails) is wrapped in this shell so the whole comms surface looks cohesive.
# --------------------------------------------------------------------------- #
_BRAND = "#198653"  # primary green (matches the app --primary)
_GOLD = "#f59f0a"  # accent gold (--accent)
_INK = "#222a26"  # body text (--foreground)
_MUTED = "#8a8f8b"  # muted / footer text
_BORDER = "#eae8e3"
_BG = "#f4f5f3"  # page background (soft cream)
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_URL_RE = re.compile(r"(https?://[^\s<>\"]+)")


def _linkify(escaped: str) -> str:
    """Wrap bare URLs (in already-HTML-escaped text) in on-brand anchors."""
    return _URL_RE.sub(
        lambda m: (
            f'<a href="{m.group(1)}" style="color:{_BRAND};text-decoration:underline;'
            f'word-break:break-all;">{m.group(1)}</a>'
        ),
        escaped,
    )


def _paragraphs_html(paragraphs: list[str]) -> str:
    blocks = []
    for para in paragraphs:
        if not para or not para.strip():
            continue
        safe = _linkify(htmllib.escape(para.strip()))
        blocks.append(
            f'<p style="margin:0 0 16px;color:{_INK};font-size:15px;'
            f'line-height:1.65;">{safe}</p>'
        )
    return "\n".join(blocks)


def render_email_html(
    *,
    title: str,
    paragraphs: list[str],
    cta_label: str | None = None,
    cta_url: str | None = None,
    footnote: str | None = None,
    preheader: str | None = None,
) -> str:
    """Render a plain message into the branded CapiMax PropShare HTML email."""
    site = get_settings().app_base_url.rstrip("/")
    year = dt.datetime.now(dt.UTC).year
    esc_title = htmllib.escape(title)

    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 4px;">
                <tr><td align="center" style="border-radius:10px;background:{_BRAND};">
                  <a href="{cta_url}" style="display:inline-block;padding:14px 30px;color:#ffffff;
                     text-decoration:none;font-weight:600;font-size:15px;font-family:{_FONT};
                     border-radius:10px;">{htmllib.escape(cta_label)}</a>
                </td></tr>
              </table>
              <p style="margin:16px 0 0;color:{_MUTED};font-size:13px;line-height:1.6;">
                Or copy and paste this link into your browser:<br>
                <a href="{cta_url}"
                   style="color:{_BRAND};word-break:break-all;">{htmllib.escape(cta_url)}</a>
              </p>"""

    footnote_html = ""
    if footnote:
        footnote_html = (
            f'<p style="margin:24px 0 0;padding-top:20px;border-top:1px solid {_BORDER};'
            f'color:{_MUTED};font-size:13px;line-height:1.6;">'
            f"{_linkify(htmllib.escape(footnote))}</p>"
        )

    preheader_html = ""
    if preheader:
        preheader_html = (
            '<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;'
            f'height:0;width:0;">{htmllib.escape(preheader)}</div>'
        )

    return f"""\
<div style="background:{_BG};margin:0;padding:0;">{preheader_html}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:{_BG};padding:28px 12px;font-family:{_FONT};">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;">
        <tr><td style="padding:4px 6px 20px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="vertical-align:middle;padding-right:12px;">
              <div style="width:42px;height:42px;background:{_BRAND};border-radius:11px;
                   color:#ffffff;font-size:20px;font-weight:700;text-align:center;
                   line-height:42px;font-family:{_FONT};">C</div>
            </td>
            <td style="vertical-align:middle;">
              <span style="font-size:18px;font-weight:700;color:{_INK};">Capimax</span>
              <span style="font-size:18px;font-weight:700;color:{_BRAND};"> PropShare</span>
            </td>
          </tr></table>
        </td></tr>
        <tr><td style="background:#ffffff;border:1px solid {_BORDER};border-radius:14px;
               border-top:3px solid {_GOLD};padding:36px 40px;">
          <h1 style="margin:0 0 20px;color:{_INK};font-size:22px;font-weight:700;
              line-height:1.3;">{esc_title}</h1>
          {_paragraphs_html(paragraphs)}
          {cta_html}
          {footnote_html}
        </td></tr>
        <tr><td style="padding:24px 20px 8px;text-align:center;">
          <p style="margin:0 0 8px;color:{_MUTED};font-size:12px;line-height:1.6;">
            <a href="{site}"
               style="color:{_MUTED};text-decoration:underline;">Visit CapiMax PropShare</a>
            &nbsp;&middot;&nbsp;
            <a href="{site}/support" style="color:{_MUTED};text-decoration:underline;">Support</a>
            &nbsp;&middot;&nbsp;
            <a href="{site}/privacy" style="color:{_MUTED};text-decoration:underline;">Privacy</a>
          </p>
          <p style="margin:0;color:{_MUTED};font-size:12px;line-height:1.6;">
            This is an automated message from CapiMax PropShare — please do not reply.<br>
            &copy; {year} CapiMax PropShare. Fractional real-estate ownership.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>"""


async def send_email(*, to: str, subject: str, text: str, html: str | None = None) -> None:
    """Send an email via the configured provider as multipart (plain text + branded HTML).

    ``text`` is always the fallback body; ``html`` is the rich body. When ``html`` is omitted
    the plain text is auto-wrapped in the branded CapiMax PropShare template, so EVERY email
    (verification, reset, notifications) looks professional with no per-caller work. A provider
    error is logged and re-raised so the caller can decide — except console, which never raises."""
    settings = get_settings()
    provider = settings.email_provider.lower()
    if html is None:
        html = render_email_html(title=subject, paragraphs=text.split("\n\n"))

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
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                    "html": html,
                },
            )
            resp.raise_for_status()
        return

    if provider == "smtp":
        await asyncio.to_thread(_send_smtp, to, subject, text, html)
        return

    raise ValueError(f"Unknown EMAIL_PROVIDER: {settings.email_provider!r}")


def _send_smtp(to: str, subject: str, text: str, html: str | None = None) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)  # plain-text fallback part
    if html:
        msg.add_alternative(html, subtype="html")  # preferred rich part
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def build_link(path: str, token: str) -> str:
    """Build a frontend link for an email action, e.g. /verify-email?token=…"""
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}{path}?token={token}"
