"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { RequireAuth } from "@/lib/auth";
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

  return (
    <RequireAuth>
      <SetupBody templateId={templateId} />
    </RequireAuth>
  );
}

function SetupBody({ templateId }: { templateId: string }) {
  const router = useRouter();
  const blank = templateId === "blank";
  const [template, setTemplate] = useState<CompetitionTemplate | null>();
  const [error, setError] = useState("");

  useEffect(() => {
    if (blank) {
      router.replace("/leagues/new/templates/new?flow=league");
    }
  }, [blank, router]);

  useEffect(() => {
    if (blank) return;
    setTemplate(undefined);
    setError("");
    api<CompetitionTemplate>(`/templates/${templateId}`)
      .then(setTemplate)
      .catch((e) => setError(errorMessage(e)));
  }, [blank, templateId]);

  if (blank) return <Loading label="Starting blank league" />;
  if (error) return <ErrorState error={error} />;
  if (template === undefined) return <Loading label="Loading template" />;

  return (
    <Stack gap="lg" className="animate-in">
      <PageHeader
        eyebrow="Step 2"
        title="League setup"
        description="Confirm season details and load clubs from the template’s competitions."
        actions={
          <Link
            href="/leagues/new"
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-bold text-ink hover:bg-surface-2"
          >
            ← Templates
          </Link>
        }
      />
      <CreateLeagueForm template={template} templateId={templateId} />
    </Stack>
  );
}
