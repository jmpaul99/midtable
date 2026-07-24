"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { CompetitionTemplate } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "@/components/State";

export default function TemplatesPage() {
  return (
    <RequireAuth>
      <TemplatesList />
    </RequireAuth>
  );
}

function TemplatesList() {
  const { isAdmin } = useAuth();
  const [items, setItems] = useState<CompetitionTemplate[]>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<CompetitionTemplate[]>("/competition-templates")
      .then(setItems)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      <header className="section-head">
        <div>
          <p className="eyebrow">Competition studio</p>
          <h1>Templates</h1>
          <p className="muted">
            {isAdmin
              ? "Define pools, scoring, phases, payouts and draft behavior."
              : "Available competition configurations."}
          </p>
        </div>
        {isAdmin && (
          <Link className="button" href="/templates/new">
            New template
          </Link>
        )}
      </header>

      {error && <ErrorState error={error} retry={load} />}

      {!items ? (
        <Loading label="Loading templates" />
      ) : !items.length ? (
        <Empty title="No templates" />
      ) : (
        <div className="grid grid-3">
          {items.map((t) => (
            <Link key={t.id} href={`/templates/${t.id}`} className="panel stack league-card">
              <div className="row between">
                <h2 style={{ fontSize: "1.25rem", margin: 0 }}>{t.name}</h2>
                <Status value={t.is_active ? "active" : "inactive"} />
              </div>
              <p className="muted">
                {t.provider} · {t.provider_competition_code}
              </p>
              <strong>
                {t.default_team_count} teams · {t.default_roster_size} roster slots
              </strong>
              <small className="muted">{t.code}</small>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
