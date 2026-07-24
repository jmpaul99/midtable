begin;

insert into public.competition_templates (
  code,
  name,
  provider,
  provider_competition_code,
  default_team_count,
  default_roster_size,
  pool_definitions,
  scoring_config,
  tiebreak_config,
  draft_config,
  is_active
)
values (
  'PL',
  'Premier League',
  'football-data.org',
  'PL',
  20,
  6,
  '[
    {
      "key": "premier_league",
      "name": "Premier League",
      "provider_competition_code": "PL",
      "slots_per_member": 5,
      "slot_label": "Premier League team"
    },
    {
      "key": "championship",
      "name": "Championship",
      "provider_competition_code": "ELC",
      "slots_per_member": 1,
      "slot_label": "Championship team"
    }
  ]'::jsonb,
  '{
    "result_points": {"win": 3, "draw": 1, "loss": 0},
    "upset": {
      "minimum_matches_played": 8,
      "thresholds": [
        {
          "key": "minor_upset",
          "result": "win",
          "minimum_position_gap": 5,
          "maximum_position_gap": 9,
          "bonus": 1
        },
        {
          "key": "major_upset",
          "result": "win",
          "minimum_position_gap": 10,
          "maximum_position_gap": null,
          "bonus": 3
        },
        {
          "key": "major_upset_draw",
          "result": "draw",
          "minimum_position_gap": 10,
          "maximum_position_gap": null,
          "bonus": 1
        }
      ]
    },
    "phases": [
      {
        "name": "mw1-19",
        "first_matchweek": 1,
        "last_matchweek": 19
      }
    ],
    "manual_bonus_defaults": {
      "winner": 12,
      "champions_league": 9,
      "other_europe": 6,
      "championship_promotion": 20,
      "relegation": -10
    },
    "table_tiebreaks": [
      "points",
      "goal_difference",
      "goals_for",
      "name"
    ]
  }'::jsonb,
  '[
    {
      "metric": "total_points",
      "direction": "desc"
    },
    {
      "metric": "event_points",
      "event_types": ["minor_upset", "major_upset", "major_upset_draw"],
      "direction": "desc"
    },
    {
      "metric": "event_count",
      "event_types": ["win"],
      "direction": "desc"
    }
  ]'::jsonb,
  '{
    "format": "linear",
    "pick_clock_seconds": null,
    "auto_pick": false,
    "pause_between_rounds_seconds": 0
  }'::jsonb,
  true
)
on conflict (code) do update set
  name = excluded.name,
  provider = excluded.provider,
  provider_competition_code = excluded.provider_competition_code,
  default_team_count = excluded.default_team_count,
  default_roster_size = excluded.default_roster_size,
  pool_definitions = excluded.pool_definitions,
  scoring_config = excluded.scoring_config,
  tiebreak_config = excluded.tiebreak_config,
  draft_config = excluded.draft_config,
  is_active = excluded.is_active,
  updated_at = now();

commit;
