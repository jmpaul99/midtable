"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate, Json, League } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { PlusIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";

type TemplatePool = {
  key: string;
  label?: string;
  competition_code?: string;
  season_year?: number;
  provider?: string;
};

type GateResponse = { blockers: Array<Record<string, Json>> };

function poolsFromTemplate(template: CompetitionTemplate | null): TemplatePool[] {
  const raw = (template?.pool_definitions || []) as Json[];
  return raw
    .map((item) => {
      const p = (item && typeof item === "object" ? item : {}) as Record<string, Json>;
      return {
        key: String(p.key || ""),
        label: p.label != null ? String(p.label) : undefined,
        competition_code: p.competition_code != null ? String(p.competition_code) : "",
        season_year: Number(p.season_year) || new Date().getFullYear(),
        provider: p.provider != null ? String(p.provider) : "football-data.org",
      } satisfies TemplatePool;
    })
    .filter((p) => p.key);
}

export function CreateLeagueForm({
  template,
  templateId,
}: {
  template: CompetitionTemplate | null;
  templateId: string | null;
}) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [gates, setGates] = useState<GateResponse>();
  const [gatesError, setGatesError] = useState("");
  const [poolParams, setPoolParams] = useState<
    Record<string, { competition_code: string; season_year: string }>
  >({});

  const isPremierLeague = template?.key === "premier_league";
  const templatePools = useMemo(() => poolsFromTemplate(template), [template]);

  useEffect(() => {
    if (!templatePools.length) {
      setPoolParams({});
      return;
    }
    setPoolParams(
      Object.fromEntries(
        templatePools.map((p) => [
          p.key,
          {
            competition_code: p.competition_code || "",
            season_year: String(p.season_year || new Date().getFullYear()),
          },
        ]),
      ),
    );
  }, [templatePools]);

  useEffect(() => {
    if (!isPremierLeague) {
      setGates(undefined);
      setGatesError("");
      return;
    }
    setGates(undefined);
    setGatesError("");
    api<GateResponse>("/leagues/premier-league/bootstrap-gates")
      .then(setGates)
      .catch((e) => setGatesError(errorMessage(e)));
  }, [isPremierLeague]);

  const blockers = gates?.blockers || [];
  const plBlocked = isPremierLeague && blockers.length > 0;

  async function createLeague(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreating(true);
    setMessage("");
    setError("");
    const form = e.currentTarget;
    const f = new FormData(form);
    const pool_provider_params = templatePools.map((p) => ({
      key: p.key,
      provider: p.provider || "football-data.org",
      competition_code: poolParams[p.key]?.competition_code || p.competition_code || "",
      season_year: Number(poolParams[p.key]?.season_year || p.season_year || 0),
    }));

    try {
      let created: League;

      if (isPremierLeague) {
        created = await api<League>(
          "/leagues/premier-league/seasons",
          json("POST", {
            template_key: "premier_league",
            name: f.get("name"),
            season_label: f.get("season_label"),
            max_members: Number(f.get("max_members")),
            pool_provider_params,
          }),
        );
        setMessage(`Created ${created.name}.`);
      } else {
        created = await api<League>(
          "/leagues",
          json("POST", {
            name: f.get("name"),
            template_id: templateId || null,
            season_label: f.get("season_label"),
            max_members: Number(f.get("max_members")),
          }),
        );

        if (templateId && templatePools.length) {
          const out = await api<{
            linked?: number;
            created_teams?: number;
            skipped_existing?: number;
            pools?: Array<Record<string, unknown>>;
          }>(
            `/leagues/${created.id}/bootstrap-teams`,
            json("POST", { pool_provider_params }),
          );
          const poolErrors = (out.pools || [])
            .filter((p) => typeof p.error === "string")
            .map((p) => `${p.pool_key}: ${p.error}`);
          const base = `Created ${created.name}. Teams: ${out.linked ?? 0} linked, ${out.created_teams ?? 0} created.`;
          setMessage(poolErrors.length ? `${base} Issues — ${poolErrors.join("; ")}` : base);
        } else {
          setMessage(`Created ${created.name}.`);
        }
      }

      router.push(`/leagues/${created.id}/admin`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <Card>
      <Stack>
        <div>
          <h2>League details</h2>
          <Muted className="mt-1">
            {template
              ? `Using template “${template.label || template.name || template.key}”.`
              : "Creating without a template — configure competitions later in Commissioner settings."}
          </Muted>
        </div>
        {error && <ErrorState error={error} />}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}
        <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={createLeague}>
          <Label>
            Name
            <Input name="name" required maxLength={160} />
          </Label>
          <Label>
            Season label
            <Input name="season_label" required placeholder="2026-27" maxLength={40} />
          </Label>
          <Label>
            Managers
            <Input
              name="max_members"
              type="number"
              min={2}
              max={100}
              placeholder="e.g. 8"
              required
            />
          </Label>

          {isPremierLeague && (
            <div className="sm:col-span-2">
              {gatesError ? (
                <ErrorState
                  error={gatesError}
                  retry={() => {
                    setGatesError("");
                    api<GateResponse>("/leagues/premier-league/bootstrap-gates")
                      .then(setGates)
                      .catch((e) => setGatesError(errorMessage(e)));
                  }}
                />
              ) : !gates ? (
                <Loading label="Checking prior seasons" />
              ) : blockers.length ? (
                <StatusBanner>
                  <strong>Prior seasons still open</strong>
                  <ul className="mt-2 list-disc pl-5">
                    {blockers.map((b, i) => (
                      <li key={i}>
                        {String(b.name || b.season_label || "league")} (
                        {String(b.status || "?")}): {String(b.reason || JSON.stringify(b))}
                      </li>
                    ))}
                  </ul>
                </StatusBanner>
              ) : (
                <StatusBanner tone="success">
                  No prior-season blockers — ready if the provider has teams.
                </StatusBanner>
              )}
            </div>
          )}

          {templatePools.length > 0 && (
            <div className="sm:col-span-2 flex flex-col gap-3">
              <div>
                <h3 className="font-display text-base font-extrabold">Load teams</h3>
                <Muted className="text-xs">
                  Competition code and season year per competition — clubs are pulled right after the league
                  is created.
                </Muted>
              </div>
              {templatePools.map((p) => (
                <div
                  className="grid grid-cols-1 gap-3 rounded-xl border border-line bg-surface-2/40 p-3 sm:grid-cols-2"
                  key={p.key}
                >
                  <strong className="sm:col-span-2">{p.label || p.key}</strong>
                  <Label>
                    Competition code
                    <Input
                      value={poolParams[p.key]?.competition_code || ""}
                      onChange={(e) =>
                        setPoolParams((prev) => ({
                          ...prev,
                          [p.key]: {
                            ...prev[p.key],
                            competition_code: e.target.value,
                          },
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
                          [p.key]: {
                            ...prev[p.key],
                            season_year: e.target.value,
                          },
                        }))
                      }
                      required
                    />
                  </Label>
                </div>
              ))}
            </div>
          )}

          <div className="sm:col-span-2 flex justify-start">
            <IconButton
              type="submit"
              variant="primary"
              label={
                creating
                  ? templatePools.length
                    ? "Creating & loading teams"
                    : "Creating"
                  : plBlocked
                    ? "Blocked by prior seasons"
                    : templatePools.length
                      ? "Create league & load teams"
                      : "Create league"
              }
              busy={creating}
              disabled={plBlocked || (isPremierLeague && !gates)}
            >
              <PlusIcon />
            </IconButton>
          </div>
        </form>
      </Stack>
    </Card>
  );
}
