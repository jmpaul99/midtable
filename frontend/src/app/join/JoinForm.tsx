"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, errorMessage, json } from "@/lib/api";
import type { Manager } from "@/lib/types";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted } from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";

type JoinPreview = {
  league_name: string;
  league_id: string;
  enabled: boolean;
  season_label?: string | null;
};

export function JoinForm() {
  const search = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();
  const token = search.get("token") || "";
  const [preview, setPreview] = useState<JoinPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(Boolean(token));

  useEffect(() => {
    if (!token) {
      setLoadingPreview(false);
      return;
    }
    let cancelled = false;
    setLoadingPreview(true);
    setPreviewError("");
    api<JoinPreview>(`/join-links/preview?token=${encodeURIComponent(token)}`)
      .then((out) => {
        if (!cancelled) setPreview(out);
      })
      .catch((err) => {
        if (!cancelled) setPreviewError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingPreview(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const out = await api<Manager & { league_id: string }>(
        "/join-links/claim",
        json("POST", { token }),
      );
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
            <Eyebrow>Join</Eyebrow>
            <h1 className="text-3xl">
              {preview?.league_name ? preview.league_name : "Join a league"}
            </h1>
            <Muted className="mt-1">
              {preview?.season_label
                ? `${preview.season_label}. Sign in, then claim a place in the dugout.`
                : "Use a shareable league link to claim a place in the dugout."}
            </Muted>
          </div>
          {!token && <StatusBanner tone="error">Missing join token.</StatusBanner>}
          {loadingPreview && <Muted>Checking join link…</Muted>}
          {previewError && <StatusBanner tone="error">{previewError}</StatusBanner>}
          <div className="flex justify-start">
            <IconButton
              type="submit"
              label="Join league"
              variant="primary"
              busy={busy}
              disabled={!token || Boolean(previewError)}
            >
              <CheckIcon />
            </IconButton>
          </div>
        </form>
      </Card>
    </section>
  );
}

export function JoinFormFallback() {
  return <Loading label="Loading join link" />;
}
