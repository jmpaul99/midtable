"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { errorMessage } from "@/lib/api";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Loading, StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { LogInIcon, SendIcon, UserPlusIcon, SpinnerIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

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
    requestedNext?.startsWith("/") && !requestedNext.startsWith("//") ? requestedNext : "/";
  const [mode, setMode] = useState<"signin" | "signup" | "magic">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
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
        const name = displayName.trim();
        if (!name) {
          setMessage("Display name is required.");
          return;
        }
        const { error } = await supabase().auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: callbackUrl(),
            data: { display_name: name },
          },
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

  return (
    <section className="mx-auto flex min-h-[70dvh] max-w-md flex-col items-center justify-center gap-6 py-6 animate-in">
      <MidtableLogo className="h-16 w-auto sm:h-20" />
      <Card className="w-full">
        <Stack gap="md">
          <div>
            <Eyebrow>Welcome</Eyebrow>
            <h1 className="text-3xl sm:text-4xl">Sign in</h1>
            <Muted className="mt-1">Magic link or password. Leagues remain invite-only.</Muted>
          </div>

          <div className="flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1" role="tablist" aria-label="Authentication method">
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
                className={cn(
                  "min-h-11 flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-bold transition",
                  mode === key ? "bg-surface text-ink shadow-sm" : "text-muted",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <form className="flex flex-col gap-3" onSubmit={submit}>
            {mode === "signup" && (
              <Label>
                Display name
                <Input
                  type="text"
                  name="display_name"
                  autoComplete="nickname"
                  required
                  maxLength={80}
                  minLength={1}
                  placeholder="How you appear in leagues"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </Label>
            )}
            <Label>
              Email
              <Input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Label>
            {mode !== "magic" && (
              <Label>
                Password
                <Input
                  type="password"
                  minLength={6}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Label>
            )}
            <Button type="submit" full disabled={busy}>
              {busy ? (
                <SpinnerIcon />
              ) : mode === "signin" ? (
                <LogInIcon />
              ) : mode === "signup" ? (
                <UserPlusIcon />
              ) : (
                <SendIcon />
              )}
              {busy
                ? "Please wait…"
                : mode === "signin"
                  ? "Sign in"
                  : mode === "signup"
                    ? "Create account"
                    : "Send magic link"}
            </Button>
          </form>

          {message && (
            <StatusBanner
              tone={/error|invalid|failed|missing|required/i.test(message) ? "error" : "info"}
            >
              {message}
            </StatusBanner>
          )}
        </Stack>
      </Card>
    </section>
  );
}
