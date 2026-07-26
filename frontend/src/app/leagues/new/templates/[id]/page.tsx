"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use } from "react";
import { RequireAuth } from "@/lib/auth";
import { TemplateEditor } from "@/components/TemplateEditor";
import type { CompetitionTemplate } from "@/lib/types";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";
import { Loading } from "@/components/ui/State";

function CreateFlowTemplateBody({ id }: { id: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isNew = id === "new";
  const leagueFlow = searchParams.get("flow") === "league";

  function onSaved(item: CompetitionTemplate) {
    if (!item.id) {
      router.replace("/leagues/new");
      return;
    }
    if (leagueFlow && (isNew || item.id !== id)) {
      router.replace(`/leagues/new/setup/${item.id}`);
      return;
    }
    if (isNew || item.id !== id) {
      router.replace(`/leagues/new/templates/${item.id}`);
    }
  }

  return (
    <Stack gap="md" className="animate-in">
      <PageHeader
        eyebrow={leagueFlow ? "Step 1 · Your template" : isNew ? "New template" : "Template"}
        title={leagueFlow ? "Build your template" : isNew ? "Create template" : "Template"}
        description={
          leagueFlow
            ? "Set competitions, scoring, phases, and payouts. When you save, you’ll continue to league setup."
            : "Competitions, scoring, phases, and payouts for leagues created from this template. Only the creator can edit; others can use it or copy it."
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
      {!isNew && !leagueFlow && (
        <Muted className="text-sm">
          Ready to launch?{" "}
          <Link
            href={`/leagues/new/setup/${id}`}
            className="font-bold text-brand hover:underline"
          >
            Use this template
          </Link>
        </Muted>
      )}
      <TemplateEditor templateId={id} onSaved={onSaved} />
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
