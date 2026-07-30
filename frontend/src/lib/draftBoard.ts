import type { DraftPick, League, Manager, Pool } from "@/lib/types";
import { managerLabel } from "@/lib/types";

export type BoardCell =
  | { kind: "picked"; pick: DraftPick; onClock: boolean }
  | { kind: "empty"; onClock: boolean };

/** Managers sorted by draft_slot (1..N), then display label. */
export function orderedDraftMembers(
  league: Pick<League, "members"> | { members?: Manager[] | null },
): Manager[] {
  return [...(league.members || [])].sort((a, b) => {
    const as = a.draft_slot ?? 10_000;
    const bs = b.draft_slot ?? 10_000;
    if (as !== bs) return as - bs;
    return managerLabel(a).localeCompare(managerLabel(b));
  });
}

/** Total draft rounds = sum of roster slots across pools. */
export function totalRounds(pools: Pick<Pool, "slot_count">[] | null | undefined): number {
  if (!pools?.length) return 0;
  return pools.reduce((sum, p) => sum + (Number(p.slot_count) || 0), 0);
}

/**
 * Mirror backend `on_clock_member`: 1-based pick → round + column index
 * into managers ordered by draft_slot. Snake reverses even rounds.
 */
export function memberForPick(opts: {
  draftStyle: string;
  memberCount: number;
  pickNumber: number;
}): { roundNumber: number; columnIndex: number } {
  const n = opts.memberCount;
  if (n <= 0 || opts.pickNumber < 1) {
    return { roundNumber: 1, columnIndex: 0 };
  }
  const roundNumber = Math.floor((opts.pickNumber - 1) / n) + 1;
  let columnIndex = (opts.pickNumber - 1) % n;
  if (opts.draftStyle === "snake" && roundNumber % 2 === 0) {
    columnIndex = n - 1 - columnIndex;
  }
  return { roundNumber, columnIndex };
}

export function cellKey(roundNumber: number, memberId: string): string {
  return `${roundNumber}:${memberId}`;
}

/** Build a rounds×managers cell map from picks + on-clock state. */
export function buildBoardCells(opts: {
  orderedMembers: Manager[];
  picks: DraftPick[];
  draftStyle: string;
  currentPickNumber: number;
  currentRound: number;
  onClockMemberId?: string | null;
  totalRounds: number;
}): {
  rounds: number;
  cells: Map<string, BoardCell>;
  onClockKey: string | null;
} {
  const {
    orderedMembers,
    picks,
    draftStyle,
    currentPickNumber,
    currentRound,
    onClockMemberId,
    totalRounds: rosterRounds,
  } = opts;

  const maxPickRound = picks.reduce(
    (max, p) => Math.max(max, Number(p.round_number) || 0),
    0,
  );
  const rounds = Math.max(rosterRounds, maxPickRound, currentRound || 0, 1);
  const cells = new Map<string, BoardCell>();

  let onClockKey: string | null = null;
  if (onClockMemberId && orderedMembers.some((m) => m.id === onClockMemberId)) {
    const fromState = cellKey(currentRound || 1, onClockMemberId);
    onClockKey = fromState;
    if (currentPickNumber >= 1 && orderedMembers.length > 0) {
      const computed = memberForPick({
        draftStyle,
        memberCount: orderedMembers.length,
        pickNumber: currentPickNumber,
      });
      const computedMember = orderedMembers[computed.columnIndex];
      if (computedMember?.id === onClockMemberId) {
        onClockKey = cellKey(computed.roundNumber, onClockMemberId);
      }
    }
  }

  for (const pick of picks) {
    const memberId = pick.member_id ? String(pick.member_id) : "";
    const roundNumber = Number(pick.round_number) || 0;
    if (!memberId || roundNumber < 1) continue;
    const key = cellKey(roundNumber, memberId);
    cells.set(key, {
      kind: "picked",
      pick,
      onClock: key === onClockKey,
    });
  }

  for (let round = 1; round <= rounds; round++) {
    for (const m of orderedMembers) {
      const key = cellKey(round, m.id);
      if (cells.has(key)) continue;
      cells.set(key, {
        kind: "empty",
        onClock: key === onClockKey,
      });
    }
  }

  return { rounds, cells, onClockKey };
}
