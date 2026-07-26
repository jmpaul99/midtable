"""Cloudflare Turnstile siteverify (server-side only)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import Settings

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
EMAIL_STATUS_ACTION = "email-status"


def verify_turnstile_token(
    *,
    token: str,
    settings: Settings,
    expected_action: str,
    remote_ip: str | None = None,
) -> None:
    """Raise 403 unless siteverify succeeds with expected action and hostname."""
    secret = settings.turnstile_secret.strip()
    hostnames = settings.turnstile_hostname_set
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 2048
        or not secret
        or not hostnames
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    body: dict[str, str] = {"secret": secret, "response": token}
    if remote_ip:
        body["remoteip"] = remote_ip

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(SITEVERIFY_URL, data=body)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("turnstile siteverify failed error=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc

    hostname = str(result.get("hostname") or "").strip().lower()
    action = str(result.get("action") or "")
    if (
        not result.get("success")
        or action != expected_action
        or hostname not in hostnames
    ):
        logger.warning(
            "turnstile rejected success=%s action=%s hostname=%s expected_action=%s",
            result.get("success"),
            action,
            hostname,
            expected_action,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
