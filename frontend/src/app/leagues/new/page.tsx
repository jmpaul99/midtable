"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import {
  AVAILABLE_COMPETITIONS,
  competitionDisplayLabel,
  findAvailableCompetition,
} from "@/lib/availableCompetitions";
import { formatTemplatePreviewMeta } from "@/lib/templatePreview";
import type {
  CompetitionTemplate,
  RecentTemplateUsage,
  TemplateListResponse,
  TemplateNumericFilterOp,
} from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { ChevronDownIcon, EraserIcon, PlusIcon, XIcon } from "@/components/ui/icons";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

const iconLinkPrimary =
  "inline-flex size-9 items-center justify-center rounded-xl bg-brand text-on-brand shadow-sm transition hover:bg-brand-dark";

const chipBase =
  "inline-flex min-h-11 items-center justify-center rounded-xl border px-3 py-2 text-sm font-bold transition";

const selectCompact =
  "w-full min-h-10 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink";

const rowLink =
  "block border-b border-line last:border-0 transition hover:bg-brand/5 focus-visible:bg-brand/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand";

const PAGE_SIZE = 12;

type TriFilter = "" | "true" | "false";

function parseFilterInt(raw: string, min = 0): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < min) return null;
  return n;
}

function TemplateBadges({
  template,
  className,
}: {
  template: CompetitionTemplate;
  className?: string;
}) {
  if (!template.featured && !template.made_by_staff) return null;
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {template.featured && (
        <span className="rounded-md bg-brand/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand">
          Featured
        </span>
      )}
      {template.made_by_staff && (
        <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted">
          Staff
        </span>
      )}
    </div>
  );
}

function MetaField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="truncate text-sm text-ink" title={value}>
        {value}
      </dd>
    </div>
  );
}

function MetaFieldLines({ label, lines }: { label: string; lines: string[] }) {
  const values = lines.length ? lines : ["—"];
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="text-sm text-ink">
        <ul className="mt-0.5 space-y-0.5">
          {values.map((line) => (
            <li key={line} className="truncate" title={line}>
              {line}
            </li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

function TemplateMobileRow({
  href,
  template,
  ariaLabel,
  extra,
  fields = "full",
}: {
  href: string;
  template: CompetitionTemplate;
  ariaLabel: string;
  extra?: { label: string; value: string };
  fields?: "full" | "recent";
}) {
  const router = useRouter();
  const meta = formatTemplatePreviewMeta(template);
  return (
    <div
      role="link"
      tabIndex={0}
      aria-label={ariaLabel}
      onClick={() => router.push(href)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          router.push(href);
        }
      }}
      className={cn(
        rowLink,
        "cursor-pointer px-3 py-2.5 active:bg-brand/10",
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="truncate text-base font-bold text-ink">{template.label}</h3>
        <TemplateBadges template={template} />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
        {extra ? <MetaField label={extra.label} value={extra.value} /> : null}
        <MetaFieldLines label="Competitions" lines={meta.competitionLines} />
        {fields === "full" ? (
          <>
            <MetaFieldLines label="Roster" lines={meta.rosterLines} />
            <MetaField label="Members" value={meta.members} />
            <MetaField label="Phases" value={meta.phases} />
            <MetaField label="Scoring" value={meta.scoring} />
          </>
        ) : null}
      </dl>
    </div>
  );
}

function TemplateTableCell({ value }: { value: string }) {
  return (
    <td className="max-w-[10rem] truncate px-3 py-2.5 align-middle text-sm" title={value}>
      {value}
    </td>
  );
}

function TemplatesDesktopTable({ items }: { items: CompetitionTemplate[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[44rem] text-left text-sm">
        <thead className="border-b border-line text-xs font-bold uppercase tracking-wide text-muted">
          <tr>
            <th className="px-3 py-2.5 font-bold">Template</th>
            <th className="px-3 py-2.5 font-bold">Competitions</th>
            <th className="px-3 py-2.5 font-bold">Roster</th>
            <th className="px-3 py-2.5 font-bold">Members</th>
            <th className="px-3 py-2.5 font-bold">Phases</th>
            <th className="px-3 py-2.5 font-bold">Scoring</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => {
            const meta = formatTemplatePreviewMeta(t);
            const href = `/leagues/new/templates/${t.id}`;
            return (
              <tr
                key={t.id}
                role="link"
                tabIndex={0}
                aria-label={`View template ${t.label}`}
                onClick={() => router.push(href)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    router.push(href);
                  }
                }}
                className="cursor-pointer border-b border-line last:border-0 transition hover:bg-brand/5 focus-visible:bg-brand/5 focus-visible:outline-none"
              >
                <td className="px-3 py-2.5 align-middle">
                  <div className="flex max-w-[14rem] flex-col gap-1">
                    <span className="truncate font-bold text-ink">{t.label}</span>
                    <TemplateBadges template={t} />
                  </div>
                </td>
                <TemplateTableCell value={meta.competitions} />
                <TemplateTableCell value={meta.roster} />
                <TemplateTableCell value={meta.members} />
                <TemplateTableCell value={meta.phases} />
                <TemplateTableCell value={meta.scoring} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RecentDesktopTable({ rows }: { rows: RecentTemplateUsage[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[28rem] text-left text-sm">
        <thead className="border-b border-line text-xs font-bold uppercase tracking-wide text-muted">
          <tr>
            <th className="px-3 py-2.5 font-bold">Template</th>
            <th className="px-3 py-2.5 font-bold">Used in</th>
            <th className="px-3 py-2.5 font-bold">Competitions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const meta = formatTemplatePreviewMeta(row.template);
            const href = `/leagues/new/templates/${row.template.id}`;
            return (
              <tr
                key={`${row.league_id}-${row.template.id}`}
                role="link"
                tabIndex={0}
                aria-label={`View template ${row.template.label}`}
                onClick={() => router.push(href)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    router.push(href);
                  }
                }}
                className="cursor-pointer border-b border-line last:border-0 transition hover:bg-brand/5 focus-visible:bg-brand/5 focus-visible:outline-none"
              >
                <td className="px-3 py-2.5 align-middle">
                  <div className="flex max-w-[14rem] flex-col gap-1">
                    <span className="truncate font-bold text-ink">
                      {row.template.label}
                    </span>
                    <TemplateBadges template={row.template} />
                  </div>
                </td>
                <TemplateTableCell value={row.league_name} />
                <TemplateTableCell value={meta.competitions} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function NumericSizeFilter({
  label,
  value,
  op,
  onValueChange,
  onOpChange,
  ariaValueLabel,
  ariaOpLabel,
  min = 0,
  max = 100,
}: {
  label: string;
  value: string;
  op: TemplateNumericFilterOp;
  onValueChange: (value: string) => void;
  onOpChange: (op: TemplateNumericFilterOp) => void;
  ariaValueLabel: string;
  ariaOpLabel: string;
  min?: number;
  max?: number;
}) {
  return (
    <fieldset className="min-w-0 sm:min-w-[11rem]">
      <legend className="mb-1 text-xs font-semibold text-muted">{label}</legend>
      <div className="flex gap-1.5">
        <Select
          value={op}
          onChange={(e) => onOpChange(e.target.value as TemplateNumericFilterOp)}
          aria-label={ariaOpLabel}
          className={cn(selectCompact, "w-[5.5rem] shrink-0")}
        >
          <option value="eq">Exact</option>
          <option value="min">Min</option>
          <option value="max">Max</option>
        </Select>
        <div className="relative min-w-0 flex-1">
          <Input
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            placeholder="Any"
            value={value}
            onChange={(e) => onValueChange(e.target.value)}
            aria-label={ariaValueLabel}
            className={cn(selectCompact, value.trim() && "pr-9")}
          />
          {value.trim() ? (
            <button
              type="button"
              className="absolute right-1.5 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
              aria-label={`Clear ${label.toLowerCase()} filter`}
              onClick={() => onValueChange("")}
            >
              <XIcon className="size-3.5" />
            </button>
          ) : null}
        </div>
      </div>
    </fieldset>
  );
}

export default function CreateLeaguePage() {
  return (
    <RequireAuth>
      <CreateLeagueHub />
    </RequireAuth>
  );
}

function CreateLeagueHub() {
  const [items, setItems] = useState<CompetitionTemplate[]>();
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [competitionCodes, setCompetitionCodes] = useState<string[]>([]);
  const [recent, setRecent] = useState<RecentTemplateUsage[]>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [filterFeatured, setFilterFeatured] = useState(false);
  const [filterStaff, setFilterStaff] = useState(false);
  const [competitions, setCompetitions] = useState<string[]>([]);
  const [membersValue, setMembersValue] = useState("");
  const [membersOp, setMembersOp] = useState<TemplateNumericFilterOp>("eq");
  const [rosterValue, setRosterValue] = useState("");
  const [rosterOp, setRosterOp] = useState<TemplateNumericFilterOp>("eq");
  const [upsets, setUpsets] = useState<TriFilter>("");
  const [bonuses, setBonuses] = useState<TriFilter>("");

  const members = parseFilterInt(membersValue, 1);
  const roster = parseFilterInt(rosterValue, 0);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    setPage(1);
  }, [
    debouncedQuery,
    filterFeatured,
    filterStaff,
    competitions,
    members,
    membersOp,
    roster,
    rosterOp,
    upsets,
    bonuses,
  ]);

  const listParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    const q = debouncedQuery.trim();
    if (q) params.set("q", q);
    if (filterFeatured) params.set("featured", "true");
    if (filterStaff) params.set("made_by_staff", "true");
    for (const code of competitions) params.append("competition", code);
    if (members != null) {
      params.set("members", String(members));
      params.set("members_op", membersOp);
    }
    if (roster != null) {
      params.set("roster", String(roster));
      params.set("roster_op", rosterOp);
    }
    if (upsets) params.set("upsets", upsets);
    if (bonuses) params.set("bonuses", bonuses);
    return params.toString();
  }, [
    page,
    debouncedQuery,
    filterFeatured,
    filterStaff,
    competitions,
    members,
    membersOp,
    roster,
    rosterOp,
    upsets,
    bonuses,
  ]);

  const loadRecent = useCallback(() => {
    return api<RecentTemplateUsage[]>("/templates/recent").then(setRecent);
  }, []);

  const loadTemplates = useCallback(() => {
    setLoading(true);
    setError("");
    return api<TemplateListResponse>(`/templates?${listParams}`)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setPageSize(res.page_size);
        setCompetitionCodes(res.competition_codes || []);
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [listParams]);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    loadRecent().catch((e) => setError(errorMessage(e)));
  }, [loadRecent]);

  useEffect(() => {
    if (!competitionCodes.length) return;
    const allowed = new Set(competitionCodes.map((c) => c.toUpperCase()));
    setCompetitions((prev) => {
      const next = prev.filter((c) => allowed.has(c.toUpperCase()));
      return next.length === prev.length ? prev : next;
    });
  }, [competitionCodes]);

  const retry = useCallback(() => {
    void loadTemplates();
    void loadRecent().catch((e) => setError(errorMessage(e)));
  }, [loadTemplates, loadRecent]);

  const flagFilterActive = filterFeatured || filterStaff;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const showPager = total > pageSize;
  const advancedFilterCount = [
    members != null,
    roster != null,
    upsets,
    bonuses,
  ].filter(Boolean).length;

  const competitionOptions = useMemo(() => {
    const curated = new Map(
      AVAILABLE_COMPETITIONS.map((c) => [c.code.toUpperCase(), c]),
    );
    return competitionCodes.map((code) => {
      const upper = code.toUpperCase();
      const known = curated.get(upper) || findAvailableCompetition(upper);
      return {
        code: upper,
        label: known?.label || competitionDisplayLabel(upper) || upper,
      };
    });
  }, [competitionCodes]);

  function toggleCompetition(code: string) {
    setCompetitions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  }

  const hasActiveFilters =
    Boolean(query.trim()) ||
    filterFeatured ||
    filterStaff ||
    competitions.length > 0 ||
    members != null ||
    roster != null ||
    Boolean(upsets) ||
    Boolean(bonuses);

  function clearAllFilters() {
    setQuery("");
    setDebouncedQuery("");
    setFilterFeatured(false);
    setFilterStaff(false);
    setCompetitions([]);
    setMembersValue("");
    setMembersOp("eq");
    setRosterValue("");
    setRosterOp("eq");
    setUpsets("");
    setBonuses("");
    setPage(1);
  }

  const advancedFilters = (
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end">
      <NumericSizeFilter
        label="Members"
        value={membersValue}
        op={membersOp}
        onValueChange={setMembersValue}
        onOpChange={setMembersOp}
        ariaValueLabel="Filter by member count"
        ariaOpLabel="Member count comparison"
        min={1}
      />
      <NumericSizeFilter
        label="Roster"
        value={rosterValue}
        op={rosterOp}
        onValueChange={setRosterValue}
        onOpChange={setRosterOp}
        ariaValueLabel="Filter by roster size"
        ariaOpLabel="Roster size comparison"
      />
      <label className="grid min-w-0 gap-1 text-xs font-semibold text-muted sm:min-w-[8.5rem]">
        <span className="flex items-center justify-between gap-2">
          Bonuses
          {bonuses ? (
            <button
              type="button"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted transition hover:bg-surface-2 hover:text-ink"
              aria-label="Clear bonuses filter"
              onClick={() => setBonuses("")}
            >
              <XIcon className="size-3.5" />
            </button>
          ) : null}
        </span>
        <Select
          value={bonuses}
          onChange={(e) => setBonuses(e.target.value as TriFilter)}
          aria-label="Filter by bonuses"
          className={selectCompact}
        >
          <option value="">Any</option>
          <option value="true">Uses bonuses</option>
          <option value="false">No bonuses</option>
        </Select>
      </label>
      <label className="grid min-w-0 gap-1 text-xs font-semibold text-muted sm:min-w-[8.5rem]">
        <span className="flex items-center justify-between gap-2">
          Upsets
          {upsets ? (
            <button
              type="button"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted transition hover:bg-surface-2 hover:text-ink"
              aria-label="Clear upsets filter"
              onClick={() => setUpsets("")}
            >
              <XIcon className="size-3.5" />
            </button>
          ) : null}
        </span>
        <Select
          value={upsets}
          onChange={(e) => setUpsets(e.target.value as TriFilter)}
          aria-label="Filter by upsets"
          className={selectCompact}
        >
          <option value="">Any</option>
          <option value="true">Uses upsets</option>
          <option value="false">No upsets</option>
        </Select>
      </label>
    </div>
  );

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        eyebrow="Step 1"
        title="Create a league"
        description="Open a template to review its settings, then use it, edit it if it’s yours, or copy it."
      />

      {error && <ErrorState error={error} retry={retry} />}

      {recent && recent.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg">Recently used</h2>
          <div
            className={cn(
              "rounded-xl border border-line bg-surface md:hidden",
            )}
          >
            {recent.map((row) => (
              <TemplateMobileRow
                key={`${row.league_id}-${row.template.id}`}
                href={`/leagues/new/templates/${row.template.id}`}
                template={row.template}
                ariaLabel={`View template ${row.template.label}`}
                extra={{ label: "Used in", value: row.league_name }}
                fields="recent"
              />
            ))}
          </div>
          <div className="hidden md:block">
            <RecentDesktopTable rows={recent} />
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-3">
          <h2 className="text-lg"> Templates</h2>

          <div className="flex flex-col gap-2.5">
            <div className="flex flex-col gap-2">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                <div className="relative w-full sm:max-w-xs">
                  <Input
                    type="search"
                    placeholder="Search by name or competition"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Search by name or competition"
                    className={cn(query.trim() && "pr-10")}
                  />
                  {query.trim() ? (
                    <button
                      type="button"
                      className="absolute right-2 top-1/2 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
                      aria-label="Clear search"
                      onClick={() => {
                        setQuery("");
                        setDebouncedQuery("");
                      }}
                    >
                      <XIcon className="size-4" />
                    </button>
                  ) : null}
                </div>
                {hasActiveFilters ? (
                  <button
                    type="button"
                    className={cn(
                      chipBase,
                      "w-fit gap-2 border-line bg-surface text-muted hover:border-brand/40 hover:bg-surface-2 hover:text-ink",
                    )}
                    onClick={clearAllFilters}
                  >
                    <EraserIcon className="size-4" />
                    Clear all filters
                  </button>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Template flags">
                <button
                  type="button"
                  className={cn(
                    chipBase,
                    "gap-1.5",
                    filterFeatured
                      ? "border-brand bg-brand/10 text-brand"
                      : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                  aria-pressed={filterFeatured}
                  onClick={() => setFilterFeatured((v) => !v)}
                >
                  Featured
                  {filterFeatured ? <XIcon className="size-3.5" /> : null}
                </button>
                <button
                  type="button"
                  className={cn(
                    chipBase,
                    "gap-1.5",
                    filterStaff
                      ? "border-brand bg-brand/10 text-brand"
                      : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                  aria-pressed={filterStaff}
                  onClick={() => setFilterStaff((v) => !v)}
                >
                  Made by staff
                  {filterStaff ? <XIcon className="size-3.5" /> : null}
                </button>
              </div>
            </div>

            {competitionOptions.length > 0 && (
              <div
                className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-0.5 sm:flex-wrap sm:overflow-visible"
                role="group"
                aria-label="Filter by competition"
              >
                {competitionOptions.map((comp) => {
                  const active = competitions.includes(comp.code);
                  return (
                    <button
                      key={comp.code}
                      type="button"
                      className={cn(
                        chipBase,
                        "min-h-9 shrink-0 gap-1.5 px-2.5 text-xs",
                        active
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                      )}
                      aria-pressed={active}
                      onClick={() => toggleCompetition(comp.code)}
                    >
                      {comp.label}
                      {active ? <XIcon className="size-3" /> : null}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="sm:hidden">
              <button
                type="button"
                className={cn(
                  chipBase,
                  "w-full justify-between border-line bg-surface text-ink",
                  advancedFilterCount > 0 && "border-brand/40",
                )}
                aria-expanded={moreFiltersOpen}
                onClick={() => setMoreFiltersOpen((v) => !v)}
              >
                <span>
                  More filters
                  {advancedFilterCount > 0 ? ` (${advancedFilterCount})` : ""}
                </span>
                <ChevronDownIcon
                  className={cn(
                    "size-4 transition",
                    moreFiltersOpen && "rotate-180",
                  )}
                />
              </button>
              {moreFiltersOpen ? <div className="mt-2">{advancedFilters}</div> : null}
            </div>

            <div className="hidden sm:block">{advancedFilters}</div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-line bg-surface-2/40 px-3 py-2.5">
          <div className="min-w-0">
            <p className="text-sm font-bold text-ink">Blank league</p>
            <Muted className="text-xs">
              Not seeing anything you like? Create your own league from scratch.
            </Muted>
          </div>
          <Link
            href="/leagues/new/templates/new?flow=league"
            className={iconLinkPrimary}
            aria-label="Start blank league"
            title="Start blank league"
          >
            <PlusIcon />
          </Link>
        </div>

        {loading && !items ? (
          <Loading label="Loading templates" />
        ) : !items?.length ? (
          <Empty
            title={
              total === 0 &&
              !debouncedQuery &&
              !flagFilterActive &&
              !competitions.length &&
              members == null &&
              roster == null &&
              !upsets &&
              !bonuses
                ? "No templates yet"
                : "No matching templates"
            }
          >
            <p>
              {total === 0 &&
              !debouncedQuery &&
              !flagFilterActive &&
              !competitions.length &&
              members == null &&
              roster == null &&
              !upsets &&
              !bonuses
                ? "Start a blank league to build your own template, then set up the league."
                : "Try a different search or clear filters."}
            </p>
          </Empty>
        ) : (
          <>
            <div
              className={cn(
                "rounded-xl border border-line bg-surface md:hidden",
                loading && "opacity-60",
              )}
            >
              {items.map((t) => (
                <TemplateMobileRow
                  key={t.id}
                  href={`/leagues/new/templates/${t.id}`}
                  template={t}
                  ariaLabel={`View template ${t.label}`}
                />
              ))}
            </div>
            <div className={cn("hidden md:block", loading && "opacity-60")}>
              <TemplatesDesktopTable items={items} />
            </div>

            {showPager && (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Muted className="text-sm">
                  Page {page} of {totalPages}
                </Muted>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={cn(
                      chipBase,
                      "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-40",
                    )}
                    disabled={page <= 1 || loading}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className={cn(
                      chipBase,
                      "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-40",
                    )}
                    disabled={page >= totalPages || loading}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </Stack>
  );
}
