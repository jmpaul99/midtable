from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import IdSchema


class RankingCatalogResponse(IdSchema):
    key: str
    label: str
    kind: str
    source: str
    as_of: date | None = None


class RankingCatalogEntryResponse(IdSchema):
    rank: int
    team_name: str
    country_code: str | None = None
    confederation: str | None = None


class RankingCatalogDetailResponse(RankingCatalogResponse):
    entries: list[RankingCatalogEntryResponse] = Field(default_factory=list)


class RankingCatalogCreate(BaseModel):
    label: str
    text: str


class RankingCatalogOverrideUpsert(BaseModel):
    country_code: str | None = None
    team_name: str | None = None
    provider: str = "football-data.org"
    external_team_id: str


class RankingCatalogOverrideResponse(IdSchema):
    country_code: str | None = None
    team_name: str | None = None
    provider: str
    external_team_id: str


class RankingCatalogUnmatchedRow(BaseModel):
    rank: int
    team_name: str
    country_code: str | None = None
    suggested_external_team_id: str | None = None
    suggested_team_name: str | None = None
    score: float = 0.0


class RankingCatalogMatchRow(BaseModel):
    rank: int
    team_name: str
    country_code: str | None = None
    matched_external_team_id: str | None = None
    matched_team_name: str | None = None
    match_source: str | None = None  # override | auto | null
    suggested_external_team_id: str | None = None
    suggested_team_name: str | None = None
    score: float = 0.0


class AdminSyncTeamsAndRankingsRequest(BaseModel):
    season_year: int | None = None


class CompetitionTeamsQueryItem(BaseModel):
    code: str
    season_year: int


class CompetitionTeamsRequest(BaseModel):
    competitions: list[CompetitionTeamsQueryItem] = Field(default_factory=list)


class CompetitionTeamResponse(BaseModel):
    external_id: str
    name: str
    short_name: str | None = None
    crest_url: str | None = None
    competition_code: str


class CompetitionTeamsResponse(BaseModel):
    teams: list[CompetitionTeamResponse] = Field(default_factory=list)


class LeagueRankingStatusResponse(BaseModel):
    id: UUID
    key: str
    label: str
    source: str
    as_of: date | None = None
    locked: bool
    entry_count: int = 0
    unmatched_count: int = 0
    is_selected: bool = False
