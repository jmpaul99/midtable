"use client";

import { useState } from "react";
import { RequireAuth, RequirePlatformAdmin } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import { defaultFootballSeasonYear } from "@/lib/availableCompetitions";
import { PlatformAdminRematch } from "@/components/admin/PlatformAdminRematch";
import { StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { Card, Muted, PageHeader, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Input, Label } from "@/components/ui/Field";
import { useToast } from "@/components/ui/ToastProvider";

interface SyncResult {
  ok: boolean;
  season_year: number;
  teams?: {
    created?: number;
    updated?: number;
    competitions_ok?: number;
    competitions_total?: number;
    competitions?: Array<{
      code: string;
      season_year?: number;
      fell_back_to_latest?: boolean;
      ok?: boolean;
    }>;
  };
  rankings?: {
    ok?: boolean;
    skipped?: boolean;
    message?: string;
    error?: string;
    catalogs?: Record<string, { entries?: number; leagues_updated?: number }>;
  };
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
  const [syncing, setSyncing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  async function syncAll() {
    const year = Number(seasonYear);
    if (!Number.isInteger(year) || year < 1990 || year > 2100) {
      setValidation("Enter a valid season year.");
      return;
    }
    setSyncing(true);
    setValidation("");
    try {
      const result = await api<SyncResult>(
        "/admin/sync-teams-and-rankings",
        json("POST", { season_year: year }),
      );
      const teams = result.teams || {};
      const rankings = result.rankings || {};
      const catalogBits = rankings.catalogs
        ? Object.entries(rankings.catalogs)
            .map(([key, row]) => `${key}: ${row.entries ?? 0} entries`)
            .join("; ")
        : "";
      const rankingPart = rankings.skipped
        ? rankings.message || "FIFA rankings skipped"
        : rankings.error
          ? `FIFA rankings failed: ${rankings.error}`
          : catalogBits || "FIFA rankings refreshed";
      const fallbacks = (teams.competitions || [])
        .filter((c) => c.ok && c.fell_back_to_latest)
        .map((c) => `${c.code}→${c.season_year}`)
        .join(", ");
      const fallbackPart = fallbacks
        ? ` Latest-available used for: ${fallbacks}.`
        : "";
      toast({
        message:
          `Synced season ${result.season_year}: ` +
          `${teams.created ?? 0} teams created, ${teams.updated ?? 0} updated ` +
          `(${teams.competitions_ok ?? 0}/${teams.competitions_total ?? 0} competitions). ` +
          rankingPart +
          "." +
          fallbackPart,
        durationMs: null,
        dismissible: true,
      });
      setReloadKey((k) => k + 1);
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setSyncing(false);
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
        title="Ranking rematch"
        description="Review and correct men’s and women’s FIFA world ranking mappings without needing a league commissioner seat."
      />

      <Card>
        <Stack>
          <div>
            <h2>Sync teams & rankings</h2>
            <Muted className="mt-1">
              Pull football-data.org squads for all free-plan competitions, then refresh FIFA men
              and women ranking catalogs. If a tournament isn’t published for this season year
              (World Cup, Euros, etc.), the latest available season is used instead.
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
              />
            </Label>
            <Button
              type="button"
              variant="primary"
              disabled={syncing}
              onClick={() => void syncAll()}
            >
              {syncing ? "Syncing…" : "Sync all teams & rankings"}
            </Button>
          </div>
          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}
        </Stack>
      </Card>

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
