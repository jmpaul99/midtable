"""Brand-aligned league invite email (HTML + plain text).

Matchday shell from brand/midtable-brand-guide.md — Managerial + Kickoff voice.
HTML source: brand/emails/league-invite.html
"""

from __future__ import annotations

import re
from functools import lru_cache
from html import escape, unescape
from pathlib import Path

# Served from frontend/public/brand (synced from brand/logos/product).
MATCHDAY_LOCKUP_PATH = "/brand/png/lockup-matchday.png"
MATCHDAY_WORDMARK_PATH = "/brand/png/wordmark-matchday.png"

# Placeholders in brand/emails/league-invite.html (must stay in sync).
TEMPLATE_PLACEHOLDERS = frozenset(
    {
        "{{HOME_URL}}",
        "{{LOGO_URL}}",
        "{{WORDMARK_URL}}",
        "{{LEAGUE_NAME}}",
        "{{INVITER_NAME}}",
        "{{ACCEPT_URL}}",
        "{{ACCEPT_URL_DISPLAY}}",
    }
)

_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


def _repo_root() -> Path:
    """Resolve repo root from this file (backend/app/services/ → ../../..)."""
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _invite_html_template() -> str:
    path = _repo_root() / "brand" / "emails" / "league-invite.html"
    return path.read_text(encoding="utf-8")


def invite_home_url(public_app_url: str) -> str:
    """Absolute app homepage URL."""
    return public_app_url.strip().rstrip("/")


def invite_logo_url(public_app_url: str) -> str:
    """Absolute Matchday lockup PNG for email clients (SVG is unreliable)."""
    base = invite_home_url(public_app_url)
    if not base:
        return ""
    return f"{base}{MATCHDAY_LOCKUP_PATH}"


def invite_wordmark_url(public_app_url: str) -> str:
    """Absolute Matchday wordmark PNG for email footers."""
    base = invite_home_url(public_app_url)
    if not base:
        return ""
    return f"{base}{MATCHDAY_WORDMARK_PATH}"


def invite_subject(*, league_name: str) -> str:
    """Subject line from <title> in brand/emails/league-invite.html."""
    match = _TITLE_RE.search(_invite_html_template())
    if match is None:
        raise ValueError("league-invite.html is missing a <title>")
    # Plain-text subject: substitute league name without HTML escaping.
    return match.group(1).replace("{{LEAGUE_NAME}}", league_name).strip()


def invite_subject_from_html(html: str) -> str:
    """Read Mailjet Subject from a rendered HTML body <title>."""
    match = _TITLE_RE.search(html)
    if match is None:
        raise ValueError("Rendered invite HTML is missing a <title>")
    return unescape(match.group(1)).strip()


def invite_text_body(*, league_name: str, accept_url: str, inviter_name: str) -> str:
    return "\n".join(
        [
            f"You've been invited to {league_name}!",
            "",
            f"{inviter_name} invited you to Midtable. Accept below and get ready for kickoff.",
            "",
            f"Accept invite: {accept_url}",
            "",
            "If you weren't expecting this, ignore the email.",
            "",
            "Midtable · Every result moves the table.",
        ]
    )


def invite_html_body(
    *,
    league_name: str,
    accept_url: str,
    inviter_name: str,
    public_app_url: str = "",
) -> str:
    """Table-based Matchday email. Safe for league_name / URLs via escaping."""
    home = invite_home_url(public_app_url)
    logo = invite_logo_url(public_app_url)
    wordmark = invite_wordmark_url(public_app_url)
    replacements = {
        "{{HOME_URL}}": escape(home, quote=True),
        "{{LOGO_URL}}": escape(logo, quote=True),
        "{{WORDMARK_URL}}": escape(wordmark, quote=True),
        "{{LEAGUE_NAME}}": escape(league_name),
        "{{INVITER_NAME}}": escape(inviter_name),
        "{{ACCEPT_URL}}": escape(accept_url, quote=True),
        "{{ACCEPT_URL_DISPLAY}}": escape(accept_url),
    }
    html = _invite_html_template()
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html
