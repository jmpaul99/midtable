"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { errorMessage } from "@/lib/api";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Loading, StatusBanner } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { LockIcon, SpinnerIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { useToast } from "@/components/ui/ToastProvider";
import { useAuth } from "@/lib/auth";

export default function UpdatePasswordPage() {
  const router = useRouter();
  const { session, loading } = useAuth();
  const { toast } = useToast();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [validation, setValidation] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!session) {
      router.replace("/login?error=" + encodeURIComponent("Reset link is missing or expired. Request a new one."));
    }
  }, [loading, session, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setValidation("Passwords do not match.");
      return;
    }
    setBusy(true);
    setValidation("");
    try {
      const { error } = await supabase().auth.updateUser({ password });
      if (error) throw error;
      router.replace("/login?reset=ok");
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

  if (loading || !session) {
    return <Loading label="Checking reset session" />;
  }

  return (
    <section className="mx-auto flex min-h-[70dvh] max-w-md flex-col items-center justify-center gap-6 py-6 animate-in">
      <MidtableLogo className="h-16 w-auto sm:h-20" />
      <Card className="w-full">
        <Stack gap="md">
          <div>
            <Eyebrow>Account</Eyebrow>
            <h1 className="text-3xl sm:text-4xl">Choose a new password</h1>
            <Muted className="mt-1">Pick a password you will remember for Midtable.</Muted>
          </div>

          <form className="flex flex-col gap-3" onSubmit={submit}>
            <Label>
              New password
              <Input
                type="password"
                minLength={6}
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Label>
            <Label>
              Confirm password
              <Input
                type="password"
                minLength={6}
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </Label>
            <Button type="submit" full disabled={busy}>
              {busy ? <SpinnerIcon /> : <LockIcon />}
              {busy ? "Please wait…" : "Update password"}
            </Button>
          </form>

          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}
        </Stack>
      </Card>
    </section>
  );
}
