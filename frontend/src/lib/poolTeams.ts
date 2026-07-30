import { api } from "@/lib/api";
import { humanizeKey } from "@/components/settings/types";
import type { PoolTeam, UUID } from "@/lib/types";

export type AnnotatedPoolTeam = PoolTeam & {
  pool_id: UUID;
  pool_label: string;
};

type PoolRef = { id: string; label?: string | null; key?: string | null };

/** Fetch teams for each pool; optionally annotate with pool_id / pool_label. */
export async function fetchPoolTeams(
  leagueId: string,
  pools: PoolRef[],
  opts?: { annotatePool?: false; signal?: AbortSignal },
): Promise<PoolTeam[]>;
export async function fetchPoolTeams(
  leagueId: string,
  pools: PoolRef[],
  opts: { annotatePool: true; signal?: AbortSignal },
): Promise<AnnotatedPoolTeam[]>;
export async function fetchPoolTeams(
  leagueId: string,
  pools: PoolRef[],
  opts?: { annotatePool?: boolean; signal?: AbortSignal },
): Promise<PoolTeam[] | AnnotatedPoolTeam[]> {
  const annotate = opts?.annotatePool === true;
  const signal = opts?.signal;
  const lists = await Promise.all(
    pools.map(async (p) => {
      try {
        const teams = await api<PoolTeam[]>(`/leagues/${leagueId}/pools/${p.id}/teams`, {
          signal,
        });
        if (!annotate) return teams;
        return teams.map(
          (t): AnnotatedPoolTeam => ({
            ...t,
            pool_id: p.id,
            pool_label:
              (p.label || "").trim() || (p.key ? humanizeKey(p.key) : ""),
          }),
        );
      } catch {
        return [];
      }
    }),
  );
  return lists.flat();
}

/** Fetch pool teams keyed by pool id (empty list on per-pool failure). */
export async function fetchPoolTeamsByPoolId(
  leagueId: string,
  pools: PoolRef[],
  opts?: { signal?: AbortSignal; safe?: <T>(p: Promise<T>, fallback: T) => Promise<T> },
): Promise<Record<string, PoolTeam[]>> {
  const signal = opts?.signal;
  const safe = opts?.safe;
  const entries = await Promise.all(
    pools.map(async (p) => {
      const request = api<PoolTeam[]>(`/leagues/${leagueId}/pools/${p.id}/teams`, { signal });
      const teams = safe ? await safe(request, []) : await request.catch(() => [] as PoolTeam[]);
      return [p.id, teams] as const;
    }),
  );
  return Object.fromEntries(entries);
}
