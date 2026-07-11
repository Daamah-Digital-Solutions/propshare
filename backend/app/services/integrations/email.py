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
_BRAND = "#198653"  # primary green (matches the app --primary + the logo mark)
_BRAND_DK = "#0f5b39"  # deeper green (button depth)
_GOLD = "#f59f0a"  # accent gold (--accent)
_INK = "#17211d"  # body/heading text — deep near-black, echoes the logo wordmark
_MUTED = "#8a8f8b"  # muted / footer text
_BORDER = "#e8e6e1"
_BG = "#eef1ee"  # page background (soft) so the white card lifts off it
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
    logo = f"{site}/capimax-logo-email.png"  # hosted PNG (email clients can't render SVG)

    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
              <table role="presentation" border="0" cellpadding="0" cellspacing="0"
                     style="margin:26px 0 4px;">
                <tr><td align="center" style="border-radius:10px;background:{_BRAND};
                     border-bottom:2px solid {_BRAND_DK};">
                  <a href="{cta_url}" style="display:inline-block;padding:15px 34px;color:#ffffff;
                     text-decoration:none;font-weight:600;font-size:15px;letter-spacing:.2px;
                     font-family:{_FONT};border-radius:10px;">{htmllib.escape(cta_label)}</a>
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
            f'<p style="margin:26px 0 0;padding-top:20px;border-top:1px solid {_BORDER};'
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
  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0"
         style="background:{_BG};padding:32px 12px;font-family:{_FONT};">
    <tr><td align="center">
      <table role="presentation" width="600" border="0" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;">
        <!-- Card -->
        <tr><td style="background:#ffffff;border:1px solid {_BORDER};border-radius:16px;
               overflow:hidden;box-shadow:0 6px 22px rgba(20,40,30,0.06);">
          <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
            <!-- Brand strip -->
            <tr><td style="height:5px;line-height:5px;font-size:0;
                   background:{_BRAND};">&nbsp;</td></tr>
            <!-- Logo header -->
            <tr><td align="center" style="background:#ffffff;padding:32px 40px 24px;
                   border-bottom:1px solid {_BORDER};">
              <img src="{logo}" width="220" height="62" alt="CapiMax PropShare"
                   style="display:block;width:220px;max-width:62%;height:auto;border:0;
                   outline:none;text-decoration:none;margin:0 auto;">
            </td></tr>
            <!-- Body -->
            <tr><td style="background:#ffffff;padding:34px 40px 40px;">
              <h1 style="margin:0 0 12px;color:{_INK};font-size:22px;font-weight:700;
                  line-height:1.3;">{esc_title}</h1>
              <div style="height:3px;width:46px;line-height:3px;font-size:0;background:{_GOLD};
                   border-radius:2px;margin:0 0 22px;">&nbsp;</div>
              {_paragraphs_html(paragraphs)}
              {cta_html}
              {footnote_html}
            </td></tr>
          </table>
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:24px 20px 6px;text-align:center;">
          <p style="margin:0 0 10px;color:{_MUTED};font-size:12px;line-height:1.7;">
            <a href="{site}"
               style="color:{_MUTED};text-decoration:underline;">Visit CapiMax PropShare</a>
            &nbsp;&middot;&nbsp;
            <a href="{site}/support" style="color:{_MUTED};text-decoration:underline;">Support</a>
            &nbsp;&middot;&nbsp;
            <a href="{site}/privacy" style="color:{_MUTED};text-decoration:underline;">Privacy</a>
            &nbsp;&middot;&nbsp;
            <a href="{site}/terms" style="color:{_MUTED};text-decoration:underline;">Terms</a>
          </p>
          <p style="margin:0;color:{_MUTED};font-size:12px;line-height:1.7;">
            This is an automated message from CapiMax PropShare — please do not reply.<br>
            &copy; {year} CapiMax PropShare · Fractional real-estate ownership across the GCC.
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
