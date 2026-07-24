"use client";

import { FormEvent, useState } from "react";
import type { League, PoolTeam } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { DownloadIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";

export function BootstrapTeamsSection({
  league,
  poolTeams,
  onLoad,
  embedded = false,
}: {
  league: League;
  poolTeams: Record<string, PoolTeam[]>;
  onLoad: (
    params: Array<{ key: string; competition_code: string; season_year: number }>,
  ) => Promise<void>;
  /** When true, omit outer Card so this can nest under Readiness & Sync. */
  embedded?: boolean;
}) {
  const [poolParams, setPoolParams] = useState(
    () =>
      Object.fromEntries(
        league.pools.map((p) => [
          p.key,
          {
            competition_code: p.competition_code || "",
            season_year: String(p.season_year ?? new Date().getFullYear()),
          },
        ]),
      ) as Record<string, { competition_code: string; season_year: string }>,
  );

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!confirm("Load teams from the football-data.org provider into each competition?")) return;
    await onLoad(
      league.pools.map((p) => ({
        key: p.key,
        competition_code: poolParams[p.key]?.competition_code || p.competition_code || "",
        season_year: Number(poolParams[p.key]?.season_year || p.season_year || 0),
      })),
    );
  }

  const body = (
      <Stack>
        <Muted>
          Set competition code and season year per competition, then load (or reload) clubs from
          football-data.org.
        </Muted>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          {league.pools.map((p) => (
            <div
              className="grid grid-cols-1 gap-3 rounded-xl border border-line bg-surface-2/40 p-3 sm:grid-cols-2"
              key={p.id}
            >
              <strong className="sm:col-span-2">{p.name || p.label || p.key}</strong>
              <Label>
                Competition code
                <Input
                  value={poolParams[p.key]?.competition_code || ""}
                  onChange={(e) =>
                    setPoolParams((prev) => ({
                      ...prev,
                      [p.key]: { ...prev[p.key], competition_code: e.target.value },
                    }))
                  }
                  required
                />
              </Label>
              <Label>
                Season year
                <Input
                  type="number"
                  value={poolParams[p.key]?.season_year || ""}
                  onChange={(e) =>
                    setPoolParams((prev) => ({
                      ...prev,
                      [p.key]: { ...prev[p.key], season_year: e.target.value },
                    }))
                  }
                  required
                />
              </Label>
              <Muted className="sm:col-span-2">
                {(poolTeams[p.id] || []).length} teams linked
              </Muted>
            </div>
          ))}
          <div className="flex justify-start">
            <IconButton type="submit" label="Load teams from provider" variant="primary">
              <DownloadIcon />
            </IconButton>
          </div>
        </form>
      </Stack>
  );

  if (embedded) return body;
  return <Card>{body}</Card>;
}
