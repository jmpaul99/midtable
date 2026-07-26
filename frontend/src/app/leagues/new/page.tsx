"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { CompetitionTemplate, RecentTemplateUsage } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { PlusIcon } from "@/components/ui/icons";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

const iconLinkPrimary =
  "inline-flex size-11 items-center justify-center rounded-xl bg-brand text-on-brand shadow-sm transition hover:bg-brand-dark";

const chipBase =
  "inline-flex min-h-11 items-center justify-center rounded-xl border px-3 py-2 text-sm font-bold transition";

const templateCard =
  "flex h-full flex-col rounded-xl border border-line bg-surface p-4 shadow-soft transition hover:border-brand/40 hover:bg-surface-2/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

function TemplateBadges({ template }: { template: CompetitionTemplate }) {
  if (!template.featured && !template.made_by_staff) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {template.featured && (
        <span className="rounded-md bg-brand/10 px-2 py-0.5 text-xs font-bold text-brand">
          Featured
        </span>
      )}
      {template.made_by_staff && (
        <span className="rounded-md bg-surface-2 px-2 py-0.5 text-xs font-bold text-muted">
          Made by staff
        </span>
      )}
    </div>
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
  const [recent, setRecent] = useState<RecentTemplateUsage[]>();
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filterFeatured, setFilterFeatured] = useState(false);
  const [filterStaff, setFilterStaff] = useState(false);

  const load = useCallback(() => {
    setError("");
    Promise.all([
      api<CompetitionTemplate[]>("/templates"),
      api<RecentTemplateUsage[]>("/templates/recent"),
    ])
      .then(([templates, recentRows]) => {
        setItems(templates);
        setRecent(recentRows);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.trim().toLowerCase();
    return items.filter((t) => {
      if (filterFeatured && !t.featured) return false;
      if (filterStaff && !t.made_by_staff) return false;
      if (!q) return true;
      return t.label.toLowerCase().includes(q);
    });
  }, [items, query, filterFeatured, filterStaff]);

  const flagFilterActive = filterFeatured || filterStaff;

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        eyebrow="Step 1"
        title="Create a league"
        description="Open a template to review its settings, then use it, edit it if it’s yours, or copy it."
      />

      {error && <ErrorState error={error} retry={load} />}

      {recent && recent.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg">Recently used</h2>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((row) => (
              <li key={`${row.league_id}-${row.template.id}`}>
                <Link
                  href={`/leagues/new/templates/${row.template.id}`}
                  className={templateCard}
                  aria-label={`View template ${row.template.label}`}
                >
                  <div className="min-w-0 flex-1">
                    <h3 className="text-lg">{row.template.label}</h3>
                    <Muted className="mt-1">
                      Used in{" "}
                      <span className="font-bold text-ink">{row.league_name}</span>
                    </Muted>
                    <TemplateBadges template={row.template} />
                  </div>
                  <Muted className="mt-4 text-xs font-semibold">View settings →</Muted>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg">Templates</h2>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              type="search"
              placeholder="Search templates"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search templates by name"
              className="sm:w-56"
            />
            <div className="flex flex-wrap gap-2" role="group" aria-label="Template filters">
              <button
                type="button"
                className={cn(
                  chipBase,
                  !flagFilterActive
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                )}
                aria-pressed={!flagFilterActive}
                onClick={() => {
                  setFilterFeatured(false);
                  setFilterStaff(false);
                }}
              >
                All
              </button>
              <button
                type="button"
                className={cn(
                  chipBase,
                  filterFeatured
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                )}
                aria-pressed={filterFeatured}
                onClick={() => setFilterFeatured((v) => !v)}
              >
                Featured
              </button>
              <button
                type="button"
                className={cn(
                  chipBase,
                  filterStaff
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink",
                )}
                aria-pressed={filterStaff}
                onClick={() => setFilterStaff((v) => !v)}
              >
                Made by staff
              </button>
            </div>
          </div>
        </div>

        {!items ? (
          <Loading label="Loading templates" />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <li className="flex h-full flex-col rounded-xl border border-dashed border-line bg-surface-2/40 p-4">
              <div className="min-w-0 flex-1">
                <h3 className="text-lg">Blank league</h3>
                <Muted className="mt-1">
                  Build your own competitions and scoring, then continue to league setup.
                </Muted>
              </div>
              <div className="mt-4 flex justify-start">
                <Link
                  href="/leagues/new/templates/new?flow=league"
                  className={iconLinkPrimary}
                  aria-label="Start blank league"
                  title="Start blank league"
                >
                  <PlusIcon />
                </Link>
              </div>
            </li>

            {!filtered.length ? (
              <li className="flex h-full flex-col justify-center rounded-xl border border-line bg-surface p-4 sm:col-span-1 lg:col-span-2">
                <Empty title={items.length ? "No matching templates" : "No templates yet"}>
                  <p>
                    {items.length
                      ? "Try a different search or clear filters."
                      : "Start a blank league to build your own template, then set up the league."}
                  </p>
                  {!items.length && (
                    <Link
                      href="/leagues/new/templates/new?flow=league"
                      className={cn(iconLinkPrimary, "mt-3")}
                      aria-label="Start blank league"
                      title="Start blank league"
                    >
                      <PlusIcon />
                    </Link>
                  )}
                </Empty>
              </li>
            ) : (
              filtered.map((t) => (
                <li key={t.id}>
                  <Link
                    href={`/leagues/new/templates/${t.id}`}
                    className={templateCard}
                    aria-label={`View template ${t.label}`}
                  >
                    <div className="min-w-0 flex-1">
                      <h3 className="text-lg">{t.label}</h3>
                      <Muted className="mt-1">
                        {t.draft_style} · {(t.pool_definitions || []).length} competitions
                      </Muted>
                      <TemplateBadges template={t} />
                    </div>
                    <Muted className="mt-4 text-xs font-semibold">View settings →</Muted>
                  </Link>
                </li>
              ))
            )}
          </ul>
        )}
      </section>
    </Stack>
  );
}
