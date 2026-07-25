"""Unit tests for league invite email builders — variables/escaping, not copy."""

from __future__ import annotations

import re

from app.services.invite_email import (
    MATCHDAY_LOCKUP_PATH,
    MATCHDAY_WORDMARK_PATH,
    TEMPLATE_PLACEHOLDERS,
    _invite_html_template,
    invite_html_body,
    invite_logo_url,
    invite_subject,
    invite_text_body,
    invite_wordmark_url,
)


def test_brand_template_declares_all_placeholders():
    template = _invite_html_template()
    missing = sorted(p for p in TEMPLATE_PLACEHOLDERS if p not in template)
    assert missing == [], f"Template missing placeholders: {missing}"


def test_invite_subject_comes_from_html_title():
    template = _invite_html_template()
    assert "<title>" in template.lower()
    assert "{{LEAGUE_NAME}}" in template
    subject = invite_subject(league_name="Euro Pool")
    assert "Euro Pool" in subject
    assert "{{" not in subject


def test_invite_text_body_includes_dynamic_values():
    accept = "https://app.example/invites/accept?token=abc"
    text = invite_text_body(
        league_name="Euro Pool",
        accept_url=accept,
        inviter_name="Alex",
    )
    assert "Euro Pool" in text
    assert "Alex" in text
    assert accept in text


def test_invite_html_substitutes_all_placeholders():
    accept = "https://app.example/invites/accept?token=abc"
    home = "https://app.example"
    html = invite_html_body(
        league_name="Euro Pool",
        accept_url=accept,
        inviter_name="Alex",
        public_app_url=home,
    )
    leftover = sorted(
        m.group(0) for m in re.finditer(r"\{\{[A-Z0-9_]+\}\}", html)
    )
    assert leftover == [], f"Unreplaced placeholders: {leftover}"

    assert "Euro Pool" in html
    assert "Alex" in html
    assert accept in html
    assert f'href="{home}"' in html
    assert f"{home}{MATCHDAY_LOCKUP_PATH}" in html
    assert f"{home}{MATCHDAY_WORDMARK_PATH}" in html
    assert invite_logo_url(home) in html
    assert invite_wordmark_url(home) in html


def test_invite_html_escapes_user_content():
    html = invite_html_body(
        league_name="<script>alert(1)</script> League",
        accept_url="https://app.example/accept?a=1&b=2",
        inviter_name='Sam & "friend"',
        public_app_url="https://app.example",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Sam &amp; &quot;friend&quot;" in html
    assert "a=1&amp;b=2" in html
    leftover = sorted(
        m.group(0) for m in re.finditer(r"\{\{[A-Z0-9_]+\}\}", html)
    )
    assert leftover == []
