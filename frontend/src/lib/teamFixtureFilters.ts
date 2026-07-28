import type { TeamFixture, UUID } from "@/lib/types";

/** Initial / incremental page size for recent & upcoming fixture lists. */
export const TEAM_FIXTURE_PAGE_SIZE = 5;

export function focusClubId(m: TeamFixture): UUID {
  return m.is_home ? m.home_team_id : m.away_team_id;
}

export function filterTeamFixtures(
  fixtures: TeamFixture[],
  {
    clubId = "",
    opponentMemberId = "",
  }: {
    clubId?: string;
    opponentMemberId?: string;
  },
): TeamFixture[] {
  return fixtures.filter((m) => {
    if (clubId && focusClubId(m) !== clubId) return false;
    if (opponentMemberId && m.opponent_owner?.member_id !== opponentMemberId) {
      return false;
    }
    return true;
  });
}
