"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UUID } from "@/lib/types";
import { Empty, ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";

interface RankingStatusRow {
  id: UUID;
  key: string;
  label: string;
  source: string;
  as_of: string | null;
  locked: boolean;
  entry_count: number;
  unmatched_count: number;
  is_selected: boolean;
}

interface CatalogOption {
  id: UUID;
  key: string;
  label: string;
  kind: string;
  source: string;
  as_of?: string | null;
}

interface UnmatchedRow {
  rank: number;
  team_name: string;
  country_code: string | null;
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

export function RankingIngest({ leagueId }: { leagueId: UUID }) {
  const { isAdmin } = useAuth();
  const [lists, setLists] = useState<RankingStatusRow[]>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    api<RankingStatusRow[]>(`/leagues/${leagueId}/ranking-lists`)
      .then(setLists)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!lists) return <Loading label="Loading ranking lists…" />;

  const selected = lists.find((l) => l.is_selected) || lists[0];

  return (
    <Card>
      <Stack>
        <div>
          <h2>Ranking lists</h2>
          <Muted className="mt-1">
            Fixed ranks used for upset scoring. System lists refresh via sync; platform admins can
            rematch unmatched countries globally.
          </Muted>
        </div>
        {error && <ErrorState error={error} />}
        {message && <StatusBanner>{message}</StatusBanner>}

        {lists.length === 0 ? (
          <Empty title="No ranking list selected" />
        ) : (
          <ul className="flex flex-col gap-2">
            {lists.map((l) => (
              <li
                key={l.id}
                className="rounded-xl border border-line bg-surface-2/50 px-3 py-2.5 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <strong>{l.label}</strong>
                  <Muted className="text-xs">
                    {l.locked ? "Locked" : "Unlocked"}
                    {l.is_selected ? " · selected" : ""}
                  </Muted>
                </div>
                <Muted className="mt-1 text-xs">
                  {l.as_of ? `As of ${l.as_of}` : "No as-of date"}
                  {" · "}
                  {l.entry_count} ranked
                  {" · "}
                  {l.unmatched_count} unmatched
                </Muted>
              </li>
            ))}
          </ul>
        )}

        {isAdmin && (
          <PlatformAdminRematch
            leagueId={leagueId}
            preferredKey={selected?.key}
            onSaved={() => {
              setMessage("Override saved. Unlocked leagues using this list were updated.");
              load();
            }}
            onError={setError}
          />
        )}
      </Stack>
    </Card>
  );
}

function PlatformAdminRematch({
  leagueId,
  preferredKey,
  onSaved,
  onError,
}: {
  leagueId: UUID;
  preferredKey?: string;
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [catalogs, setCatalogs] = useState<CatalogOption[]>([]);
  const [catalogId, setCatalogId] = useState<UUID | "">("");
  const [unmatched, setUnmatched] = useState<UnmatchedRow[]>([]);
  const [teams, setTeams] = useState<AdminTeamOption[]>([]);
  const [mappings, setMappings] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<CatalogOption[]>("/ranking-catalogs")
      .then((rows) => {
        const system = rows.filter((c) => c.kind === "system");
        setCatalogs(system);
        const preferred = system.find((c) => c.key === preferredKey) || system[0];
        if (preferred) setCatalogId(preferred.id);
      })
      .catch((e) => onError(errorMessage(e)));
    api<AdminTeamOption[]>("/admin/teams")
      .then(setTeams)
      .catch(() => undefined);
  }, [preferredKey, onError]);

  const loadUnmatched = useCallback(() => {
    if (!catalogId) return;
    api<UnmatchedRow[]>(
      `/ranking-catalogs/${catalogId}/unmatched?league_id=${leagueId}`,
    )
      .then((rows) => {
        setUnmatched(rows);
        setMappings(
          Object.fromEntries(
            rows.map((r) => [r.rank, r.suggested_external_team_id || ""] as const),
          ),
        );
      })
      .catch((e) => onError(errorMessage(e)));
  }, [catalogId, leagueId, onError]);

  useEffect(() => {
    loadUnmatched();
  }, [loadUnmatched]);

  async function saveOverride(row: UnmatchedRow) {
    const externalId = mappings[row.rank];
    if (!catalogId || !externalId) return;
    setBusy(true);
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
      loadUnmatched();
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-3 rounded-xl border border-line p-3">
      <div>
        <h3 className="text-sm font-extrabold">Platform admin rematch</h3>
        <Muted className="mt-1 text-xs">
          Overrides apply to all unlocked leagues using this catalog.
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
      {unmatched.length === 0 ? (
        <Muted className="text-sm">No unmatched catalog entries for this league’s teams.</Muted>
      ) : (
        <ul className="flex flex-col gap-2">
          {unmatched.map((row) => (
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
                    {row.suggested_team_name
                      ? ` · suggested ${row.suggested_team_name}`
                      : ""}
                  </Muted>
                </div>
              </div>
              <Label>
                football-data.org team
                <Select
                  value={mappings[row.rank] || ""}
                  onChange={(e) =>
                    setMappings((prev) => ({ ...prev, [row.rank]: e.target.value }))
                  }
                >
                  <option value="">— unmatched —</option>
                  {teams.map((t) => (
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
                  busy={busy}
                  disabled={!mappings[row.rank]}
                  onClick={() => void saveOverride(row)}
                >
                  <SaveIcon />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
