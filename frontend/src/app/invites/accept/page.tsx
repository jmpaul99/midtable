"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { Manager } from "@/lib/types";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted } from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";

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
  const { toast } = useToast();
  const token = search.get("token") || "";
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const out = await api<Manager & { league_id: string }>("/invites/accept", json("POST", { token }));
      router.replace(`/leagues/${out.league_id}`);
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center gap-6 py-6 animate-in">
      <MidtableLogo className="h-16 w-auto sm:h-20" />
      <Card className="w-full">
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div>
            <Eyebrow>Invite</Eyebrow>
            <h1 className="text-3xl">Join a league</h1>
            <Muted className="mt-1">Your verified email must match the invite.</Muted>
          </div>
          {!token && <StatusBanner tone="error">Missing invite token.</StatusBanner>}
          <div className="flex justify-start">
            <IconButton
              type="submit"
              label="Accept invite"
              variant="primary"
              busy={busy}
              disabled={!token}
            >
              <CheckIcon />
            </IconButton>
          </div>
        </form>
      </Card>
    </section>
  );
}
