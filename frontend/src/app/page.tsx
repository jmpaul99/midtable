"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { LeagueSummary } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "@/components/ui/State";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";

function ordinal(n: number): string {
  const abs = Math.abs(n);
  const mod100 = abs % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (abs % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

function leagueMetaLabel(league: LeagueSummary): string {
  const season = league.season_label || league.season || "Season";
  const count = league.member_count ?? 0;
  const preScoring =
    !league.has_scored ||
    league.status === "pre_draft" ||
    league.status === "drafting";

  if (preScoring) {
    if (league.my_draft_slot != null && count > 0) {
      return `${season} · Draft ${ordinal(league.my_draft_slot)} of ${count}`;
    }
    if (count > 0) {
      return `${season} · Draft order TBD · ${count} managers`;
    }
    return season;
  }

  if (league.my_rank != null && count > 0) {
    const pts =
      league.my_points != null ? ` · ${formatNumber(league.my_points)} pts` : "";
    return `${season} · ${ordinal(league.my_rank)} of ${count}${pts}`;
  }
  if (count > 0) {
    return `${season} · ${count} managers`;
  }
  return season;
}

export default function HomePage() {
  return (
    <RequireAuth>
      <LeagueList />
    </RequireAuth>
  );
}

function LeagueList() {
  const { isAdmin } = useAuth();
  const [leagues, setLeagues] = useState<LeagueSummary[]>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    api<LeagueSummary[]>("/leagues")
      .then(setLeagues)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader title="Midtable" />

      {error && <ErrorState error={error} retry={load} />}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg sm:text-xl">Your leagues</h2>

        {!leagues ? (
          <Loading label="Loading leagues" />
        ) : !leagues.length ? (
          <Empty title="No leagues yet">
            <p>
              {isAdmin
                ? "Use Create a league in the nav to start from a template, or accept an invite link."
                : "Accept an invite link to join a league."}
            </p>
          </Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {leagues.map((league) => (
              <li key={league.id}>
                <Link
                  href={`/leagues/${league.id}`}
                  className="block rounded-xl border border-line bg-surface p-4 shadow-soft transition hover:border-brand/40 active:scale-[0.99]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <strong className="min-w-0 flex-1 truncate text-base">{league.name}</strong>
                    <span className="shrink-0">
                      <Status value={league.status} />
                    </span>
                  </div>
                  <Muted className="mt-1">{leagueMetaLabel(league)}</Muted>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Stack>
  );
}
