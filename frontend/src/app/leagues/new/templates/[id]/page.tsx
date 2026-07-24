"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { TemplateEditor } from "@/components/TemplateEditor";
import { ErrorState, Loading } from "@/components/ui/State";
import type { CompetitionTemplate } from "@/lib/types";
import { Muted, PageHeader, Stack } from "@/components/ui/Card";

export default function CreateFlowTemplatePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { isAdmin, loading: authLoading } = useAuth();
  const router = useRouter();
  const isNew = id === "new";

  function onSaved(item: CompetitionTemplate) {
    if (!item.id) {
      router.replace("/leagues/new");
      return;
    }
    if (isNew) {
      router.replace(`/leagues/new/templates/${item.id}`);
      return;
    }
  }

  return (
    <RequireAuth>
      <Stack gap="md" className="animate-in">
        <PageHeader
          eyebrow={isNew ? "New template" : "Edit template"}
          title={isNew ? "Create template" : "Edit template"}
          description="Competitions, scoring, phases, and payouts for leagues created from this template."
          actions={
            <Link
              href="/leagues/new"
              className="inline-flex min-h-11 items-center justify-center rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-bold text-ink hover:bg-surface-2"
            >
              ← Templates
            </Link>
          }
        />
        {!isNew && (
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
        {authLoading ? (
          <Loading label="Checking permissions" />
        ) : !isAdmin ? (
          <ErrorState error="Platform admin access required to manage templates." />
        ) : (
          <TemplateEditor templateId={id} onSaved={onSaved} />
        )}
      </Stack>
    </RequireAuth>
  );
}
