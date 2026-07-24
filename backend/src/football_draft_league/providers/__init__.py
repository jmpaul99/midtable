from collections.abc import Callable

from football_draft_league.config import Settings
from football_draft_league.providers.base import FootballProvider
from football_draft_league.providers.football_data import FootballDataProvider


ProviderFactory = Callable[[Settings], FootballProvider]


def _football_data(settings: Settings) -> FootballProvider:
    if not settings.football_data_api_token:
        raise ValueError("FOOTBALL_DATA_API_TOKEN is required")
    return FootballDataProvider(
        settings.football_data_api_token,
        base_url=str(settings.football_data_base_url),
        requests_per_minute=settings.football_data_requests_per_minute,
    )


PROVIDERS: dict[str, ProviderFactory] = {"football-data.org": _football_data}


def provider_for(name: str, settings: Settings) -> FootballProvider:
    try:
        return PROVIDERS[name](settings)
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {name}") from exc


__all__ = ["FootballDataProvider", "FootballProvider", "provider_for", "PROVIDERS"]
