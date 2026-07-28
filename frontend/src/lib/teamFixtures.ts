import { api } from "@/lib/api";
import type { TeamFixturePage, UUID } from "@/lib/types";

export const TEAM_FIXTURE_PAGE_SIZE = 5;

export type TeamFixtureSection = "recent" | "upcoming";

export type MemberFixturesQuery = {
  section: TeamFixtureSection;
  limit?: number;
  offset?: number;
  club_id?: string;
  opponent_member_id?: string;
};

export type TeamFixturesQuery = {
  section: TeamFixtureSection;
  limit?: number;
  offset?: number;
  opponent_member_id?: string;
};

function qs(
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function fetchMemberFixturesPage(
  leagueId: UUID,
  memberId: UUID,
  params: MemberFixturesQuery,
): Promise<TeamFixturePage> {
  return api<TeamFixturePage>(
    `/leagues/${leagueId}/members/${memberId}/fixtures${qs({
      section: params.section,
      limit: params.limit ?? TEAM_FIXTURE_PAGE_SIZE,
      offset: params.offset ?? 0,
      club_id: params.club_id,
      opponent_member_id: params.opponent_member_id,
    })}`,
  );
}

export function fetchTeamFixturesPage(
  leagueId: UUID,
  teamId: UUID,
  params: TeamFixturesQuery,
): Promise<TeamFixturePage> {
  return api<TeamFixturePage>(
    `/leagues/${leagueId}/teams/${teamId}/fixtures${qs({
      section: params.section,
      limit: params.limit ?? TEAM_FIXTURE_PAGE_SIZE,
      offset: params.offset ?? 0,
      opponent_member_id: params.opponent_member_id,
    })}`,
  );
}
