"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate, Json, League } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
import { cn } from "@/lib/cn";
import {
  AVAILABLE_COMPETITIONS,
  defaultFootballSeasonYear,
} from "@/lib/availableCompetitions";
import { CompetitionAutocomplete } from "@/components/settings/CompetitionAutocomplete";

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
        season_year: Number(p.season_year) || defaultFootballSeasonYear(),
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
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [seasonLabel, setSeasonLabel] = useState("");
  const [maxMembers, setMaxMembers] = useState("");
  const [poolParams, setPoolParams] = useState<
    Record<string, { competition_code: string; season_year: string }>
  >({});

  const isPremierLeague = template?.key === "premier_league";
  const templatePools = useMemo(() => poolsFromTemplate(template), [template]);
  const hasCompetitions = templatePools.length > 0;
  const stepCount = 2;
  const isLast = step >= stepCount - 1;

  useEffect(() => {
    const n = Number(template?.max_members);
    setMaxMembers(Number.isFinite(n) && n >= 2 ? String(n) : "");
  }, [template]);

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
            season_year: String(p.season_year || defaultFootballSeasonYear()),
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

  function goNext() {
    if (!name.trim() || !seasonLabel.trim() || !maxMembers) {
      setError("Fill in name, season label, and managers to continue.");
      return;
    }
    if (!hasCompetitions) {
      setError("This template needs at least one competition before you can create a league.");
      return;
    }
    setError("");
    setStep(1);
  }

  async function createLeague(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!isLast) {
      goNext();
      return;
    }
    if (!hasCompetitions) {
      setError("This template needs at least one competition before you can create a league.");
      return;
    }
    setCreating(true);
    setMessage("");
    setError("");
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
            name,
            season_label: seasonLabel,
            max_members: Number(maxMembers),
            pool_provider_params,
          }),
        );
        setMessage(`Created ${created.name}.`);
      } else {
        created = await api<League>(
          "/leagues",
          json("POST", {
            name,
            template_id: templateId || null,
            season_label: seasonLabel,
            max_members: Number(maxMembers),
          }),
        );

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
          <div className="flex items-baseline justify-between gap-3">
            <h2>{step === 0 ? "League details" : "Competitions"}</h2>
            <p className="text-xs font-semibold text-muted">
              Step {step + 1} of {stepCount}
            </p>
          </div>
          <Muted className="mt-1">
            {template
              ? `Using template “${template.label}”.`
              : "Pick a template with competitions to create a league."}
          </Muted>
        </div>

        <div className="flex gap-1" aria-label="League setup steps">
          {Array.from({ length: stepCount }, (_, i) => (
            <button
              key={i}
              type="button"
              disabled={i >= step}
              onClick={() => i < step && setStep(i)}
              className={cn(
                "h-1.5 min-w-6 flex-1 rounded-full transition",
                i === step ? "bg-brand" : i < step ? "bg-brand/35" : "bg-surface-2",
                i < step && "cursor-pointer hover:bg-brand/60",
              )}
              aria-label={`Step ${i + 1}`}
              aria-current={i === step ? "step" : undefined}
            />
          ))}
        </div>

        {error && <ErrorState error={error} />}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}

        <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={createLeague}>
          {step === 0 && (
            <>
              <Label>
                Name
                <Input
                  name="name"
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Label>
              <Label>
                <LabelRow>
                  Season label
                  <FieldHelp label="Season label">
                    Display name for this season (for example 2026-27). Shown on the league home and
                    standings.
                  </FieldHelp>
                </LabelRow>
                <Input
                  name="season_label"
                  required
                  placeholder="2026-27"
                  maxLength={40}
                  value={seasonLabel}
                  onChange={(e) => setSeasonLabel(e.target.value)}
                />
              </Label>
              <Label>
                <LabelRow>
                  Managers
                  <FieldHelp label="Managers">
                    Maximum number of manager seats in the league (including you).
                  </FieldHelp>
                </LabelRow>
                <Input
                  name="max_members"
                  type="number"
                  min={2}
                  max={100}
                  placeholder="e.g. 8"
                  required
                  value={maxMembers}
                  onChange={(e) => setMaxMembers(e.target.value)}
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
            </>
          )}

          {step === 1 && (
            <div className="sm:col-span-2 flex flex-col gap-3">
              {!hasCompetitions ? (
                <StatusBanner>
                  This template has no competitions. Edit the template and add at least one before
                  creating a league.
                </StatusBanner>
              ) : (
                <>
              <div className="flex items-start gap-2">
                <Muted className="text-xs">
                  Confirm the competition and season year for each — clubs are loaded when you
                  create the league.
                </Muted>
                <FieldHelp label="Competitions">
                  <p className="mb-2">
                    Choose which provider competition and season year to pull clubs from for each
                    competition on the template.
                  </p>
                  <ul className="list-disc space-y-1 pl-4">
                    <li>
                      <strong className="text-ink">Competition</strong> — the real-world league or
                      cup code (for example PL).
                    </li>
                    <li>
                      <strong className="text-ink">Season year</strong> — the provider season year
                      for that competition.
                    </li>
                  </ul>
                </FieldHelp>
              </div>
              {templatePools.map((p) => (
                <div
                  className="grid grid-cols-1 gap-3 rounded-xl border border-line bg-surface-2/40 p-3 sm:grid-cols-2"
                  key={p.key}
                >
                  <strong className="sm:col-span-2">{p.label || p.key}</strong>
                  <Label>
                    Competition
                    <CompetitionAutocomplete
                      value={poolParams[p.key]?.competition_code || ""}
                      onChange={(code) =>
                        setPoolParams((prev) => ({
                          ...prev,
                          [p.key]: {
                            ...prev[p.key],
                            competition_code: code,
                          },
                        }))
                      }
                      options={AVAILABLE_COMPETITIONS}
                      required
                    />
                  </Label>
                  <Label>
                    <LabelRow>
                      Season year
                      <FieldHelp label="Season year">
                        Provider season year used when loading clubs for this competition.
                      </FieldHelp>
                    </LabelRow>
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
                </>
              )}
            </div>
          )}

          <div className="sm:col-span-2 flex flex-wrap gap-2">
            {step > 0 && (
              <Button type="button" variant="secondary" onClick={() => setStep(0)}>
                Back
              </Button>
            )}
            {!isLast ? (
              <Button type="button" variant="primary" onClick={goNext}>
                Next
              </Button>
            ) : (
              <Button
                type="submit"
                variant="primary"
                disabled={
                  creating ||
                  !hasCompetitions ||
                  plBlocked ||
                  (isPremierLeague && !gates)
                }
              >
                {creating
                  ? "Creating"
                  : plBlocked
                    ? "Blocked by prior seasons"
                    : "Create League"}
              </Button>
            )}
          </div>
        </form>
      </Stack>
    </Card>
  );
}
