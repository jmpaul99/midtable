"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RequireAuth, RequirePlatformAdmin } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import { defaultFootballSeasonYear } from "@/lib/availableCompetitions";
import { formatDate } from "@/lib/format";
import { PlatformAdminRematch } from "@/components/admin/PlatformAdminRematch";
import { CompetitionTiersEditor } from "@/components/admin/CompetitionTiersEditor";
import { Status, StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { Card, Muted, PageHeader, Row, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Input, Label } from "@/components/ui/Field";
import { useToast } from "@/components/ui/ToastProvider";
import type { LatestPlatformJobs, PlatformJob, UUID } from "@/lib/types";

const JOB_POLL_MS = 2500;
const ACTIVE_JOB = new Set(["pending", "running"]);

function isActiveJob(job: PlatformJob | null | undefined): boolean {
  return !!job && ACTIVE_JOB.has(job.status);
}

export default function AdminRankingsPage() {
  return (
    <RequireAuth>
      <RequirePlatformAdmin>
        <AdminRankingsContent />
      </RequirePlatformAdmin>
    </RequireAuth>
  );
}

function AdminRankingsContent() {
  const { toast } = useToast();
  const [validation, setValidation] = useState("");
  const [seasonYear, setSeasonYear] = useState(String(defaultFootballSeasonYear()));
  const [latestJobs, setLatestJobs] = useState<LatestPlatformJobs>({
    manual: null,
    cron: null,
  });
  const [pollingJobId, setPollingJobId] = useState<UUID | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const toastedJobIds = useRef<Set<string>>(new Set());

  const loadJobs = useCallback(async () => {
    try {
      const jobs = await api<LatestPlatformJobs>("/admin/jobs/latest");
      setLatestJobs(jobs);
      if (isActiveJob(jobs.manual)) {
        setPollingJobId(jobs.manual!.id);
      }
      return jobs;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!pollingJobId) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const job = await api<PlatformJob>(`/admin/jobs/${pollingJobId}`);
        if (cancelled) return;
        setLatestJobs((prev) => ({
          ...prev,
          manual: job.source === "admin" ? job : prev.manual,
        }));
        if (ACTIVE_JOB.has(job.status)) return;

        setPollingJobId(null);
        if (!toastedJobIds.current.has(job.id)) {
          toastedJobIds.current.add(job.id);
          const summary = summarizePlatformJob(job);
          toast({
            message: summary,
            tone: job.status === "failed" ? "error" : "success",
            durationMs: summary.length > 120 ? null : 5000,
            dismissible: summary.length > 120 ? true : undefined,
          });
        }
        void loadJobs();
        setReloadKey((k) => k + 1);
      } catch {
        /* keep polling; transient errors */
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), JOB_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollingJobId, loadJobs, toast]);

  const jobBusy = isActiveJob(latestJobs.manual) || !!pollingJobId;

  async function enqueueSync() {
    const year = Number(seasonYear);
    if (!Number.isInteger(year) || year < 1990 || year > 2100) {
      setValidation("Enter a valid season year.");
      return;
    }
    setValidation("");
    try {
      const job = await api<PlatformJob>(
        "/admin/sync-teams-and-rankings",
        json("POST", { season_year: year }),
      );
      setLatestJobs((prev) => ({ ...prev, manual: job }));
      setPollingJobId(job.id);
      toast({ message: "Teams & rankings sync started in the background." });
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        breadcrumbs={
          <Breadcrumbs
            items={[{ label: "Home", href: "/" }, { label: "Platform admin" }]}
          />
        }
        title="Rankings & tiers"
        description="Correct FIFA ranking team mappings and set domestic competition tiers used for draft autopick."
      />

      <Card>
        <Stack>
          <div>
            <h2>Sync teams & rankings</h2>
            <Muted className="mt-1">
              Pull football-data.org squads for all free-plan competitions, refresh FIFA men
              and women ranking catalogs, and create shared table baselines (previous-season
              final + zeroed current opener) when missing. Runs in the background — you can
              leave and return. Waits out API rate limits using response headers, so a full
              run can take several minutes. If a tournament isn’t published for this season
              year (World Cup, Euros, etc.), the latest available season is used instead.
              Scheduled FIFA ranking refreshes appear in their own card.
            </Muted>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Label className="sm:w-40">
              Season year
              <Input
                type="number"
                min={1990}
                max={2100}
                value={seasonYear}
                onChange={(e) => setSeasonYear(e.target.value)}
                disabled={jobBusy}
              />
            </Label>
            <Button
              type="button"
              variant="primary"
              disabled={jobBusy}
              onClick={() => void enqueueSync()}
            >
              {jobBusy ? "Job running…" : "Sync all teams & rankings"}
            </Button>
          </div>
          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <PlatformJobResultCard
              title="Manual"
              job={latestJobs.manual}
              empty="No manual teams & rankings sync yet."
            />
            <PlatformJobResultCard
              title="Scheduled"
              job={latestJobs.cron}
              empty="No scheduled FIFA rankings sync has run yet."
            />
          </div>
        </Stack>
      </Card>

      <CompetitionTiersEditor
        onSaved={() => {
          toast({ message: "Competition tiers saved." });
        }}
        onError={(msg) => {
          if (!msg) return;
          toast({
            message: msg,
            tone: "error",
            durationMs: 6000,
            dismissible: true,
          });
        }}
      />

      <PlatformAdminRematch
        key={reloadKey}
        onSaved={() => {
          toast({
            message: "Override saved. Unlocked leagues using this list were updated.",
          });
        }}
        onError={(msg) => {
          if (!msg) return;
          toast({
            message: msg,
            tone: "error",
            durationMs: 6000,
            dismissible: true,
          });
        }}
      />
    </Stack>
  );
}

function PlatformJobResultCard({
  title,
  job,
  empty,
}: {
  title: string;
  job: PlatformJob | null;
  empty: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/50 p-3">
      <Row between>
        <strong className="text-sm">{title}</strong>
        {job ? <Status value={job.status} /> : null}
      </Row>
      {!job ? (
        <Muted className="mt-1 text-xs">{empty}</Muted>
      ) : (
        <>
          <Muted className="mt-1 text-xs">
            {kindLabel(job.kind)} ·{" "}
            {formatDate(job.finished_at || job.started_at || job.created_at)}
          </Muted>
          <Muted className="mt-1 text-xs">{summarizePlatformJob(job)}</Muted>
          {job.error && (
            <StatusBanner tone="error" className="mt-2">
              {job.error}
            </StatusBanner>
          )}
        </>
      )}
    </div>
  );
}

function kindLabel(kind: string): string {
  if (kind === "fifa_rankings") return "FIFA rankings";
  return "Teams & rankings";
}

export function summarizePlatformJob(job: PlatformJob): string {
  const source = job.source === "cron" ? "Scheduled" : "Manual";
  const subject = `${source} ${kindLabel(job.kind).toLowerCase()}`;

  if (job.status === "pending") return `${subject} queued.`;
  if (job.status === "running") return `${subject} running…`;
  if (job.status === "failed") {
    return job.error || `${subject} failed.`;
  }

  const parts = platformSummaryParts(job.summary);
  if (parts.length) return `${subject} complete — ${parts.join(" · ")}`;
  return `${subject} complete.`;
}

function platformSummaryParts(
  summary: Record<string, unknown> | null | undefined,
): string[] {
  if (!summary) return [];
  const parts: string[] = [];
  if (summary.season_year != null) parts.push(`season ${summary.season_year}`);
  if (summary.teams_created != null) parts.push(`${summary.teams_created} teams created`);
  if (summary.teams_updated != null) parts.push(`${summary.teams_updated} updated`);
  if (summary.competitions_ok != null && summary.competitions_total != null) {
    parts.push(`${summary.competitions_ok}/${summary.competitions_total} competitions`);
  }
  if (summary.rankings_skipped) {
    parts.push(
      typeof summary.rankings_message === "string"
        ? summary.rankings_message
        : "FIFA rankings skipped",
    );
  } else if (typeof summary.rankings_error === "string") {
    parts.push(`FIFA rankings failed: ${summary.rankings_error}`);
  } else if (summary.rankings_catalogs && typeof summary.rankings_catalogs === "object") {
    const catalogs = Object.entries(
      summary.rankings_catalogs as Record<string, { entries?: number }>,
    )
      .map(([key, row]) => `${key}: ${row.entries ?? 0}`)
      .join("; ");
    if (catalogs) parts.push(catalogs);
  }
  if (summary.created_previous_final != null || summary.created_zeroed_opener != null) {
    parts.push(
      `baselines ${summary.created_previous_final ?? 0}/${summary.created_zeroed_opener ?? 0}`,
    );
  }
  if (Array.isArray(summary.season_fallbacks) && summary.season_fallbacks.length) {
    parts.push(`fallbacks: ${summary.season_fallbacks.join(", ")}`);
  }
  return parts;
}
