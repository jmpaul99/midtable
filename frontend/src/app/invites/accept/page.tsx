"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { LeagueSummary } from "@/lib/types";
import { Loading } from "@/components/State";

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<Loading label="Loading invite" />}>
      <RequireAuth>
        <AcceptForm />
      </RequireAuth>
    </Suspense>
  );
}

function AcceptForm() {
  const search = useSearchParams();
  const router = useRouter();
  const token = search.get("token") || "";
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const league = await api<LeagueSummary>(
        "/invites/accept",
        json("POST", {
          token,
          display_name: displayName || null,
        }),
      );
      router.replace(`/leagues/${league.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth">
      <form className="panel auth-card stack" onSubmit={submit}>
        <div>
          <p className="eyebrow">Invite</p>
          <h1 style={{ fontSize: "2rem" }}>Join a league</h1>
          <p className="muted">Your verified email must match the invite.</p>
        </div>
        {!token && <div className="notice error">Missing invite token.</div>}
        <label>
          Display name <span className="muted">(optional)</span>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={80}
          />
        </label>
        <button type="submit" disabled={busy || !token}>
          {busy ? "Joining…" : "Accept invite"}
        </button>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
      </form>
    </section>
  );
}
