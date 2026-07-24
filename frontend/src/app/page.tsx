"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate, LeagueSummary } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "@/components/State";

export default function HomePage() {
  return (
    <RequireAuth>
      <LeagueList />
    </RequireAuth>
  );
}

function LeagueList() {
  const { user } = useAuth();
  const [leagues, setLeagues] = useState<LeagueSummary[]>();
  const [templates, setTemplates] = useState<CompetitionTemplate[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError("");
    Promise.all([
      api<LeagueSummary[]>("/leagues"),
      api<CompetitionTemplate[]>("/competition-templates").catch(() => [] as CompetitionTemplate[]),
    ])
      .then(([list, tpls]) => {
        setLeagues(list);
        setTemplates(tpls.filter((t) => t.is_active));
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createLeague(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreating(true);
    setMessage("");
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const created = await api<LeagueSummary>(
        "/leagues",
        json("POST", {
          name: f.get("name"),
          slug: String(f.get("slug") || "")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, ""),
          template_id: f.get("template_id"),
          season: f.get("season"),
          max_members: Number(f.get("max_members")),
          visibility: f.get("visibility"),
        }),
      );
      setMessage(`Created ${created.name}.`);
      e.currentTarget.reset();
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="stack">
      <header className="section-head">
        <div>
          <p className="eyebrow">Your leagues</p>
          <h1>Draft League</h1>
          <p className="muted">
            Signed in as {user?.email}. Invite-only membership is enforced by the API.
          </p>
        </div>
      </header>

      {error && <ErrorState error={error} retry={load} />}
      {message && <div className="notice">{message}</div>}

      {!leagues ? (
        <Loading label="Loading leagues" />
      ) : !leagues.length ? (
        <Empty title="No leagues yet">
          <p className="muted">Create one below or accept an invite link.</p>
        </Empty>
      ) : (
        <div className="league-list">
          {leagues.map((league) => (
            <Link
              key={league.id}
              href={`/leagues/${league.id}`}
              className="panel league-card"
            >
              <div className="row between">
                <strong>{league.name}</strong>
                <Status value={league.status} />
              </div>
              <div className="muted">
                {league.season} · {league.role} · {league.visibility}
              </div>
            </Link>
          ))}
        </div>
      )}

      <section className="panel stack">
        <h2>Create a league</h2>
        <p className="muted">Requires an active competition template.</p>
        <form className="form-grid" onSubmit={createLeague}>
          <label>
            Name
            <input name="name" required maxLength={160} />
          </label>
          <label>
            Slug
            <input name="slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="my-league" />
          </label>
          <label>
            Template
            <select name="template_id" required>
              <option value="">Choose…</option>
              {templates.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name} ({t.code})
                </option>
              ))}
            </select>
          </label>
          <label>
            Season
            <input name="season" required placeholder="2026" maxLength={20} />
          </label>
          <label>
            Max members
            <input name="max_members" type="number" min={2} max={100} defaultValue={12} required />
          </label>
          <label>
            Visibility
            <select name="visibility" defaultValue="private">
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public</option>
            </select>
          </label>
          <button className="full" type="submit" disabled={creating || !templates.length}>
            {creating ? "Creating…" : "Create league"}
          </button>
        </form>
      </section>
    </div>
  );
}
