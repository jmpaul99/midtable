"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { TemplateEditor } from "@/components/TemplateEditor";
import type { CompetitionTemplate } from "@/lib/types";
import { PageHeader, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { ErrorState, Loading } from "@/components/ui/State";

function CreateFlowTemplateBody({ id }: { id: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isNew = id === "new";
  const leagueFlow = searchParams.get("flow") === "league";
  const initialEditing = searchParams.get("edit") === "1";
  const [templateLabel, setTemplateLabel] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (isNew) {
      setTemplateLabel("");
      setLoadError("");
      return;
    }
    setLoadError("");
    api<CompetitionTemplate>(`/templates/${id}`)
      .then((item) => setTemplateLabel(item.label))
      .catch((e) => setLoadError(errorMessage(e)));
  }, [id, isNew]);

  const pageTitle = leagueFlow
    ? "Build your template"
    : isNew
      ? "Create template"
      : "Template settings";

  const breadcrumbItems = isNew
    ? [
        { label: "Templates", href: "/leagues/new" },
        { label: leagueFlow ? "Your template" : "New template" },
      ]
    : [
        { label: "Templates", href: "/leagues/new" },
        { label: templateLabel || "Template" },
      ];

  function onSaved(item: CompetitionTemplate) {
    if (!item.id) {
      router.replace("/leagues/new");
      return;
    }
    if (item.label) setTemplateLabel(item.label);
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

  if (loadError) return <ErrorState error={loadError} />;

  return (
    <Stack gap="md" className="animate-in">
      <PageHeader
        breadcrumbs={<Breadcrumbs items={breadcrumbItems} />}
        title={pageTitle}
        description={
          leagueFlow
            ? "Set competitions, scoring, phases, and payouts. When you save, you’ll continue to league setup."
            : isNew
              ? "Competitions, scoring, phases, and payouts for leagues created from this template."
              : "Review the full settings below, then use this template, edit it if you own it, or copy it."
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
