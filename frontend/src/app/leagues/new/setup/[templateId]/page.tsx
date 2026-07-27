"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { CompetitionTemplate } from "@/lib/types";
import { CreateLeagueForm } from "@/components/CreateLeagueForm";
import { ErrorState, Loading } from "@/components/ui/State";
import { PageHeader, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";

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
        breadcrumbs={
          <Breadcrumbs
            items={[
              { label: "Templates", href: "/leagues/new" },
              {
                label: template?.label || "Template",
                href: `/leagues/new/templates/${templateId}`,
              },
            ]}
          />
        }
        title="League setup"
        description="Confirm season details and load clubs from the template’s competitions. Draft schedule and pick timer are optional — you can set them later in Admin."
      />
      <CreateLeagueForm template={template} templateId={templateId} />
    </Stack>
  );
}
