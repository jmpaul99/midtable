"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate } from "@/lib/types";
import { Empty, ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CopyIcon, PencilIcon, PlayIcon, PlusIcon } from "@/components/ui/icons";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

const iconLink =
  "inline-flex size-11 items-center justify-center rounded-xl border border-line bg-surface text-ink transition hover:bg-surface-2";
const iconLinkPrimary =
  "inline-flex size-11 items-center justify-center rounded-xl bg-brand text-on-brand shadow-sm transition hover:bg-brand-dark";

export default function CreateLeaguePage() {
  return (
    <RequireAuth>
      <CreateLeagueHub />
    </RequireAuth>
  );
}

function CreateLeagueHub() {
  const { isAdmin } = useAuth();
  const [items, setItems] = useState<CompetitionTemplate[]>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError("");
    api<CompetitionTemplate[]>("/templates")
      .then(setItems)
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
      setMessage(`Duplicated as ${copy.label || copy.key}.`);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  }

  if (!isAdmin) {
    return (
      <ErrorState error="Platform admin access is required to create leagues and manage templates." />
    );
  }

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        eyebrow="Step 1"
        title="Create a league"
        description="Start from a template, build a new one, or create a blank league and configure it later."
        actions={
          <Link
            href="/leagues/new/templates/new"
            className={iconLinkPrimary}
            aria-label="New template"
            title="New template"
          >
            <PlusIcon />
          </Link>
        }
      />

      {error && <ErrorState error={error} retry={load} />}
      {message && <StatusBanner tone="success">{message}</StatusBanner>}

      {!items ? (
        <Loading label="Loading templates" />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <li className="flex h-full flex-col rounded-xl border border-dashed border-line bg-surface-2/40 p-4">
            <div className="min-w-0 flex-1">
              <h2 className="text-lg">Blank league</h2>
              <Muted className="mt-1">
                No template — set name and manager count now, configure competitions and scoring in Commissioner settings.
              </Muted>
            </div>
            <div className="mt-4 flex justify-start">
              <Link
                href="/leagues/new/setup/blank"
                className={iconLink}
                aria-label="Create without template"
                title="Create without template"
              >
                <PlusIcon />
              </Link>
            </div>
          </li>

          {!items.length ? (
            <li className="flex h-full flex-col justify-center rounded-xl border border-line bg-surface p-4 sm:col-span-1 lg:col-span-2">
              <Empty title="No templates yet">
                <p>Create a template to reuse competitions and scoring across seasons.</p>
                <Link
                  href="/leagues/new/templates/new"
                  className={cn(iconLinkPrimary, "mt-3")}
                  aria-label="New template"
                  title="New template"
                >
                  <PlusIcon />
                </Link>
              </Empty>
            </li>
          ) : (
            items.map((t) => (
              <li
                key={t.id}
                className="flex h-full flex-col rounded-xl border border-line bg-surface p-4 shadow-soft"
              >
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg">{t.label}</h2>
                  <Muted className="mt-1">
                    {t.draft_style} · {(t.pool_definitions || []).length} competitions
                  </Muted>
                  <Muted className="mt-2 text-xs">{t.key}</Muted>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link
                    href={`/leagues/new/setup/${t.id}`}
                    className={iconLinkPrimary}
                    aria-label={`Use template ${t.label}`}
                    title="Use template"
                  >
                    <PlayIcon />
                  </Link>
                  <Link
                    href={`/leagues/new/templates/${t.id}`}
                    className={iconLink}
                    aria-label={`Edit ${t.label}`}
                    title="Edit"
                  >
                    <PencilIcon />
                  </Link>
                  <IconButton
                    type="button"
                    variant="secondary"
                    label="Copy template"
                    busy={busyId === t.id}
                    onClick={() => duplicate(t.id)}
                  >
                    <CopyIcon />
                  </IconButton>
                </div>
              </li>
            ))
          )}
        </ul>
      )}
    </Stack>
  );
}
