from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RateLimit:
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    items: tuple[dict[str, Any], ...]
    rate_limit: RateLimit
    fetched_at: datetime


class FootballProvider(Protocol):
    async def competitions(self, codes: Sequence[str]) -> ProviderResponse: ...

    async def teams(self, competition_codes: Sequence[str], season: int) -> ProviderResponse: ...

    async def matches(
        self,
        competition_codes: Sequence[str],
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: Sequence[str] = (),
    ) -> ProviderResponse: ...

    async def standings(
        self, competition_codes: Sequence[str], season: int
    ) -> ProviderResponse: ...

    async def close(self) -> None: ...
