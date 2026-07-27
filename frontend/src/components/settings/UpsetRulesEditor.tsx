"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Checkbox, Input, Label, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import {
  CustomRankingListModal,
  type RankingCatalogOption,
  type RankingCompetitionRef,
} from "./CustomRankingListModal";
import {
  slugifyKey,
  uniqueKey,
  type UpsetRules,
  type UpsetThreshold,
} from "./types";

const compactInput = "min-h-10 rounded-lg px-2.5 py-2 text-sm";
const tip = "text-[0.65rem] font-normal leading-snug text-muted";

function blankThreshold(existingKeys: string[]): UpsetThreshold {
  return {
    key: uniqueKey("upset", existingKeys, undefined, "upset"),
    name: "",
    result: "win",
    min_gap: 5,
    max_gap: 9,
    points: 1,
  };
}

export function UpsetRulesEditor({
  value,
  onChange,
  allowCustomLists = false,
  competitions = [],
}: {
  value: UpsetRules;
  onChange: (next: UpsetRules) => void;
  /** Custom lists require competitions to be defined first. */
  allowCustomLists?: boolean;
  /** Competitions whose teams can be ranked in a custom list. */
  competitions?: RankingCompetitionRef[];
}) {
  const fixed = value.rank_source === "fixed_ranking_at_event_start";
  const [catalogs, setCatalogs] = useState<RankingCatalogOption[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const loadCatalogs = useCallback(() => {
    api<RankingCatalogOption[]>("/ranking-catalogs")
      .then(setCatalogs)
      .catch((e) => setCatalogError(errorMessage(e)));
  }, []);

  useEffect(() => {
    if (fixed) loadCatalogs();
  }, [fixed, loadCatalogs]);

  function updateThreshold(index: number, patch: Partial<UpsetThreshold>) {
    onChange({
      ...value,
      thresholds: value.thresholds.map((t, i) => (i === index ? { ...t, ...patch } : t)),
    });
  }

  function updateName(index: number, name: string) {
    const current = value.thresholds[index];
    if (!current) return;
    const patch: Partial<UpsetThreshold> = { name };
    const hadName = Boolean((current.name ?? "").trim());
    const key = (current.key ?? "").trim();
    const placeholderKey = !key || /^upset(_\d+)?$/.test(key);
    if (!hadName && name.trim() && placeholderKey) {
      const keys = value.thresholds.map((t) => t.key);
      patch.key = uniqueKey(slugifyKey(name) || "upset", keys, index, "upset");
    }
    updateThreshold(index, patch);
  }

  function removeThreshold(index: number) {
    onChange({
      ...value,
      thresholds: value.thresholds.filter((_, i) => i !== index),
    });
  }

  const selectValue =
    value.ranking_list_key && catalogs.some((c) => c.key === value.ranking_list_key)
      ? value.ranking_list_key
      : value.ranking_list_key
        ? value.ranking_list_key
        : "";

  return (
    <EditorSection
      title="Upset rules"
      description="Bonus points when a lower-ranked club beats (or draws) a higher-ranked one. Gap is how many places separate them in the table (underdog rank − favorite rank)."
    >
      <div className="flex min-w-0 flex-col gap-3">
        <label className="flex items-center gap-2 text-sm font-semibold text-muted">
          <Checkbox
            className="size-4"
            checked={value.enabled}
            onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
          />
          Enabled
        </label>
        <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Label className="min-w-0 gap-1">
            Rank source
            <Select
              value={value.rank_source}
              onChange={(e) =>
                onChange({
                  ...value,
                  rank_source: e.target.value,
                  ranking_list_key:
                    e.target.value === "fixed_ranking_at_event_start"
                      ? value.ranking_list_key || "fifa_men"
                      : null,
                })
              }
              className={compactInput}
            >
              <option value="league_table_at_kickoff">League table at kickoff</option>
              <option value="fixed_ranking_at_event_start">Fixed ranking list</option>
            </Select>
          </Label>
          <Label className="min-w-0 gap-1 sm:max-w-[7rem]">
            Min GP
            <Input
              type="number"
              min={0}
              value={value.min_played || ""}
              placeholder="0"
              onChange={(e) =>
                onChange({
                  ...value,
                  min_played: e.target.value === "" ? 0 : Number(e.target.value),
                })
              }
              className={cn(compactInput, "w-full sm:w-[5.5rem]")}
              title="Both clubs need this many league games played before an upset can score"
            />
          </Label>
        </div>
        <p className={tip}>
          Min GP: both clubs must have completed this many games before upset points are awarded.
        </p>
        {fixed && (
          <Label className="min-w-0 gap-1">
            Ranking list
            <Select
              value={selectValue}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "__add_custom__") {
                  if (allowCustomLists) setModalOpen(true);
                  return;
                }
                onChange({ ...value, ranking_list_key: v || null });
              }}
              className={compactInput}
            >
              <option value="">Select a list…</option>
              {catalogs.map((c) => (
                <option key={c.id} value={c.key}>
                  {c.label}
                  {c.kind === "user" ? " (yours)" : ""}
                </option>
              ))}
              <option value="__add_custom__" disabled={!allowCustomLists}>
                {allowCustomLists
                  ? "Add custom list…"
                  : "Add custom list… (set competitions first)"}
              </option>
            </Select>
            {catalogError && <span className="text-xs text-danger">{catalogError}</span>}
          </Label>
        )}
      </div>

      {value.thresholds.length > 0 && (
        <RowList>
          {value.thresholds.map((t, index) => (
            <RowItem key={t.key || index} className="p-2.5 sm:p-3">
              <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1.2fr)_5.5rem_4rem_minmax(9rem,1fr)_auto] sm:items-start">
                <Label className="col-span-2 min-w-0 gap-1 sm:col-span-1">
                  Name
                  <Input
                    value={t.name ?? ""}
                    onChange={(e) => updateName(index, e.target.value)}
                    className={compactInput}
                    required
                  />
                </Label>
                <Label className="min-w-0 gap-1">
                  Result
                  <Select
                    value={t.result}
                    onChange={(e) =>
                      updateThreshold(index, {
                        result: e.target.value as UpsetThreshold["result"],
                      })
                    }
                    className={compactInput}
                  >
                    <option value="win">Win</option>
                    <option value="draw">Draw</option>
                    <option value="loss">Loss</option>
                  </Select>
                </Label>
                <Label className="min-w-0 gap-1">
                  Pts
                  <Input
                    type="number"
                    step="0.5"
                    value={t.points}
                    onChange={(e) =>
                      updateThreshold(index, { points: Number(e.target.value) })
                    }
                    className={compactInput}
                  />
                </Label>
                <div className="col-span-2 grid min-w-0 grid-cols-2 gap-x-2 gap-y-1 sm:col-span-1">
                  <span className="text-sm font-semibold text-muted">Min gap</span>
                  <span className="text-sm font-semibold text-muted">Max gap</span>
                  <Input
                    type="number"
                    min={0}
                    value={t.min_gap}
                    onChange={(e) =>
                      updateThreshold(index, { min_gap: Number(e.target.value) })
                    }
                    className={compactInput}
                    title="Smallest rank gap that counts for this threshold"
                    aria-label="Min gap"
                  />
                  <Input
                    type="number"
                    min={0}
                    value={t.max_gap ?? ""}
                    placeholder="∞"
                    onChange={(e) =>
                      updateThreshold(index, {
                        max_gap: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                    className={compactInput}
                    title="Largest rank gap that counts; leave blank for no upper limit"
                    aria-label="Max gap"
                  />
                  <span className={cn(tip, "col-span-2")}>
                    Places apart, inclusive · blank max = no limit
                  </span>
                </div>
                <div className="col-span-2 flex justify-end sm:col-span-1 sm:justify-start sm:pt-[1.375rem]">
                  <RemoveButton onClick={() => removeThreshold(index)} />
                </div>
              </div>
            </RowItem>
          ))}
        </RowList>
      )}

      <AddRowButton
        label="Add threshold"
        onClick={() =>
          onChange({
            ...value,
            thresholds: [
              ...value.thresholds,
              blankThreshold(value.thresholds.map((t) => t.key)),
            ],
          })
        }
      />

      <CustomRankingListModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        competitions={competitions}
        onCreated={(catalog) => {
          setCatalogs((prev) =>
            prev.some((c) => c.id === catalog.id) ? prev : [...prev, catalog],
          );
          onChange({ ...value, ranking_list_key: catalog.key });
        }}
      />
    </EditorSection>
  );
}
