"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { UUID } from "@/lib/types";
import { Empty, ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { LockIcon, PlusIcon, UploadIcon, ListChecksIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Input, Label, Select, Textarea } from "@/components/ui/Field";

interface RankingListRow {
  id: UUID;
  key: string;
  label: string;
  source: string;
  as_of: string | null;
  locked: boolean;
}

interface ParseSuggestion {
  rank: number;
  input_name: string;
  suggested_team_id: UUID | null;
  suggested_team_name: string | null;
  score: number;
}

interface PoolTeamOption {
  id: UUID;
  name: string;
}

export function RankingIngest({ leagueId }: { leagueId: UUID }) {
  const [lists, setLists] = useState<RankingListRow[]>();
  const [teams, setTeams] = useState<PoolTeamOption[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [key, setKey] = useState("fifa_men");
  const [label, setLabel] = useState("FIFA rankings");
  const [text, setText] = useState("1,Argentina\n2,France\n3,England");
  const [activeListId, setActiveListId] = useState<UUID | "">("");
  const [suggestions, setSuggestions] = useState<ParseSuggestion[]>([]);
  const [mappings, setMappings] = useState<Record<number, UUID | "">>({});

  const load = useCallback(() => {
    api<RankingListRow[]>(`/leagues/${leagueId}/ranking-lists`)
      .then(setLists)
      .catch((e) => setError(errorMessage(e)));
    api<{ pools: Array<{ id: UUID }> }>(`/leagues/${leagueId}`)
      .then(async (league) => {
        const poolIds = (league as { pools?: Array<{ id: UUID }> }).pools?.map((p) => p.id) || [];
        const rows: PoolTeamOption[] = [];
        for (const poolId of poolIds) {
          const pts = await api<Array<{ id: UUID; name: string }>>(
            `/leagues/${leagueId}/pools/${poolId}/teams`,
          );
          for (const t of pts) {
            if (!rows.some((r) => r.id === t.id)) rows.push({ id: t.id, name: t.name });
          }
        }
        setTeams(rows.sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => undefined);
  }, [leagueId]);

  useEffect(() => {
    load();
  }, [load]);

  async function createList(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      const created = await api<RankingListRow>(
        `/leagues/${leagueId}/ranking-lists`,
        json("POST", {
          key,
          label,
          source: "manual",
        }),
      );
      setActiveListId(created.id);
      setMessage(`Created ranking list “${created.label}”.`);
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function parseText() {
    if (!activeListId) {
      setError("Create or select a ranking list first.");
      return;
    }
    setError("");
    setMessage("");
    try {
      const out = await api<{ rows: ParseSuggestion[] }>(
        `/leagues/${leagueId}/ranking-lists/${activeListId}/parse`,
        json("POST", { text }),
      );
      const rows = out.rows || [];
      setSuggestions(rows);
      setMappings(Object.fromEntries(rows.map((r) => [r.rank, r.suggested_team_id || ""] as const)));
      setMessage(`Parsed ${rows.length} rows. Rematch any unmatched teams, then import.`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function importEntries() {
    if (!activeListId) return;
    setError("");
    setMessage("");
    const bodyMappings: Record<number, UUID> = {};
    for (const row of suggestions) {
      const teamId = mappings[row.rank];
      if (teamId) bodyMappings[row.rank] = teamId;
    }
    try {
      const out = await api<{ created: number }>(
        `/leagues/${leagueId}/ranking-lists/${activeListId}/entries`,
        json("POST", { text, mappings: bodyMappings }),
      );
      setMessage(`Imported ${out.created} rankings.`);
      setSuggestions([]);
      setMappings({});
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function lockList() {
    if (!activeListId) return;
    setError("");
    try {
      await api(`/leagues/${leagueId}/ranking-lists/${activeListId}/lock`, json("POST"));
      setMessage("Ranking list locked.");
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (!lists) return <Loading label="Loading ranking lists…" />;

  return (
    <Card>
      <Stack>
        <div>
          <h2>Ranking lists (FIFA / fixed ranks)</h2>
          <Muted className="mt-1">
            Paste a ranked list for tournament upset scoring. Create the list, parse to preview team
            matches, rematch as needed, then import.
          </Muted>
        </div>
        {error && <ErrorState error={error} />}
        {message && <StatusBanner>{message}</StatusBanner>}

        <form className="flex flex-col gap-3" onSubmit={createList}>
          <Label>
            Key
            <Input value={key} onChange={(e) => setKey(e.target.value)} required />
          </Label>
          <Label>
            Label
            <Input value={label} onChange={(e) => setLabel(e.target.value)} required />
          </Label>
          <div className="flex justify-start">
            <IconButton type="submit" label="Create ranking list" variant="primary">
              <PlusIcon />
            </IconButton>
          </div>
        </form>

        <Label>
          Active list
          <Select
            value={activeListId}
            onChange={(e) => setActiveListId(e.target.value as UUID | "")}
          >
            <option value="">Select…</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label} ({l.key})
                {l.locked ? " · locked" : ""}
              </option>
            ))}
          </Select>
        </Label>

        <Label>
          Paste ranks
          <Textarea
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"1,Argentina\n2,France\nor one team name per line"}
            className="font-mono text-base"
          />
        </Label>

        <div className="flex flex-wrap gap-2">
          <IconButton
            type="button"
            label="Parse / preview"
            variant="secondary"
            onClick={parseText}
            disabled={!activeListId}
          >
            <ListChecksIcon />
          </IconButton>
          <IconButton
            type="button"
            label="Import entries"
            variant="primary"
            onClick={importEntries}
            disabled={!activeListId || !suggestions.length}
          >
            <UploadIcon />
          </IconButton>
          <IconButton
            type="button"
            label="Lock list"
            variant="secondary"
            onClick={lockList}
            disabled={!activeListId}
          >
            <LockIcon />
          </IconButton>
        </div>

        {suggestions.length ? (
          <ul className="flex flex-col gap-2">
            {suggestions.map((row) => (
              <li
                key={`${row.rank}-${row.input_name}`}
                className="rounded-xl border border-line bg-surface-2/50 p-3"
              >
                <div className="mb-2 flex items-center gap-3">
                  <RankBadge value={row.rank} />
                  <div className="min-w-0 flex-1">
                    <strong className="block truncate">{row.input_name}</strong>
                    <Muted className="text-xs">Match score {row.score.toFixed(2)}</Muted>
                  </div>
                </div>
                <Label>
                  Team
                  <Select
                    value={mappings[row.rank] || ""}
                    onChange={(e) =>
                      setMappings((prev) => ({
                        ...prev,
                        [row.rank]: e.target.value as UUID | "",
                      }))
                    }
                  >
                    <option value="">— unmatched —</option>
                    {teams.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </Select>
                </Label>
              </li>
            ))}
          </ul>
        ) : lists.length === 0 ? (
          <Empty title="No ranking lists yet" />
        ) : null}
      </Stack>
    </Card>
  );
}
