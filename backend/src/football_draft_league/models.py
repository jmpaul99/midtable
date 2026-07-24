from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from football_draft_league.db import Base, EntityMixin


class CompetitionTemplate(EntityMixin, Base):
    __tablename__ = "competition_templates"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(40), default="football-data.org")
    provider_competition_code: Mapped[str] = mapped_column(String(40))
    default_team_count: Mapped[int] = mapped_column(Integer)
    default_roster_size: Mapped[int] = mapped_column(Integer)
    pool_definitions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    scoring_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tiebreak_config: Mapped[list[str]] = mapped_column(JSONB, default=list)
    payout_config: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    draft_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Competition(EntityMixin, Base):
    __tablename__ = "competitions"

    template_id: Mapped[int] = mapped_column(ForeignKey("competition_templates.id"), index=True)
    season: Mapped[str] = mapped_column(String(20))
    provider_competition_id: Mapped[str | None] = mapped_column(String(80))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    provider_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    template: Mapped[CompetitionTemplate] = relationship()


class League(EntityMixin, Base):
    __tablename__ = "leagues"

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    owner_profile_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="setup")
    visibility: Mapped[str] = mapped_column(String(24), default="private")
    max_members: Mapped[int] = mapped_column(Integer)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    provider_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    competition: Mapped[Competition] = relationship()
    pools: Mapped[list["Pool"]] = relationship(back_populates="league")


class Pool(EntityMixin, Base):
    __tablename__ = "pools"

    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    definition_key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    ordinal: Mapped[int] = mapped_column(Integer)
    roster_size: Mapped[int] = mapped_column(Integer)
    draft_order: Mapped[list[str]] = mapped_column(JSONB, default=list)
    provider_competition_code: Mapped[str | None] = mapped_column(String(40))
    scoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    provider_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    league: Mapped[League] = relationship(back_populates="pools")


class Team(EntityMixin, Base):
    __tablename__ = "teams"

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    provider_team_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    short_name: Mapped[str | None] = mapped_column(String(80))
    tla: Mapped[str | None] = mapped_column(String(10))
    crest_url: Mapped[str | None] = mapped_column(Text)


class Match(EntityMixin, Base):
    __tablename__ = "matches"

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    provider_match_id: Mapped[str] = mapped_column(String(80), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    winner: Mapped[str | None] = mapped_column(String(10))
    result_version: Mapped[int] = mapped_column(Integer, default=1)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScoringEvent(EntityMixin, Base):
    __tablename__ = "scoring_events"

    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    roster_entry_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    league_member_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    snapshot_id: Mapped[int] = mapped_column(BigInteger)
    phase: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(40))
    points: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    source_result_version: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
