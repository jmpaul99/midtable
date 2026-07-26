"""Parse.bot FIFA.com rankings client (men + women)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FifaRankingRow:
    rank: int
    team_name: str
    country_code: str | None
    confederation: str | None
    as_of: date | None


class FifaRankingsError(RuntimeError):
    pass


class ParseFifaRankingsProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("PARSE_API_KEY is required")
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=httpx.Timeout(60.0),
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ParseFifaRankingsProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_mens(self, *, limit: int | None = None) -> list[FifaRankingRow]:
        return self._fetch("get_mens_world_ranking", limit=limit)

    def fetch_womens(self, *, limit: int | None = None) -> list[FifaRankingRow]:
        return self._fetch("get_womens_world_ranking", limit=limit)

    def _fetch(self, endpoint: str, *, limit: int | None) -> list[FifaRankingRow]:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        try:
            response = self._client.get(f"/{endpoint}", params=params or None)
        except httpx.HTTPError as exc:
            raise FifaRankingsError(f"Parse FIFA request failed: {exc}") from exc
        if response.status_code >= 400:
            logger.error(
                "parse fifa error endpoint=%s status=%s body=%s",
                endpoint,
                response.status_code,
                response.text[:500],
            )
            raise FifaRankingsError(
                f"Parse FIFA returned {response.status_code} for {endpoint}"
            )
        payload = response.json()
        results = _extract_results(payload)
        rows: list[FifaRankingRow] = []
        for item in results:
            row = _parse_row(item)
            if row is not None:
                rows.append(row)
        if not rows:
            raise FifaRankingsError(f"No ranking rows returned from {endpoint}")
        return sorted(rows, key=lambda r: r.rank)


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        results = data.get("Results") or data.get("results") or data.get("ranking")
        if isinstance(results, list):
            return [x for x in results if isinstance(x, dict)]
    results = payload.get("Results") or payload.get("results") or payload.get("ranking")
    if isinstance(results, list):
        return [x for x in results if isinstance(x, dict)]
    return []


def _parse_row(item: dict[str, Any]) -> FifaRankingRow | None:
    rank_raw = item.get("Rank") if item.get("Rank") is not None else item.get("rank")
    if rank_raw is None:
        return None
    try:
        rank = int(rank_raw)
    except (TypeError, ValueError):
        return None
    name = _team_name(item)
    if not name:
        return None
    country = item.get("IdCountry") or item.get("country_code") or item.get("idCountry")
    country_code = str(country).strip().upper() if country else None
    confed = item.get("ConfederationName") or item.get("confederation")
    confederation = str(confed).strip() if confed else None
    as_of = _parse_date(item.get("PubDate") or item.get("date") or item.get("pubDate"))
    return FifaRankingRow(
        rank=rank,
        team_name=name,
        country_code=country_code,
        confederation=confederation,
        as_of=as_of,
    )


def _team_name(item: dict[str, Any]) -> str | None:
    names = item.get("TeamName") or item.get("teamName") or item.get("name")
    if isinstance(names, str) and names.strip():
        return names.strip()
    if isinstance(names, list):
        preferred = None
        for entry in names:
            if not isinstance(entry, dict):
                continue
            desc = entry.get("Description") or entry.get("description")
            if not desc:
                continue
            locale = str(entry.get("Locale") or entry.get("locale") or "").lower()
            if locale.startswith("en"):
                return str(desc).strip()
            if preferred is None:
                preferred = str(desc).strip()
        return preferred
    return None


def _parse_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%d %B, %Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
