from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _public_id_column() -> Mapped[UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        unique=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    auth_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), unique=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompetitionTemplate(Base):
    __tablename__ = "competition_templates"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    key: Mapped[str] = mapped_column(Text, unique=True)
    label: Mapped[str] = mapped_column(Text)
    draft_style: Mapped[str] = mapped_column(Text, default="linear")
    preassign_mode: Mapped[str] = mapped_column(Text, default="none")
    result_points: Mapped[dict] = mapped_column(JSONB)
    upset_rules: Mapped[dict] = mapped_column(JSONB)
    leaderboard_phases: Mapped[list] = mapped_column(JSONB)
    leaderboard_tiebreaks: Mapped[list] = mapped_column(JSONB)
    buy_in: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payouts: Mapped[list] = mapped_column(JSONB)
    roster_slots: Mapped[list] = mapped_column(JSONB)
    pool_definitions: Mapped[list] = mapped_column(JSONB)
    bonus_types: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class League(Base):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    template_id: Mapped[int | None] = mapped_column(ForeignKey("competition_templates.id"))
    name: Mapped[str] = mapped_column(Text)
    season_label: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pre_draft")
    draft_style: Mapped[str] = mapped_column(Text, default="linear")
    preassign_mode: Mapped[str] = mapped_column(Text, default="none")
    result_points: Mapped[dict] = mapped_column(JSONB)
    upset_rules: Mapped[dict] = mapped_column(JSONB)
    leaderboard_phases: Mapped[list] = mapped_column(JSONB)
    leaderboard_tiebreaks: Mapped[list] = mapped_column(JSONB)
    buy_in: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payouts: Mapped[list] = mapped_column(JSONB)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    scheduled_start_date: Mapped[date | None] = mapped_column(Date)
    scheduled_end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["LeagueMember"]] = relationship(back_populates="league")
    pools: Mapped[list["TeamPool"]] = relationship(back_populates="league")


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (UniqueConstraint("league_id", "email"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(Text)
    token: Mapped[str | None] = mapped_column(Text, unique=True)
    is_commissioner: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_slot: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeagueMember(Base):
    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_id", "profile_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    is_commissioner: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_slot: Mapped[int | None] = mapped_column(Integer)
    team_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="members")
    profile: Mapped[Profile] = relationship()


class TeamPool(Base):
    __tablename__ = "team_pools"
    __table_args__ = (UniqueConstraint("league_id", "key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    scores_match_results: Mapped[bool] = mapped_column(Boolean, default=True)
    slot_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    tie_break_order: Mapped[list] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(Text, default="football-data.org")
    competition_code: Mapped[str | None] = mapped_column(Text)
    season_year: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    league: Mapped[League] = relationship(back_populates="pools")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    provider: Mapped[str] = mapped_column(Text, default="football-data.org")
    external_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    tla: Mapped[str | None] = mapped_column(Text)
    crest_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PoolTeam(Base):
    __tablename__ = "pool_teams"
    __table_args__ = (UniqueConstraint("pool_id", "team_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    pool_id: Mapped[int] = mapped_column(ForeignKey("team_pools.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RosterEntry(Base):
    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("league_id", "team_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("league_members.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    pool_id: Mapped[int] = mapped_column(ForeignKey("team_pools.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DraftState(Base):
    __tablename__ = "draft_state"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), unique=True)
    current_pick_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DraftPick(Base):
    __tablename__ = "draft_picks"
    __table_args__ = (UniqueConstraint("league_id", "pick_number"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    pick_number: Mapped[int] = mapped_column(Integer)
    round_number: Mapped[int] = mapped_column(Integer)
    member_id: Mapped[int] = mapped_column(ForeignKey("league_members.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    pool_id: Mapped[int] = mapped_column(ForeignKey("team_pools.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("league_id", "provider", "external_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    pool_id: Mapped[int] = mapped_column(ForeignKey("team_pools.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text, default="football-data.org")
    external_id: Mapped[str] = mapped_column(Text)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="SCHEDULED")
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    scheduled_matchweek: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StandingsSnapshot(Base):
    __tablename__ = "standings_snapshots"
    __table_args__ = (UniqueConstraint("pool_id", "kickoff_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    pool_id: Mapped[int] = mapped_column(ForeignKey("team_pools.id", ondelete="CASCADE"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rows: Mapped[list["StandingsSnapshotRow"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class StandingsSnapshotRow(Base):
    __tablename__ = "standings_snapshot_rows"
    __table_args__ = (UniqueConstraint("snapshot_id", "team_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("standings_snapshots.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    played: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goal_difference: Mapped[int] = mapped_column(Integer, default=0)

    snapshot: Mapped["StandingsSnapshot"] = relationship(back_populates="rows")


class RankingList(Base):
    __tablename__ = "ranking_lists"
    __table_args__ = (UniqueConstraint("league_id", "key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    as_of: Mapped[date | None] = mapped_column(Date)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamRanking(Base):
    __tablename__ = "team_rankings"
    __table_args__ = (UniqueConstraint("ranking_list_id", "team_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    ranking_list_id: Mapped[int] = mapped_column(ForeignKey("ranking_lists.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)


class BonusType(Base):
    __tablename__ = "bonus_types"
    __table_args__ = (UniqueConstraint("league_id", "key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    default_points: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    include_in_phases: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManualBonus(Base):
    __tablename__ = "manual_bonuses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    bonus_type_id: Mapped[int] = mapped_column(ForeignKey("bonus_types.id", ondelete="CASCADE"))
    points: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoringEvent(Base):
    __tablename__ = "scoring_events"
    __table_args__ = (UniqueConstraint("match_id", "team_id", "event_type"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    scheduled_matchweek: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    points: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DraftIdempotencyKey(Base):
    __tablename__ = "draft_idempotency_keys"
    __table_args__ = (UniqueConstraint("league_id", "member_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("league_members.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(Text)
    pick_id: Mapped[int | None] = mapped_column(ForeignKey("draft_picks.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncStatus(Base):
    __tablename__ = "sync_status"
    __table_args__ = (UniqueConstraint("league_id", "provider"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = _public_id_column()
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text, default="football-data.org")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    in_progress: Mapped[bool] = mapped_column(Boolean, default=False)
    in_progress_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requests_available_minute: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_summary: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
