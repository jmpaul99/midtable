from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PoolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    provider_competition_code: str
    slots_per_member: int = Field(gt=0)
    slot_label: str


class DraftRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: Literal["linear"] = "linear"
    pick_clock_seconds: None = None
    auto_pick: Literal[False] = False
    pause_between_rounds_seconds: int = Field(default=0, ge=0)


class PremierLeagueTemplateDefaults(BaseModel):
    model_config = ConfigDict(frozen=True)

    roster_size: int = 6
    pool_definitions: tuple[PoolDefinition, ...] = (
        PoolDefinition(
            key="premier_league",
            name="Premier League",
            provider_competition_code="PL",
            slots_per_member=5,
            slot_label="Premier League team",
        ),
        PoolDefinition(
            key="championship",
            name="Championship",
            provider_competition_code="ELC",
            slots_per_member=1,
            slot_label="Championship team",
        ),
    )
    draft: DraftRules = DraftRules()

    @model_validator(mode="after")
    def slots_match_roster_size(self) -> "PremierLeagueTemplateDefaults":
        if sum(pool.slots_per_member for pool in self.pool_definitions) != self.roster_size:
            raise ValueError("pool slots must add up to roster_size")
        return self


PL_TEMPLATE_DEFAULTS = PremierLeagueTemplateDefaults()
