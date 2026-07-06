"""Unit tests for the branded HTML email template (no DB / no network).

Guards that every outgoing email is wrapped in the professional CapiMax PropShare
shell, that user-supplied text is HTML-escaped (no injection / broken markup), that a
CTA renders as a button + copy-paste fallback, and that plain-text sends auto-wrap."""

from __future__ import annotations

import pytest

from app.services.integrations import email


def test_render_email_html_brand_cta_and_escaping():
    html = email.render_email_html(
        title="Verify your <email>",
        paragraphs=["Hello & welcome.", "Continue at https://x.test/verify?token=abc"],
        cta_label="Verify email address",
        cta_url="https://x.test/verify?token=abc",
        footnote="Ignore if this wasn't you.",
        preheader="Confirm your email",
    )
    # Branded shell + wordmark + brand green.
    assert "PropShare" in html
    assert "#198653" in html
    # CTA button label + link, plus the copy-paste fallback (url appears at least twice).
    assert "Verify email address" in html
    assert html.count("https://x.test/verify?token=abc") >= 2
    # User-facing text is HTML-escaped — no raw tag or ampersand leaks into the markup.
    assert "<email>" not in html
    assert "Hello &amp; welcome." in html


@pytest.mark.asyncio
async def test_send_email_autowraps_plain_text(monkeypatch):
    """A caller that passes only text (e.g. the notification outbox) still gets the
    branded HTML: send_email splits paragraphs and renders the shell before sending."""
    captured: dict = {}
    monkeypatch.setattr(
        email, "render_email_html", lambda **kw: (captured.update(kw), "<html/>")[1]
    )
    monkeypatch.setattr(email.get_settings(), "email_provider", "console", raising=False)

    await email.send_email(
        to="investor@x.test",
        subject="Deposit received",
        text="Your deposit of 100 USD was credited.\n\nView it in your wallet.",
    )
    assert captured["title"] == "Deposit received"
    assert captured["paragraphs"] == [
        "Your deposit of 100 USD was credited.",
        "View it in your wallet.",
    ]
