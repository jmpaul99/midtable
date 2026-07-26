"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate, RecentTemplateUsage } from "@/lib/types";
import { Empty, ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CopyIcon, PencilIcon, PlayIcon, PlusIcon } from "@/components/ui/icons";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

const iconLink =
  "inline-flex size-11 items-center justify-center rounded-xl border border-line bg-surface text-ink transition hover:bg-surface-2";
const iconLinkPrimary =
  "inline-flex size-11 items-center justify-center rounded-xl bg-brand text-on-brand shadow-sm transition hover:bg-brand-dark";

const chipBase =
  "inline-flex min-h-11 items-center justify-center rounded-xl border px-3 py-2 text-sm font-bold transition";

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

function TemplateActions({
  template,
  busyId,
  onDuplicate,
}: {
  template: CompetitionTemplate;
  busyId: string | null;
  onDuplicate: (id: string) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <Link
        href={`/leagues/new/setup/${template.id}`}
        className={iconLinkPrimary}
        aria-label={`Use template ${template.label}`}
        title="Use template"
      >
        <PlayIcon />
      </Link>
      {template.can_edit ? (
        <Link
          href={`/leagues/new/templates/${template.id}`}
          className={iconLink}
          aria-label={`Edit ${template.label}`}
          title="Edit"
        >
          <PencilIcon />
        </Link>
      ) : null}
      <IconButton
        type="button"
        variant="secondary"
        label="Copy template"
        busy={busyId === template.id}
        onClick={() => onDuplicate(template.id)}
      >
        <CopyIcon />
      </IconButton>
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
  const router = useRouter();
  const [items, setItems] = useState<CompetitionTemplate[]>();
  const [recent, setRecent] = useState<RecentTemplateUsage[]>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
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

  async function duplicate(id: string) {
    setBusyId(id);
    setMessage("");
    setError("");
    try {
      const copy = await api<CompetitionTemplate>(`/templates/${id}/duplicate`, json("POST"));
      setMessage(`Copied as ${copy.label}. You can edit your copy.`);
      if (copy.id) {
        router.push(`/leagues/new/templates/${copy.id}`);
        return;
      }
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  }

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
        description="Pick a template to reuse, or start blank to build your own competitions and scoring first."
      />

      {error && <ErrorState error={error} retry={load} />}
      {message && <StatusBanner tone="success">{message}</StatusBanner>}

      {recent && recent.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg">Recently used</h2>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((row) => (
              <li
                key={`${row.league_id}-${row.template.id}`}
                className="flex h-full flex-col rounded-xl border border-line bg-surface p-4 shadow-soft"
              >
                <div className="min-w-0 flex-1">
                  <h3 className="text-lg">{row.template.label}</h3>
                  <Muted className="mt-1">
                    Used in{" "}
                    <Link
                      href={`/leagues/${row.league_id}`}
                      className="font-bold text-ink hover:underline"
                    >
                      {row.league_name}
                    </Link>
                  </Muted>
                  <TemplateBadges template={row.template} />
                </div>
                <TemplateActions
                  template={row.template}
                  busyId={busyId}
                  onDuplicate={duplicate}
                />
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
                <li
                  key={t.id}
                  className="flex h-full flex-col rounded-xl border border-line bg-surface p-4 shadow-soft"
                >
                  <div className="min-w-0 flex-1">
                    <h3 className="text-lg">{t.label}</h3>
                    <Muted className="mt-1">
                      {t.draft_style} · {(t.pool_definitions || []).length} competitions
                    </Muted>
                    <TemplateBadges template={t} />
                  </div>
                  <TemplateActions template={t} busyId={busyId} onDuplicate={duplicate} />
                </li>
              ))
            )}
          </ul>
        )}
      </section>
    </Stack>
  );
}
