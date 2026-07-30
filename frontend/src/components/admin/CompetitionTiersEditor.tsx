"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { StatusBanner } from "@/components/ui/State";

export interface CompetitionTierRow {
  code: string;
  label: string;
  key: string;
  team_kind: string;
  domestic_tier: number | null;
  default_domestic_tier: number | null;
}

const TIER_OPTIONS = [
  { value: "", label: "None (cup / international)" },
  { value: "1", label: "Tier 1 (top flight)" },
  { value: "2", label: "Tier 2" },
  { value: "3", label: "Tier 3" },
  { value: "4", label: "Tier 4" },
] as const;

function tierToSelectValue(tier: number | null): string {
  return tier == null ? "" : String(tier);
}

function selectValueToTier(value: string): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

function kindLabel(kind: string) {
  if (kind === "national_men") return "National (men)";
  if (kind === "national_women") return "National (women)";
  return "Club";
}

export function CompetitionTiersEditor({
  onSaved,
  onError,
}: {
  onSaved?: () => void;
  onError?: (msg: string) => void;
}) {
  const [rows, setRows] = useState<CompetitionTierRow[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setLoadError("");
    api<CompetitionTierRow[]>("/admin/competition-tiers")
      .then((data) => {
        setRows(data);
        setDraft(
          Object.fromEntries(
            data.map((row) => [row.code, tierToSelectValue(row.domestic_tier)]),
          ),
        );
      })
      .catch((err) => {
        const msg = errorMessage(err);
        setLoadError(msg);
        onError?.(msg);
      })
      .finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = useMemo(() => {
    return rows.some(
      (row) => draft[row.code] !== tierToSelectValue(row.domestic_tier),
    );
  }, [rows, draft]);

  async function save() {
    const tiers = rows.map((row) => ({
      code: row.code,
      domestic_tier: selectValueToTier(draft[row.code] ?? ""),
    }));
    setSaving(true);
    try {
      const updated = await api<CompetitionTierRow[]>(
        "/admin/competition-tiers",
        json("PUT", { tiers }),
      );
      setRows(updated);
      setDraft(
        Object.fromEntries(
          updated.map((row) => [row.code, tierToSelectValue(row.domestic_tier)]),
        ),
      );
      onSaved?.();
    } catch (err) {
      onError?.(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function resetToDefaults() {
    setDraft(
      Object.fromEntries(
        rows.map((row) => [
          row.code,
          tierToSelectValue(row.default_domestic_tier),
        ]),
      ),
    );
  }

  return (
    <Card>
      <Stack>
        <div>
          <h2>Competition tiers</h2>
          <Muted className="mt-1">
            Domestic ladder used for draft autopick when ranking by league table.
            Lower numbers are stronger (Premier League = 1, Championship = 2).
            Same-tier competitions (e.g. Premier League and La Liga) interleave by
            table position. Cups and internationals should be “None”.
          </Muted>
        </div>

        {loadError ? <StatusBanner tone="error">{loadError}</StatusBanner> : null}
        {loading ? (
          <Muted>Loading competitions…</Muted>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
              <thead className="bg-surface-2 text-xs font-bold uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2">Competition</th>
                  <th className="px-3 py-2">Code</th>
                  <th className="px-3 py-2">Kind</th>
                  <th className="px-3 py-2">Tier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((row) => {
                  const value = draft[row.code] ?? "";
                  const changed =
                    value !== tierToSelectValue(row.domestic_tier);
                  return (
                    <tr
                      key={row.code}
                      className={changed ? "bg-brand/[0.04]" : undefined}
                    >
                      <td className="px-3 py-2 font-semibold text-ink">
                        {row.label}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-muted">
                        {row.code}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {kindLabel(row.team_kind)}
                      </td>
                      <td className="px-3 py-2">
                        <Label className="m-0 min-w-[12rem]">
                          <span className="sr-only">Tier for {row.label}</span>
                          <Select
                            value={value}
                            onChange={(e) =>
                              setDraft((prev) => ({
                                ...prev,
                                [row.code]: e.target.value,
                              }))
                            }
                          >
                            {TIER_OPTIONS.map((opt) => (
                              <option key={opt.value || "none"} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </Select>
                        </Label>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="primary"
            disabled={saving || loading || !dirty}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Save tiers"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={saving || loading}
            onClick={resetToDefaults}
          >
            Reset to defaults
          </Button>
        </div>
      </Stack>
    </Card>
  );
}
