"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { TemplateEditor } from "@/components/TemplateEditor";
import { ErrorState, Loading, Status } from "@/components/State";
import type { CompetitionTemplate } from "@/lib/types";

export default function TemplateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { isAdmin, loading: authLoading } = useAuth();
  const router = useRouter();

  function onSaved(item: CompetitionTemplate) {
    if (id === "new") router.replace(`/templates/${item.id}`);
  }

  return (
    <RequireAuth>
      <div className="stack">
        <div className="row between">
          <Link className="button secondary" href="/templates">
            ← All templates
          </Link>
        </div>
        {authLoading ? (
          <Loading label="Checking permissions" />
        ) : !isAdmin && id === "new" ? (
          <ErrorState error="Administrator access required to create templates." />
        ) : isAdmin ? (
          <TemplateEditor templateId={id} onSaved={onSaved} />
        ) : (
          <TemplateReadonly templateId={id} />
        )}
      </div>
    </RequireAuth>
  );
}

function TemplateReadonly({ templateId }: { templateId: string }) {
  const [item, setItem] = useState<CompetitionTemplate>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<CompetitionTemplate>(`/competition-templates/${templateId}`)
      .then(setItem)
      .catch((e) => setError(errorMessage(e)));
  }, [templateId]);

  if (error) return <ErrorState error={error} />;
  if (!item) return <Loading label="Loading template" />;

  return (
    <section className="panel stack">
      <div className="row between">
        <h1 style={{ fontSize: "2rem", margin: 0 }}>{item.name}</h1>
        <Status value={item.is_active ? "active" : "inactive"} />
      </div>
      <p className="muted">
        {item.code} · {item.provider} · {item.provider_competition_code}
      </p>
      <div className="grid grid-3">
        <div className="panel inset">
          <p className="eyebrow">Teams</p>
          <div className="metric">{item.default_team_count}</div>
        </div>
        <div className="panel inset">
          <p className="eyebrow">Roster size</p>
          <div className="metric">{item.default_roster_size}</div>
        </div>
        <div className="panel inset">
          <p className="eyebrow">Pools</p>
          <div className="metric">{item.pools.length}</div>
        </div>
      </div>
      <div className="stack">
        {item.pools.map((p) => (
          <div className="panel inset" key={p.key}>
            <strong>{p.name}</strong>
            <div className="muted">
              {p.slots_per_member} slots · {p.provider_competition_code}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
