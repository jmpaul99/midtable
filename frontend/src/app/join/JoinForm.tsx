"use client";

import { useEffect, useState } from "react";
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

/** Deduplicate Strict Mode / remount claim attempts for the same token. */
const claimInFlight = new Map<string, Promise<Manager & { league_id: string }>>();

function claimJoinToken(token: string) {
  const existing = claimInFlight.get(token);
  if (existing) return existing;
  const request = api<Manager & { league_id: string }>(
    "/join-links/claim",
    json("POST", { token }),
  ).finally(() => {
    claimInFlight.delete(token);
  });
  claimInFlight.set(token, request);
  return request;
}

export function JoinForm() {
  const search = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();
  const token = search.get("token") || "";
  const [preview, setPreview] = useState<JoinPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [claimError, setClaimError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(Boolean(token));
  const [autoClaimAttempted, setAutoClaimAttempted] = useState(false);

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

  useEffect(() => {
    if (!token || loadingPreview || previewError) return;

    let cancelled = false;
    setBusy(true);
    setClaimError("");
    setAutoClaimAttempted(true);

    claimJoinToken(token)
      .then((out) => {
        if (!cancelled) router.replace(`/leagues/${out.league_id}`);
      })
      .catch((err) => {
        if (cancelled) return;
        const message = errorMessage(err);
        setClaimError(message);
        toast({
          message,
          tone: "error",
          durationMs: 6000,
          dismissible: true,
        });
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, loadingPreview, previewError, router, toast]);

  async function retryClaim() {
    if (!token || busy) return;
    setBusy(true);
    setClaimError("");
    try {
      const out = await claimJoinToken(token);
      router.replace(`/leagues/${out.league_id}`);
    } catch (err) {
      const message = errorMessage(err);
      setClaimError(message);
      toast({
        message,
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      setBusy(false);
    }
  }

  if (token && !previewError && !claimError && (loadingPreview || busy || !autoClaimAttempted)) {
    return (
      <Loading
        label={preview?.league_name ? `Joining ${preview.league_name}` : "Joining league"}
      />
    );
  }

  return (
    <section className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center gap-6 py-6 animate-in">
      <MidtableLogo className="h-16 w-auto sm:h-20" />
      <Card className="w-full">
        <div className="flex flex-col gap-4">
          <div>
            <Eyebrow>Join</Eyebrow>
            <h1 className="text-3xl">
              {preview?.league_name ? preview.league_name : "Join a league"}
            </h1>
            <Muted className="mt-1">
              {preview?.season_label
                ? `${preview.season_label}. Claim a place in the dugout.`
                : "Use a shareable league link to claim a place in the dugout."}
            </Muted>
          </div>
          {!token && <StatusBanner tone="error">Missing join token.</StatusBanner>}
          {previewError && <StatusBanner tone="error">{previewError}</StatusBanner>}
          {claimError && <StatusBanner tone="error">{claimError}</StatusBanner>}
          {token && !previewError && (
            <div className="flex justify-start">
              <IconButton
                type="button"
                label="Join league"
                variant="primary"
                busy={busy}
                onClick={() => void retryClaim()}
              >
                <CheckIcon />
              </IconButton>
            </div>
          )}
        </div>
      </Card>
    </section>
  );
}

export function JoinFormFallback() {
  return <Loading label="Loading join link" />;
}
