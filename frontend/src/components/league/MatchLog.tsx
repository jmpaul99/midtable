"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { League, MatchLogPage, MatchLogRow, PoolTeam, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { ChoiceToggle } from "@/components/ui/ChoiceToggle";
import { MatchLogCard } from "./MatchLogCard";

type Section = "upcoming" | "results";
type SortMode = "kickoff" | "points";

type SectionState = {
  items: MatchLogRow[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  offset: number;
};

const emptySection = (): SectionState => ({
  items: [],
  hasMore: false,
  loading: true,
  loadingMore: false,
  error: "",
  offset: 0,
});

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    q.set(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

function MatchSection({
  leagueId,
  title,
  eyebrow,
  emptyTitle,
  state,
  showPoolLabel,
  onLoadMore,
}: {
  leagueId: UUID;
  title: string;
  eyebrow: string;
  emptyTitle: string;
  state: SectionState;
  showPoolLabel: boolean;
  onLoadMore: () => void;
}) {
  return (
    <Card className="min-w-0 overflow-hidden">
      <Stack>
        <div>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h2>{title}</h2>
        </div>
        {state.error && <ErrorState error={state.error} />}
        {state.loading ? (
          <Loading label={`Loading ${title.toLowerCase()}`} />
        ) : !state.items.length ? (
          <Empty title={emptyTitle} />
        ) : (
          <>
            <ul className="flex flex-col gap-2">
              {state.items.map((m) => (
                <li key={m.id}>
                  <MatchLogCard
                    leagueId={leagueId}
                    match={m}
                    showPoolLabel={showPoolLabel}
                  />
                </li>
              ))}
            </ul>
            {state.hasMore && (
              <div className="flex justify-start">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={state.loadingMore}
                  onClick={onLoadMore}
                >
                  {state.loadingMore ? "Loading…" : "Load more"}
                </Button>
              </div>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}

export function MatchLog({
  leagueId,
  league,
  limit,
  compact = false,
  section: compactSection,
}: {
  leagueId: UUID;
  league?: League;
  /** Compact/stats mode: page size (default 10). Full page uses 20. */
  limit?: number;
  compact?: boolean;
  /** Compact mode section; defaults to results. */
  section?: Section;
}) {
  const pageSize = limit ?? (compact ? 10 : 20);
  const scoringPools = useMemo(
    () => (league?.pools || []).filter((p) => p.scores_match_results),
    [league?.pools],
  );
  const multiPool = scoringPools.length > 1;
  const showCompetitionFilter = multiPool;

  const [poolId, setPoolId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [mine, setMine] = useState(false);
  const [sort, setSort] = useState<SortMode>("kickoff");
  const [poolTeams, setPoolTeams] = useState<PoolTeam[]>([]);
  const [upcoming, setUpcoming] = useState<SectionState>(emptySection);
  const [results, setResults] = useState<SectionState>(emptySection);

  const filterKey = `${poolId}|${teamId}|${memberId}|${mine}|${sort}`;

  const loadClubs = useCallback(async () => {
    if (!league) {
      setPoolTeams([]);
      return;
    }
    const pools = poolId
      ? scoringPools.filter((p) => p.id === poolId)
      : scoringPools;
    if (!pools.length) {
      setPoolTeams([]);
      return;
    }
    const entries = await Promise.all(
      pools.map(async (p) => {
        try {
          return await api<PoolTeam[]>(`/leagues/${league.id}/pools/${p.id}/teams`);
        } catch {
          return [] as PoolTeam[];
        }
      }),
    );
    const byId = new Map<string, PoolTeam>();
    for (const list of entries) {
      for (const t of list) byId.set(t.id, t);
    }
    setPoolTeams(
      [...byId.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" })),
    );
  }, [league, poolId, scoringPools]);

  useEffect(() => {
    void loadClubs();
  }, [loadClubs]);

  useEffect(() => {
    if (teamId && !poolTeams.some((t) => t.id === teamId)) {
      setTeamId("");
    }
  }, [poolTeams, teamId]);

  const fetchSection = useCallback(
    async (
      section: Section,
      offset: number,
      append: boolean,
    ) => {
      const setState = section === "upcoming" ? setUpcoming : setResults;
      setState((prev) => ({
        ...prev,
        loading: !append && offset === 0,
        loadingMore: append,
        error: "",
      }));
      try {
        const qs = buildQuery({
          section,
          limit: pageSize,
          offset,
          pool_id: poolId || undefined,
          team_id: teamId || undefined,
          member_id: mine ? undefined : memberId || undefined,
          mine: mine || undefined,
          sort: section === "results" ? sort : "kickoff",
        });
        const page = await api<MatchLogPage>(`/leagues/${leagueId}/match-log${qs}`);
        setState((prev) => ({
          items: append ? [...prev.items, ...page.items] : page.items,
          hasMore: page.has_more,
          loading: false,
          loadingMore: false,
          error: "",
          offset: offset + page.items.length,
        }));
      } catch (e) {
        setState((prev) => ({
          ...prev,
          loading: false,
          loadingMore: false,
          error: errorMessage(e),
          ...(append ? {} : { items: [], hasMore: false, offset: 0 }),
        }));
      }
    },
    [leagueId, pageSize, poolId, teamId, memberId, mine, sort],
  );

  useEffect(() => {
    if (compact) {
      void fetchSection(compactSection ?? "results", 0, false);
      return;
    }
    setUpcoming(emptySection());
    setResults(emptySection());
    void fetchSection("upcoming", 0, false);
    void fetchSection("results", 0, false);
    // filterKey forces refetch when filters change
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional filterKey trigger
  }, [compact, compactSection, filterKey, fetchSection]);

  if (compact) {
    const state = (compactSection ?? "results") === "upcoming" ? upcoming : results;
    if (state.error) return <ErrorState error={state.error} />;
    if (state.loading) return <Loading label="Loading match log" />;
    if (!state.items.length) return <Empty title="No matches synced yet" />;
    return (
      <ul className="flex flex-col gap-2">
        {state.items.map((m) => (
          <li key={m.id}>
            <MatchLogCard leagueId={leagueId} match={m} showPoolLabel={multiPool} />
          </li>
        ))}
      </ul>
    );
  }

  if (!league) {
    return <ErrorState error="League context required for match log." />;
  }

  return (
    <Stack gap="md" className="animate-in">
      <Card className="min-w-0 overflow-hidden">
        <Stack gap="sm">
          <div>
            <Eyebrow>Fixtures</Eyebrow>
            <h2>Match log</h2>
            <Muted className="mt-1 text-sm">
              Browse upcoming fixtures and scored results. Filters apply to both lists.
            </Muted>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {showCompetitionFilter && (
              <Label>
                Competition
                <Select
                  value={poolId}
                  onChange={(e) => {
                    setPoolId(e.target.value);
                    setTeamId("");
                  }}
                >
                  <option value="">All competitions</option>
                  {scoringPools.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </Label>
            )}
            <Label>
              Club
              <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">All clubs</option>
                {poolTeams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Label>
            <Label>
              Owner
              <Select
                value={mine ? "" : memberId}
                disabled={mine}
                onChange={(e) => setMemberId(e.target.value)}
              >
                <option value="">All managers</option>
                {league.members.map((m) => {
                  const team = m.team_name?.trim() || managerLabel(m);
                  const person = m.display_name?.trim() || m.email || null;
                  const label = person && person !== team ? `${team} (${person})` : team;
                  return (
                    <option key={m.id} value={m.id}>
                      {label}
                    </option>
                  );
                })}
              </Select>
            </Label>
            <div className="flex flex-col gap-1.5 sm:col-span-2 lg:col-span-1">
              <span className="text-sm font-semibold text-muted">My clubs</span>
              <ChoiceToggle
                label="My clubs"
                value={mine ? "mine" : "all"}
                options={
                  [
                    { id: "all", label: "All" },
                    { id: "mine", label: "Mine" },
                  ] as const
                }
                onChange={(value) => {
                  const next = value === "mine";
                  setMine(next);
                  if (next) setMemberId("");
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-semibold text-muted">Sort</span>
              <ChoiceToggle
                label="Sort"
                value={sort}
                options={
                  [
                    { id: "kickoff", label: "Kickoff" },
                    { id: "points", label: "Fantasy points" },
                  ] as const
                }
                onChange={setSort}
              />
              <Muted className="text-[11px] leading-snug">
                Fantasy points sorts Results only; Upcoming stays by kickoff.
              </Muted>
            </div>
          </div>
        </Stack>
      </Card>

      <MatchSection
        leagueId={leagueId}
        title="Upcoming"
        eyebrow="Schedule"
        emptyTitle="No upcoming fixtures"
        state={upcoming}
        showPoolLabel={multiPool}
        onLoadMore={() => void fetchSection("upcoming", upcoming.offset, true)}
      />
      <MatchSection
        leagueId={leagueId}
        title="Results"
        eyebrow="Scored"
        emptyTitle="No scored matches yet"
        state={results}
        showPoolLabel={multiPool}
        onLoadMore={() => void fetchSection("results", results.offset, true)}
      />
    </Stack>
  );
}
