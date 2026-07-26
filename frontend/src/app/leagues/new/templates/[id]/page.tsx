"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use } from "react";
import { RequireAuth } from "@/lib/auth";
import { TemplateEditor } from "@/components/TemplateEditor";
import type { CompetitionTemplate } from "@/lib/types";
import { PageHeader, Stack } from "@/components/ui/Card";
import { Loading } from "@/components/ui/State";

function CreateFlowTemplateBody({ id }: { id: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isNew = id === "new";
  const leagueFlow = searchParams.get("flow") === "league";
  const initialEditing = searchParams.get("edit") === "1";

  function onSaved(item: CompetitionTemplate) {
    if (!item.id) {
      router.replace("/leagues/new");
      return;
    }
    // New template in league flow → continue to setup
    if (leagueFlow && (isNew || item.id !== id)) {
      router.replace(`/leagues/new/setup/${item.id}`);
      return;
    }
    // Copied template → open the copy ready to edit
    if (isNew || item.id !== id) {
      router.replace(`/leagues/new/templates/${item.id}?edit=1`);
      return;
    }
    // Saved in place — drop ?edit=1 so we return to view mode
    if (searchParams.get("edit") === "1") {
      router.replace(`/leagues/new/templates/${item.id}`);
    }
  }

  return (
    <Stack gap="md" className="animate-in">
      <PageHeader
        eyebrow={leagueFlow ? "Step 1 · Your template" : isNew ? "New template" : "Template"}
        title={
          leagueFlow
            ? "Build your template"
            : isNew
              ? "Create template"
              : "Template settings"
        }
        description={
          leagueFlow
            ? "Set competitions, scoring, phases, and payouts. When you save, you’ll continue to league setup."
            : isNew
              ? "Competitions, scoring, phases, and payouts for leagues created from this template."
              : "Review the full settings below, then use this template, edit it if you own it, or copy it."
        }
        actions={
          <Link
            href="/leagues/new"
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-bold text-ink hover:bg-surface-2"
          >
            ← Templates
          </Link>
        }
      />
      <TemplateEditor
        templateId={id}
        onSaved={onSaved}
        useHref={isNew ? undefined : `/leagues/new/setup/${id}`}
        initialEditing={initialEditing}
      />
    </Stack>
  );
}

export default function CreateFlowTemplatePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <RequireAuth>
      <Suspense fallback={<Loading label="Loading template" />}>
        <CreateFlowTemplateBody id={id} />
      </Suspense>
    </RequireAuth>
  );
}
