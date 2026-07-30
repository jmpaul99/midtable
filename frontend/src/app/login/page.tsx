"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { ApiError, errorMessage } from "@/lib/api";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Loading, StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { LogInIcon, SendIcon, UserPlusIcon, SpinnerIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import {
  TURNSTILE_ENABLED,
  TurnstileWidget,
  resetTurnstile,
} from "@/components/TurnstileWidget";
import { useToast } from "@/components/ui/ToastProvider";

export default function LoginPage() {
  return (
    <Suspense fallback={<Loading label="Loading sign-in" />}>
      <LoginForm />
    </Suspense>
  );
}

type Step = "email" | "existing" | "register" | "reset" | "check-email";

function LoginForm() {
  const search = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();
  const requestedNext = search.get("next");
  const next =
    requestedNext?.startsWith("/") && !requestedNext.startsWith("//") ? requestedNext : "/";
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [otp, setOtp] = useState("");
  const [pendingDisplayName, setPendingDisplayName] = useState<string | null>(null);
  const [validation, setValidation] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPasswordSignIn, setShowPasswordSignIn] = useState(false);
  const [showPasswordRegister, setShowPasswordRegister] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileWidgetId, setTurnstileWidgetId] = useState<string | null>(null);

  useEffect(() => {
    const urlError = search.get("error");
    if (urlError) {
      toast({
        message: urlError,
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      return;
    }
    if (search.get("reset") === "ok") {
      toast({
        message: "Password updated. Sign in with your new password.",
        tone: "info",
        durationMs: 6000,
        dismissible: true,
      });
    }
    // Run once on mount for query-param feedback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function callbackUrl(path = next) {
    return `${window.location.origin}/auth/callback?next=${encodeURIComponent(path)}`;
  }

  function goToStep(nextStep: Step) {
    setStep(nextStep);
    setValidation("");
    setPassword("");
    if (nextStep !== "check-email") {
      setOtp("");
      setPendingDisplayName(null);
    }
    if (nextStep !== "register") setShowPasswordRegister(false);
    if (nextStep !== "existing" && nextStep !== "reset") setShowPasswordSignIn(false);
  }

  function useDifferentEmail() {
    setStep("email");
    setValidation("");
    setPassword("");
    setDisplayName("");
    setOtp("");
    setPendingDisplayName(null);
    setShowPasswordSignIn(false);
    setShowPasswordRegister(false);
  }

  async function continueWithEmail(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setValidation("");
    try {
      if (TURNSTILE_ENABLED && !turnstileToken) {
        setValidation("Please complete the verification challenge.");
        return;
      }
      const normalized = email.trim().toLowerCase();
      const response = await fetch("/api/auth/email-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: normalized,
          ...(turnstileToken ? { turnstile_token: turnstileToken } : {}),
        }),
        cache: "no-store",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail =
          typeof payload?.detail === "string"
            ? payload.detail
            : `Request failed (${response.status})`;
        throw new ApiError(response.status, detail, payload?.detail);
      }
      setEmail(normalized);
      setTurnstileToken(null);
      resetTurnstile(turnstileWidgetId);
      goToStep(payload.exists ? "existing" : "register");
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      setTurnstileToken(null);
      resetTurnstile(turnstileWidgetId);
    } finally {
      setBusy(false);
    }
  }

  async function signInWithPassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setValidation("");
    try {
      const { error } = await supabase().auth.signInWithPassword({ email, password });
      if (error) throw error;
      router.replace(next);
      router.refresh();
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  async function sendMagicLink(options?: { displayName?: string; resend?: boolean }) {
    setBusy(true);
    setValidation("");
    try {
      const { error } = await supabase().auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: callbackUrl(),
          ...(options?.displayName
            ? { data: { display_name: options.displayName } }
            : {}),
        },
      });
      if (error) throw error;
      setOtp("");
      setPendingDisplayName(options?.displayName ?? null);
      setStep("check-email");
      if (options?.resend) {
        toast({ message: "Code resent. Check your inbox.", tone: "info" });
      }
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  async function verifyEmailOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setValidation("");
    try {
      const token = otp.trim();
      if (!token) {
        setValidation("Enter the one-time code from your email.");
        return;
      }
      const { error } = await supabase().auth.verifyOtp({
        email,
        token,
        type: "email",
      });
      if (error) throw error;
      router.replace(next);
      router.refresh();
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  async function registerWithPassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setValidation("");
    try {
      const name = displayName.trim();
      if (!name) {
        setValidation("Display name is required.");
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
      toast({
        message: "Account created. Check your email to confirm it.",
        tone: "info",
        durationMs: 6000,
        dismissible: true,
      });
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  async function registerWithMagicLink() {
    const name = displayName.trim();
    if (!name) {
      setValidation("Display name is required.");
      return;
    }
    await sendMagicLink({ displayName: name });
  }

  async function resendMagicLink() {
    await sendMagicLink({
      ...(pendingDisplayName ? { displayName: pendingDisplayName } : {}),
      resend: true,
    });
  }

  async function sendReset(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setValidation("");
    try {
      const { error } = await supabase().auth.resetPasswordForEmail(email, {
        redirectTo: callbackUrl("/auth/update-password"),
      });
      if (error) throw error;
      toast({
        message: "Check your inbox for a reset link.",
        tone: "info",
        durationMs: 6000,
        dismissible: true,
      });
    } catch (error) {
      toast({
        message: errorMessage(error),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  const heading =
    step === "reset"
      ? "Reset password"
      : step === "check-email"
        ? "Check your email"
        : step === "register"
          ? "Create account"
          : step === "existing"
            ? "Welcome back"
            : "Sign in";
  const muted =
    step === "reset"
      ? "We will email you a link to choose a new password."
      : step === "check-email"
        ? "We emailed a magic link and a one-time code. Enter the code below, or open the link."
        : step === "register"
          ? "Choose a display name, then we will email a magic link or one-time code to finish signing up."
          : step === "existing"
            ? "We will email a magic link or one-time code to sign in."
            : "Enter your email to continue. Create a league, or join with an invite or shareable link.";

  return (
    <section className="mx-auto flex min-h-[70dvh] max-w-md flex-col items-center justify-center gap-6 py-6 animate-in">
      <MidtableLogo className="h-16 w-auto sm:h-20" />
      <Card className="w-full">
        <Stack gap="md">
          <div>
            <Eyebrow>Welcome</Eyebrow>
            <h1 className="text-3xl sm:text-4xl">{heading}</h1>
            <Muted className="mt-1">{muted}</Muted>
          </div>

          {step === "email" && (
            <form className="flex flex-col gap-3" onSubmit={continueWithEmail}>
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
              {TURNSTILE_ENABLED && (
                <TurnstileWidget
                  action="email-status"
                  onToken={setTurnstileToken}
                  onWidgetId={setTurnstileWidgetId}
                />
              )}
              <Button
                type="submit"
                full
                disabled={busy || (TURNSTILE_ENABLED && !turnstileToken)}
              >
                {busy ? <SpinnerIcon /> : <LogInIcon />}
                {busy ? "Please wait…" : "Continue"}
              </Button>
            </form>
          )}

          {step === "existing" && (
            <form
              className="flex flex-col gap-3"
              onSubmit={
                showPasswordSignIn
                  ? signInWithPassword
                  : (e) => {
                      e.preventDefault();
                      void sendMagicLink();
                    }
              }
            >
              <LockedEmail email={email} onChange={useDifferentEmail} />
              {!showPasswordSignIn && (
                <Button type="submit" full disabled={busy}>
                  {busy ? <SpinnerIcon /> : <SendIcon />}
                  {busy ? "Please wait…" : "Send magic link"}
                </Button>
              )}
              {showPasswordSignIn ? (
                <>
                  <div className="flex flex-col gap-1.5">
                    <Label>
                      Password
                      <Input
                        type="password"
                        minLength={6}
                        autoComplete="current-password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                      />
                    </Label>
                    <button
                      type="button"
                      onClick={() => goToStep("reset")}
                      className="self-end text-sm font-semibold text-brand hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <Button type="submit" full disabled={busy}>
                    {busy ? <SpinnerIcon /> : <LogInIcon />}
                    {busy ? "Please wait…" : "Sign in"}
                  </Button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowPasswordSignIn(false);
                      setPassword("");
                      setValidation("");
                    }}
                    className="text-sm font-semibold text-muted hover:text-ink"
                  >
                    Use a magic link instead
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordSignIn(true);
                    setValidation("");
                  }}
                  className="text-sm font-semibold text-muted hover:text-ink"
                >
                  Or use a password
                </button>
              )}
            </form>
          )}

          {step === "register" && (
            <form
              className="flex flex-col gap-3"
              onSubmit={
                showPasswordRegister
                  ? registerWithPassword
                  : (e) => {
                      e.preventDefault();
                      void registerWithMagicLink();
                    }
              }
            >
              <LockedEmail email={email} onChange={useDifferentEmail} />
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
              {!showPasswordRegister && (
                <Button type="submit" full disabled={busy || !displayName.trim()}>
                  {busy ? <SpinnerIcon /> : <SendIcon />}
                  {busy ? "Please wait…" : "Register with magic link"}
                </Button>
              )}
              {showPasswordRegister ? (
                <>
                  <Label>
                    Password
                    <Input
                      type="password"
                      minLength={6}
                      autoComplete="new-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </Label>
                  <Button type="submit" full disabled={busy || !displayName.trim()}>
                    {busy ? <SpinnerIcon /> : <UserPlusIcon />}
                    {busy ? "Please wait…" : "Create account"}
                  </Button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowPasswordRegister(false);
                      setPassword("");
                      setValidation("");
                    }}
                    className="text-sm font-semibold text-muted hover:text-ink"
                  >
                    Use a magic link instead
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordRegister(true);
                    setValidation("");
                  }}
                  className="text-sm font-semibold text-muted hover:text-ink"
                >
                  Or use a password
                </button>
              )}
            </form>
          )}

          {step === "check-email" && (
            <form className="flex flex-col gap-3" onSubmit={verifyEmailOtp}>
              <LockedEmail email={email} onChange={useDifferentEmail} />
              <Label>
                One-time code
                <Input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={8}
                  required
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\s/g, ""))}
                  placeholder="Code from email"
                />
              </Label>
              <Button type="submit" full disabled={busy || !otp.trim()}>
                {busy ? <SpinnerIcon /> : <LogInIcon />}
                {busy ? "Please wait…" : "Verify code"}
              </Button>
              <button
                type="button"
                onClick={() => void resendMagicLink()}
                disabled={busy}
                className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-50"
              >
                Resend code
              </button>
            </form>
          )}

          {step === "reset" && (
            <form className="flex flex-col gap-3" onSubmit={sendReset}>
              <LockedEmail email={email} onChange={useDifferentEmail} />
              <Button type="submit" full disabled={busy}>
                {busy ? <SpinnerIcon /> : <SendIcon />}
                {busy ? "Please wait…" : "Send reset link"}
              </Button>
              <button
                type="button"
                onClick={() => goToStep("existing")}
                className="text-sm font-semibold text-muted hover:text-ink"
              >
                Back to sign in
              </button>
            </form>
          )}

          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}
        </Stack>
      </Card>
    </section>
  );
}

function LockedEmail({ email, onChange }: { email: string; onChange: () => void }) {
  return (
    <div className="flex flex-col gap-1">
      <Label>
        Email
        <Input type="email" value={email} readOnly autoComplete="email" />
      </Label>
      <button
        type="button"
        onClick={onChange}
        className="self-start text-sm font-semibold text-brand hover:underline"
      >
        Use a different email
      </button>
    </div>
  );
}
