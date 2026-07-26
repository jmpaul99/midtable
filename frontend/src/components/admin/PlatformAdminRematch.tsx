"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { UUID } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Input, Label, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

interface CatalogOption {
  id: UUID;
  key: string;
  label: string;
  kind: string;
  source: string;
  as_of?: string | null;
}

interface MatchRow {
  rank: number;
  team_name: string;
  country_code: string | null;
  matched_external_team_id: string | null;
  matched_team_name: string | null;
  match_source: "override" | "auto" | null;
  suggested_external_team_id: string | null;
  suggested_team_name: string | null;
  score: number;
}

interface AdminTeamOption {
  external_id: string;
  name: string;
  short_name: string | null;
  tla: string | null;
  provider: string;
}

type FilterMode = "all" | "unmatched" | "override" | "auto";

function sourceLabel(source: MatchRow["match_source"]) {
  if (source === "override") return "Override";
  if (source === "auto") return "Auto";
  return "Unmatched";
}

export function PlatformAdminRematch({
  leagueId,
  preferredKey,
  onSaved,
  onError,
}: {
  leagueId?: UUID;
  preferredKey?: string;
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [catalogs, setCatalogs] = useState<CatalogOption[]>([]);
  const [catalogId, setCatalogId] = useState<UUID | "">("");
  const [matches, setMatches] = useState<MatchRow[]>([]);
  const [teams, setTeams] = useState<AdminTeamOption[]>([]);
  const [teamQuery, setTeamQuery] = useState("");
  const [entryQuery, setEntryQuery] = useState("");
  const [filter, setFilter] = useState<FilterMode>("all");
  const [mappings, setMappings] = useState<Record<number, string>>({});
  const [busyRank, setBusyRank] = useState<number | null>(null);

  useEffect(() => {
    api<CatalogOption[]>("/ranking-catalogs")
      .then((rows) => {
        const system = rows.filter((c) => c.kind === "system");
        setCatalogs(system);
        const preferred = system.find((c) => c.key === preferredKey) || system[0];
        if (preferred) setCatalogId(preferred.id);
      })
      .catch((e) => onError(errorMessage(e)));
  }, [preferredKey, onError]);

  useEffect(() => {
    const q = teamQuery.trim();
    if (q.length < 2) {
      setTeams([]);
      return;
    }
    const handle = window.setTimeout(() => {
      api<AdminTeamOption[]>(`/admin/teams?q=${encodeURIComponent(q)}`)
        .then(setTeams)
        .catch(() => setTeams([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [teamQuery]);

  const loadMatches = useCallback(() => {
    if (!catalogId) return;
    const path = leagueId
      ? `/ranking-catalogs/${catalogId}/matches?league_id=${leagueId}`
      : `/ranking-catalogs/${catalogId}/matches`;
    api<MatchRow[]>(path)
      .then((rows) => {
        setMatches(rows);
        setMappings(
          Object.fromEntries(
            rows.map((r) => {
              const current =
                r.matched_external_team_id || r.suggested_external_team_id || "";
              return [r.rank, current] as const;
            }),
          ),
        );
      })
      .catch((e) => onError(errorMessage(e)));
  }, [catalogId, leagueId, onError]);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  const filtered = useMemo(() => {
    const q = entryQuery.trim().toLowerCase();
    return matches.filter((row) => {
      if (filter === "unmatched" && row.matched_external_team_id) return false;
      if (filter === "override" && row.match_source !== "override") return false;
      if (filter === "auto" && row.match_source !== "auto") return false;
      if (!q) return true;
      return (
        row.team_name.toLowerCase().includes(q) ||
        (row.country_code || "").toLowerCase().includes(q) ||
        (row.matched_team_name || "").toLowerCase().includes(q)
      );
    });
  }, [matches, filter, entryQuery]);

  const counts = useMemo(() => {
    let unmatched = 0;
    let override = 0;
    let auto = 0;
    for (const row of matches) {
      if (!row.matched_external_team_id) unmatched += 1;
      else if (row.match_source === "override") override += 1;
      else auto += 1;
    }
    return { all: matches.length, unmatched, override, auto };
  }, [matches]);

  const teamOptions = useMemo(() => {
    const byId = new Map(teams.map((t) => [t.external_id, t]));
    for (const row of matches) {
      if (row.matched_external_team_id && !byId.has(row.matched_external_team_id)) {
        byId.set(row.matched_external_team_id, {
          external_id: row.matched_external_team_id,
          name: row.matched_team_name || row.matched_external_team_id,
          short_name: null,
          tla: row.country_code,
          provider: "football-data.org",
        });
      }
      if (row.suggested_external_team_id && !byId.has(row.suggested_external_team_id)) {
        byId.set(row.suggested_external_team_id, {
          external_id: row.suggested_external_team_id,
          name: row.suggested_team_name || row.suggested_external_team_id,
          short_name: null,
          tla: row.country_code,
          provider: "football-data.org",
        });
      }
      const selected = mappings[row.rank];
      if (selected && !byId.has(selected)) {
        byId.set(selected, {
          external_id: selected,
          name: selected,
          short_name: null,
          tla: null,
          provider: "football-data.org",
        });
      }
    }
    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [teams, matches, mappings]);

  async function saveOverride(row: MatchRow) {
    const externalId = mappings[row.rank];
    if (!catalogId || !externalId) return;
    if (externalId === row.matched_external_team_id && row.match_source === "override") {
      return;
    }
    setBusyRank(row.rank);
    onError("");
    try {
      await api(
        `/ranking-catalogs/${catalogId}/overrides`,
        json("PUT", {
          country_code: row.country_code,
          team_name: row.team_name,
          provider: "football-data.org",
          external_team_id: externalId,
        }),
      );
      onSaved();
      loadMatches();
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusyRank(null);
    }
  }

  const filters: { id: FilterMode; label: string; count: number }[] = [
    { id: "all", label: "All", count: counts.all },
    { id: "unmatched", label: "Unmatched", count: counts.unmatched },
    { id: "override", label: "Overrides", count: counts.override },
    { id: "auto", label: "Auto", count: counts.auto },
  ];

  return (
    <Card>
      <Stack>
        <div>
          <h2>Platform admin rematch</h2>
          <Muted className="mt-1">
            Review and correct FIFA ranking → football-data.org team mappings. Saving an
            override updates all unlocked leagues using this catalog.
          </Muted>
        </div>
        <Label>
          Catalog
          <Select
            value={catalogId}
            onChange={(e) => setCatalogId(e.target.value as UUID | "")}
          >
            <option value="">Select…</option>
            {catalogs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </Select>
        </Label>
        <div className="flex flex-wrap gap-2">
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-bold transition",
                filter === f.id
                  ? "bg-brand text-on-brand"
                  : "bg-surface-2 text-muted hover:text-ink",
              )}
            >
              {f.label} ({f.count})
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Label>
            Filter countries
            <Input
              type="search"
              value={entryQuery}
              onChange={(e) => setEntryQuery(e.target.value)}
              placeholder="Name or code…"
              autoComplete="off"
            />
          </Label>
          <Label>
            Search teams to map
            <Input
              type="search"
              value={teamQuery}
              onChange={(e) => setTeamQuery(e.target.value)}
              placeholder="Type at least 2 characters…"
              autoComplete="off"
            />
          </Label>
        </div>
        {filtered.length === 0 ? (
          <Muted className="text-sm">No catalog entries match this filter.</Muted>
        ) : (
          <ul className="flex flex-col gap-2">
            {filtered.map((row) => {
              const selected = mappings[row.rank] || "";
              const dirty =
                selected !== "" && selected !== (row.matched_external_team_id || "");
              return (
                <li
                  key={`${row.rank}-${row.team_name}`}
                  className="rounded-xl border border-line bg-surface-2/50 p-3"
                >
                  <div className="mb-2 flex items-center gap-3">
                    <RankBadge value={row.rank} />
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate">{row.team_name}</strong>
                      <Muted className="text-xs">
                        {row.country_code || "no code"}
                        {row.matched_team_name
                          ? ` · ${row.matched_team_name}`
                          : row.suggested_team_name
                            ? ` · suggested ${row.suggested_team_name}`
                            : ""}
                      </Muted>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-md px-2 py-0.5 text-[0.7rem] font-bold",
                        row.match_source === "override" && "bg-brand/15 text-brand",
                        row.match_source === "auto" && "bg-surface text-muted ring-1 ring-line",
                        !row.match_source && "bg-amber-500/15 text-amber-800 dark:text-amber-200",
                      )}
                    >
                      {sourceLabel(row.match_source)}
                    </span>
                  </div>
                  <Label>
                    football-data.org team
                    <Select
                      value={selected}
                      onChange={(e) =>
                        setMappings((prev) => ({ ...prev, [row.rank]: e.target.value }))
                      }
                    >
                      <option value="">— unmatched —</option>
                      {teamOptions.map((t) => (
                        <option key={t.external_id} value={t.external_id}>
                          {t.name}
                          {t.tla ? ` (${t.tla})` : ""}
                        </option>
                      ))}
                    </Select>
                  </Label>
                  <div className="mt-2">
                    <IconButton
                      type="button"
                      label="Save override"
                      variant="primary"
                      busy={busyRank === row.rank}
                      disabled={!selected || !dirty}
                      onClick={() => void saveOverride(row)}
                    >
                      <SaveIcon />
                    </IconButton>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Stack>
    </Card>
  );
}
