"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { errorMessage } from "@/lib/api";
import { Loading } from "@/components/State";

export default function LoginPage() {
  return (
    <Suspense fallback={<Loading label="Loading sign-in" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const search = useSearchParams();
  const router = useRouter();
  const requestedNext = search.get("next");
  const next =
    requestedNext?.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/";
  const [mode, setMode] = useState<"signin" | "signup" | "magic">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState(search.get("error") || "");
  const [busy, setBusy] = useState(false);

  function callbackUrl() {
    return `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (mode === "magic") {
        const { error } = await supabase().auth.signInWithOtp({
          email,
          options: { emailRedirectTo: callbackUrl() },
        });
        if (error) throw error;
        setMessage("Magic link sent. Check your inbox.");
      } else if (mode === "signup") {
        const { error } = await supabase().auth.signUp({
          email,
          password,
          options: { emailRedirectTo: callbackUrl() },
        });
        if (error) throw error;
        setMessage("Account created. Check your email to confirm it.");
      } else {
        const { error } = await supabase().auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.replace(next);
        router.refresh();
      }
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function oauth(provider: "google" | "github") {
    setBusy(true);
    setMessage("");
    const { error } = await supabase().auth.signInWithOAuth({
      provider,
      options: { redirectTo: callbackUrl() },
    });
    if (error) {
      setMessage(error.message);
      setBusy(false);
    }
  }

  return (
    <section className="auth">
      <div className="panel auth-card stack">
        <div>
          <p className="eyebrow">Welcome</p>
          <h1 style={{ fontSize: "2.25rem" }}>Sign in</h1>
          <p className="muted">Magic link, password, or OAuth. Leagues remain invite-only.</p>
        </div>

        <div className="oauth">
          <button type="button" className="secondary" disabled={busy} onClick={() => oauth("google")}>
            Google
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => oauth("github")}>
            GitHub
          </button>
        </div>

        <div className="divider">or use email</div>

        <div className="tabs" role="tablist" aria-label="Authentication method">
          {(
            [
              ["signin", "Sign in"],
              ["signup", "Sign up"],
              ["magic", "Magic link"],
            ] as const
          ).map(([key, label]) => (
            <button
              type="button"
              role="tab"
              key={key}
              aria-selected={mode === key}
              onClick={() => setMode(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <form className="stack" onSubmit={submit}>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          {mode !== "magic" && (
            <label>
              Password
              <input
                type="password"
                minLength={6}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          )}
          <button type="submit" disabled={busy}>
            {busy
              ? "Please wait…"
              : mode === "signin"
                ? "Sign in"
                : mode === "signup"
                  ? "Create account"
                  : "Send magic link"}
          </button>
        </form>

        {message && (
          <div
            className={`notice ${/error|invalid|failed|missing/i.test(message) ? "error" : ""}`}
            role="status"
          >
            {message}
          </div>
        )}
      </div>
    </section>
  );
}
