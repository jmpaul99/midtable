"""Mailjet Send API v3.1 client for league invite emails (inline HTML)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.services.invite_email import (
    invite_html_body,
    invite_subject_from_html,
    invite_text_body,
)

logger = logging.getLogger(__name__)

MAILJET_SEND_URL = "https://api.mailjet.com/v3.1/send"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 1.0)
ERROR_MAX_LEN = 500


@dataclass(frozen=True)
class MailSendResult:
    status: str  # sent | failed | skipped
    error: str | None = None
    provider_message_id: str | None = None
    http_attempts: int = 0


def _truncate_error(message: str) -> str:
    text = message.strip()
    if len(text) <= ERROR_MAX_LEN:
        return text
    return text[: ERROR_MAX_LEN - 1] + "…"


def send_invite_email(
    *,
    to_email: str,
    league_name: str,
    accept_url: str,
    inviter_name: str,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> MailSendResult:
    """Send a transactional invite via Mailjet HTML. Soft-fails when unconfigured."""
    cfg = settings or get_settings()
    if not cfg.mailjet_configured:
        return MailSendResult(
            status="skipped",
            error="Mailjet is not configured",
            http_attempts=0,
        )

    html = invite_html_body(
        league_name=league_name,
        accept_url=accept_url,
        inviter_name=inviter_name,
        public_app_url=cfg.public_app_url,
    )
    payload: dict[str, Any] = {
        "Messages": [
            {
                "From": {
                    "Email": cfg.mailjet_from_email.strip(),
                    "Name": cfg.mailjet_from_name.strip() or "Midtable",
                },
                "To": [{"Email": to_email.strip().lower()}],
                "Subject": invite_subject_from_html(html),
                "TextPart": invite_text_body(
                    league_name=league_name,
                    accept_url=accept_url,
                    inviter_name=inviter_name,
                ),
                "HTMLPart": html,
            }
        ]
    }

    owns_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(20.0))
    attempts = 0
    last_error = "Unknown Mailjet error"
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                response = http.post(
                    MAILJET_SEND_URL,
                    json=payload,
                    auth=(
                        cfg.mailjet_api_key_public.strip(),
                        cfg.mailjet_api_key_private.strip(),
                    ),
                )
            except httpx.TransportError as exc:
                last_error = _truncate_error(f"Transport error: {exc}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                    continue
                break

            if response.status_code in {429} or response.status_code >= 500:
                last_error = _truncate_error(
                    f"Mailjet HTTP {response.status_code}: {response.text}"
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                    continue
                break

            if response.status_code >= 400:
                return MailSendResult(
                    status="failed",
                    error=_truncate_error(
                        f"Mailjet HTTP {response.status_code}: {response.text}"
                    ),
                    http_attempts=attempts,
                )

            message_id = _extract_message_id(response)
            return MailSendResult(
                status="sent",
                provider_message_id=message_id,
                http_attempts=attempts,
            )
    finally:
        if owns_client:
            http.close()

    return MailSendResult(
        status="failed",
        error=last_error,
        http_attempts=attempts,
    )


def _extract_message_id(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    messages = data.get("Messages")
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict):
        return None
    to_list = first.get("To")
    if isinstance(to_list, list) and to_list:
        entry = to_list[0]
        if isinstance(entry, dict):
            mid = entry.get("MessageID") or entry.get("MessageUUID")
            if mid is not None:
                return str(mid)
    mid = first.get("MessageID") or first.get("MessageUUID")
    return str(mid) if mid is not None else None
