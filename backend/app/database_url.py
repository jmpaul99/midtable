"""Normalize Postgres URLs for SQLAlchemy / psycopg."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "host.docker.internal"})


def ensure_remote_ssl(url: str) -> str:
    """Require TLS for remote Postgres hosts; leave local Supabase URLs unchanged."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or host in _LOCAL_HOSTS:
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(query)))
