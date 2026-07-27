"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import { fetchMatchLogPage } from "@/lib/matchLog";
import { fetchPoolTeams } from "@/lib/poolTeams";
import type { League, MatchLogRow, PoolTeam, UUID } from "@/lib/types";
import { managerOptionLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Eyebrow, Stack } from "@/components/ui/Card";
import { Select } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { ChoiceToggle } from "@/components/ui/ChoiceToggle";
import { PoolFilterSelect } from "@/components/ui/PoolFilterSelect";
import { MatchLogCard } from "./MatchLogCard";

type ViewMode = "recent" | "upcoming";

type ListState = {
  items: MatchLogRow[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  offset: number;
};

const emptyList = (): ListState => ({
  items: [],
  hasMore: false,
  loading: true,
  loadingMore: false,
  error: "",
  offset: 0,
});

const VIEW_OPTIONS = [
  { id: "recent", label: "Recent" },
  { id: "upcoming", label: "Upcoming" },
] as const;

function sectionParam(view: ViewMode): "upcoming" | "results" {
  return view === "upcoming" ? "upcoming" : "results";
}

function emptyTitleFor(view: ViewMode): string {
  return view === "upcoming" ? "No upcoming fixtures" : "No scored matches yet";
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
  section?: "upcoming" | "results";
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
  const [view, setView] = useState<ViewMode>("recent");
  const [poolTeams, setPoolTeams] = useState<PoolTeam[]>([]);
  const [list, setList] = useState<ListState>(emptyList);
  const fellBackToUpcoming = useRef(false);
  const fetchGeneration = useRef(0);

  const filterKey = `${poolId}|${teamId}|${memberId}|${view}`;

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
    const teams = await fetchPoolTeams(league.id, pools);
    const byId = new Map<string, PoolTeam>();
    for (const t of teams) byId.set(t.id, t);
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

  const fetchMatches = useCallback(
    async (offset: number, append: boolean, viewMode: ViewMode) => {
      const generation = ++fetchGeneration.current;
      setList((prev) => ({
        ...prev,
        loading: !append && offset === 0,
        loadingMore: append,
        error: "",
      }));
      try {
        const page = await fetchMatchLogPage(leagueId, {
          section: sectionParam(viewMode),
          limit: pageSize,
          offset,
          pool_id: poolId || undefined,
          team_id: teamId || undefined,
          member_id: memberId || undefined,
        });
        if (generation !== fetchGeneration.current) return;
        // Only auto-switch Recent → Upcoming on the unfiltered first load so
        // legitimate empty filter results still show "No scored matches yet".
        if (
          !compact &&
          !append &&
          viewMode === "recent" &&
          page.items.length === 0 &&
          !poolId &&
          !teamId &&
          !memberId &&
          !fellBackToUpcoming.current
        ) {
          fellBackToUpcoming.current = true;
          setView("upcoming");
          return;
        }
        setList((prev) => ({
          items: append ? [...prev.items, ...page.items] : page.items,
          hasMore: page.has_more,
          loading: false,
          loadingMore: false,
          error: "",
          offset: offset + page.items.length,
        }));
      } catch (e) {
        if (generation !== fetchGeneration.current) return;
        setList((prev) => ({
          ...prev,
          loading: false,
          loadingMore: false,
          error: errorMessage(e),
          ...(append ? {} : { items: [], hasMore: false, offset: 0 }),
        }));
      }
    },
    [compact, leagueId, pageSize, poolId, teamId, memberId],
  );

  useEffect(() => {
    if (compact) {
      const compactView: ViewMode =
        compactSection === "upcoming" ? "upcoming" : "recent";
      void fetchMatches(0, false, compactView);
      return;
    }
    setList(emptyList());
    void fetchMatches(0, false, view);
    // filterKey forces refetch when filters/view change
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional filterKey trigger
  }, [compact, compactSection, filterKey, fetchMatches]);

  if (compact) {
    if (list.error) return <ErrorState error={list.error} />;
    if (list.loading) return <Loading label="Loading match log" />;
    if (!list.items.length) return <Empty title="No matches synced yet" />;
    return (
      <ul className="flex flex-col gap-2">
        {list.items.map((m) => (
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

  const selectClass =
    "min-h-9 w-auto min-w-0 flex-1 basis-[9.5rem] rounded-lg px-2.5 py-1.5 text-sm sm:flex-none sm:basis-auto";

  return (
    <Card className="animate-in min-w-0 overflow-hidden">
      <Stack>
        <div>
          <Eyebrow>Fixtures</Eyebrow>
          <h2>Match log</h2>
        </div>
        <ChoiceToggle
          label="Match view"
          value={view}
          options={VIEW_OPTIONS}
          onChange={setView}
        />
        <div className="flex flex-wrap items-center gap-2">
          {showCompetitionFilter && (
            <PoolFilterSelect
              aria-label="Competition"
              className={selectClass}
              pools={scoringPools}
              value={poolId}
              onChange={(next) => {
                setPoolId(next);
                setTeamId("");
              }}
            />
          )}
          <Select
            aria-label="Club"
            className={selectClass}
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
          >
            <option value="">All clubs</option>
            {poolTeams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Owner"
            className={selectClass}
            value={memberId}
            onChange={(e) => setMemberId(e.target.value)}
          >
            <option value="">All managers</option>
            {league.members.map((m) => (
              <option key={m.id} value={m.id}>
                {managerOptionLabel(m)}
              </option>
            ))}
          </Select>
        </div>
        {list.error && <ErrorState error={list.error} />}
        {list.loading ? (
          <Loading label="Loading matches" />
        ) : !list.items.length ? (
          <Empty title={emptyTitleFor(view)} />
        ) : (
          <>
            <ul className="flex flex-col gap-2">
              {list.items.map((m) => (
                <li key={m.id}>
                  <MatchLogCard
                    leagueId={leagueId}
                    match={m}
                    showPoolLabel={multiPool}
                  />
                </li>
              ))}
            </ul>
            {list.hasMore && (
              <div className="flex justify-start">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={list.loadingMore}
                  onClick={() => void fetchMatches(list.offset, true, view)}
                >
                  {list.loadingMore ? "Loading…" : "Load more"}
                </Button>
              </div>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}
