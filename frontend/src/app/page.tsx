"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { LeagueSummary, Manager, PendingInvite } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "@/components/ui/State";
import { Muted, Stack } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { PlusIcon } from "@/components/ui/icons";
import { MidtableLogo } from "@/components/MidtableLogo";
import { LandingPage } from "@/components/LandingPage";
import { useToast } from "@/components/ui/ToastProvider";

function safeNext(value: string | null): string | null {
  if (!value?.startsWith("/") || value.startsWith("//")) return null;
  return value;
}

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
  const season = league.season_label || "Season";
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

function inviteMetaLabel(invite: PendingInvite): string {
  const season = invite.season_label || "Season";
  const role = invite.role === "commissioner" ? "Commissioner" : "Manager";
  if (invite.draft_slot != null) {
    return `${season} · ${role} · Draft ${ordinal(invite.draft_slot)}`;
  }
  return `${season} · ${role}`;
}

export default function HomePage() {
  return (
    <Suspense fallback={<Loading label="Checking your session" />}>
      <HomeContent />
    </Suspense>
  );
}

function isJoinOrInviteNext(next: string) {
  return (
    next === "/join" ||
    next.startsWith("/join?") ||
    next.startsWith("/join/") ||
    next === "/invites/accept" ||
    next.startsWith("/invites/accept?") ||
    next.startsWith("/invites/accept/")
  );
}

function HomeContent() {
  const { session, loading } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const next = safeNext(search.get("next"));

  useEffect(() => {
    if (loading) return;
    // Legacy join/invite `/?next=…` bookmarks should still open sign-in directly.
    if (!session && next && isJoinOrInviteNext(next)) {
      router.replace(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    if (!session || !next) return;
    router.replace(next);
  }, [loading, session, next, router]);

  if (loading) {
    return <Loading label="Checking your session" />;
  }

  if (!session) {
    if (next && isJoinOrInviteNext(next)) {
      return <Loading label="Opening sign-in" />;
    }
    return <LandingPage />;
  }

  if (next) {
    return <Loading label="Opening your page" />;
  }

  return <LeagueList />;
}

function LeagueList() {
  const router = useRouter();
  const { toast } = useToast();
  const [leagues, setLeagues] = useState<LeagueSummary[]>();
  const [invites, setInvites] = useState<PendingInvite[]>();
  const [error, setError] = useState("");
  const [acceptingId, setAcceptingId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError("");
    Promise.all([
      api<LeagueSummary[]>("/leagues"),
      api<PendingInvite[]>("/invites/pending"),
    ])
      .then(([leagueRows, inviteRows]) => {
        setLeagues(leagueRows);
        setInvites(inviteRows);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function acceptInvite(invite: PendingInvite) {
    if (!invite.token) return;
    setAcceptingId(invite.id);
    try {
      const out = await api<Manager & { league_id: string }>(
        "/invites/accept",
        json("POST", { token: invite.token }),
      );
      router.push(`/leagues/${out.league_id}`);
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      setAcceptingId(null);
    }
  }

  return (
    <Stack gap="lg" className="animate-in">
      <div className="flex justify-center">
        <MidtableLogo className="h-32 w-auto sm:h-40 md:h-48" />
      </div>

      {error && <ErrorState error={error} retry={load} />}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg sm:text-xl">Your leagues</h2>
          <Link
            href="/leagues/new"
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-brand transition hover:bg-brand/10 active:scale-[0.98]"
            aria-label="Create a league"
            title="Create a league"
          >
            <PlusIcon />
          </Link>
        </div>

        {!leagues ? (
          <Loading label="Loading leagues" />
        ) : !leagues.length ? (
          <Empty title="No leagues yet">
            <p>Use + to create a league, or join via an invite or shareable link.</p>
          </Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {leagues.map((league) => (
              <li key={league.id}>
                <Link
                  href={
                    league.status === "drafting"
                      ? `/leagues/${league.id}/draft`
                      : `/leagues/${league.id}`
                  }
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

      {invites && invites.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg sm:text-xl">Pending invites</h2>
          <ul className="flex flex-col gap-2">
            {invites.map((invite) => (
              <li
                key={invite.id}
                className="rounded-xl border border-line bg-surface p-4 shadow-soft"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <strong className="block truncate text-base">{invite.league_name}</strong>
                    <Muted className="mt-1">{inviteMetaLabel(invite)}</Muted>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    disabled={!invite.token || acceptingId === invite.id}
                    onClick={() => acceptInvite(invite)}
                  >
                    {acceptingId === invite.id ? "Accepting…" : "Accept"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Stack>
  );
}
