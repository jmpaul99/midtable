"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { use } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { CompetitionTemplate } from "@/lib/types";
import { CreateLeagueForm } from "@/components/CreateLeagueForm";
import { ErrorState, Loading } from "@/components/ui/State";
import { PageHeader, Stack } from "@/components/ui/Card";

export default function CreateLeagueSetupPage({
  params,
}: {
  params: Promise<{ templateId: string }>;
}) {
  const { templateId } = use(params);
  const blank = templateId === "blank";

  return (
    <RequireAuth>
      <SetupBody templateId={blank ? null : templateId} blank={blank} />
    </RequireAuth>
  );
}

function SetupBody({ templateId, blank }: { templateId: string | null; blank: boolean }) {
  const { isAdmin, loading: authLoading } = useAuth();
  const [template, setTemplate] = useState<CompetitionTemplate | null>();
  const [error, setError] = useState("");

  useEffect(() => {
    if (blank) {
      setTemplate(null);
      return;
    }
    if (!templateId) return;
    setTemplate(undefined);
    setError("");
    api<CompetitionTemplate>(`/templates/${templateId}`)
      .then(setTemplate)
      .catch((e) => setError(errorMessage(e)));
  }, [blank, templateId]);

  if (authLoading) return <Loading label="Checking permissions" />;
  if (!isAdmin) {
    return (
      <ErrorState error="Platform admin access is required to create leagues." />
    );
  }
  if (error) return <ErrorState error={error} />;
  if (!blank && template === undefined) return <Loading label="Loading template" />;

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        eyebrow="Step 2"
        title="League setup"
        description={
          blank
            ? "Name the league and set how many managers. Add competitions later in Commissioner settings."
            : "Confirm season details and load clubs from the template’s competitions."
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
      <CreateLeagueForm template={template ?? null} templateId={templateId} />
    </Stack>
  );
}
