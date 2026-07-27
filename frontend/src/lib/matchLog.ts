import { api } from "@/lib/api";
import type { MatchLogPage, UUID } from "@/lib/types";

export type MatchLogQuery = {
  section?: "upcoming" | "results";
  limit?: number;
  offset?: number;
  pool_id?: string;
  team_id?: string;
  member_id?: string;
  mine?: boolean;
  sort?: "kickoff" | "points";
  q?: string;
};

export function matchLogQueryString(params: MatchLogQuery): string {
  const qs = new URLSearchParams();
  if (params.section) qs.set("section", params.section);
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.pool_id) qs.set("pool_id", params.pool_id);
  if (params.team_id) qs.set("team_id", params.team_id);
  if (params.member_id) qs.set("member_id", params.member_id);
  if (params.mine) qs.set("mine", "true");
  if (params.sort) qs.set("sort", params.sort);
  if (params.q) qs.set("q", params.q);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export function fetchMatchLogPage(
  leagueId: UUID,
  params: MatchLogQuery = {},
): Promise<MatchLogPage> {
  return api<MatchLogPage>(
    `/leagues/${leagueId}/match-log${matchLogQueryString(params)}`,
  );
}
