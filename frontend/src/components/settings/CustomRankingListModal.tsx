"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, errorMessage, json } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Field";
import { ErrorState, Loading } from "@/components/ui/State";
import { Muted } from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";
import { TeamCrest } from "@/components/league/TeamCrest";
import { ReorderButtons, RowItem, RowList } from "./chrome";

export type RankingCatalogOption = {
  id: string;
  key: string;
  label: string;
  kind: string;
  source: string;
  as_of?: string | null;
};

export type RankingCompetitionRef = {
  competition_code: string;
  season_year: number;
};

type CompetitionTeam = {
  external_id: string;
  name: string;
  short_name?: string | null;
  crest_url?: string | null;
  competition_code: string;
};

type CompetitionTeamsResponse = {
  teams: CompetitionTeam[];
};

function rankingsText(teams: CompetitionTeam[]): string {
  return teams.map((t, i) => `${i + 1},${t.name}`).join("\n");
}

export function CustomRankingListModal({
  open,
  onClose,
  onCreated,
  competitions,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (catalog: RankingCatalogOption) => void;
  competitions: RankingCompetitionRef[];
}) {
  const titleId = useId();
  const labelRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const [label, setLabel] = useState("");
  const [teams, setTeams] = useState<CompetitionTeam[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const competitionsKey = competitions
    .map((c) => `${c.competition_code.trim().toUpperCase()}:${c.season_year}`)
    .filter((k) => !k.startsWith(":"))
    .sort()
    .join("|");

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    labelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    setLabel("");
    setTeams([]);
    setLoadError("");
    setLoading(true);

    const payload = {
      competitions: competitionsKey
        ? competitionsKey.split("|").map((pair) => {
            const [code, year] = pair.split(":");
            return { code, season_year: Number(year) };
          })
        : [],
    };

    let cancelled = false;
    api<CompetitionTeamsResponse>("/competitions/teams", json("POST", payload))
      .then((res) => {
        if (cancelled) return;
        setTeams(res.teams ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, competitionsKey]);

  function reorder(from: number, to: number) {
    if (from === to || from < 0 || to < 0 || from >= teams.length || to >= teams.length) {
      return;
    }
    const next = [...teams];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setTeams(next);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!teams.length || loading || loadError) return;
    setBusy(true);
    try {
      const created = await api<RankingCatalogOption>(
        "/ranking-catalogs",
        json("POST", { label: label.trim(), text: rankingsText(teams) }),
      );
      onCreated(created);
      onClose();
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  if (!open || typeof document === "undefined") return null;

  const canSave = !busy && !loading && !loadError && teams.length > 0 && label.trim().length > 0;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <button
        type="button"
        aria-label="Dismiss"
        className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex max-h-[min(90vh,40rem)] w-full max-w-xl flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-lg"
        onSubmit={submit}
      >
        <h2 id={titleId} className="font-display text-lg font-extrabold text-ink">
          Custom ranking list
        </h2>
        <p className="text-sm text-muted">
          Rank teams from your selected competitions with the arrows. Only you can reuse this list.
        </p>
        <Label>
          Name
          <Input
            ref={labelRef}
            required
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="My tournament rankings"
          />
        </Label>
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <span className="text-sm font-semibold text-muted">Rankings</span>
          {loading ? (
            <Loading label="Loading teams" />
          ) : loadError ? (
            <ErrorState error={loadError} />
          ) : teams.length === 0 ? (
            <Muted className="text-sm">No teams found for the selected competitions.</Muted>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto rounded-xl">
              <RowList>
                {teams.map((team, index) => (
                  <RowItem key={team.external_id} className="p-2 sm:p-2.5">
                    <div className="flex items-center gap-2">
                      <ReorderButtons
                        index={index}
                        total={teams.length}
                        onMove={reorder}
                        itemLabel="team"
                      />
                      <Muted className="w-8 shrink-0 text-xs font-bold tabular-nums">
                        #{index + 1}
                      </Muted>
                      <TeamCrest name={team.name} crestUrl={team.crest_url} size="sm" />
                      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
                        {team.name}
                      </span>
                    </div>
                  </RowItem>
                ))}
              </RowList>
            </div>
          )}
        </div>
        <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!canSave}>
            {busy ? "Saving…" : "Save list"}
          </Button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
