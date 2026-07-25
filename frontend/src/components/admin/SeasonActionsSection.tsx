"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, json } from "@/lib/api";
import type { League } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { StatusBanner } from "@/components/ui/State";
import { Card, Muted, Stack } from "@/components/ui/Card";

const COMPLETE_LEAGUE_WARNING =
  "Completing this league marks the season as finished. It will sort below open leagues and no longer block starting a new season from the same template. You can still view standings and history afterward.";

const DELETE_LEAGUE_WARNING =
  "Deleting this league permanently removes the season, managers, draft, fixtures, scores, and invites. This cannot be undone.";

export function SeasonActionsSection({
  league,
  onSaved,
}: {
  league: League;
  onSaved?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [completeConfirmOpen, setCompleteConfirmOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const isComplete = league.status === "complete";

  async function completeLeague() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}/complete`, json("POST"));
      setMessage("League marked complete.");
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteLeague() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}`, json("DELETE"));
      router.push("/");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Card>
      <Stack>
        <Muted>Finish the season or permanently remove this league.</Muted>
        {error && <StatusBanner tone="error">{error}</StatusBanner>}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button
            type="button"
            variant="secondary"
            disabled={busy || isComplete}
            onClick={() => setCompleteConfirmOpen(true)}
          >
            {isComplete ? "League complete" : "Complete league"}
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={busy}
            onClick={() => setDeleteConfirmOpen(true)}
          >
            Delete league
          </Button>
        </div>

        <ConfirmDialog
          open={completeConfirmOpen}
          title="Complete this league?"
          description={COMPLETE_LEAGUE_WARNING}
          confirmLabel="Complete league"
          cancelLabel="Keep league open"
          tone="warning"
          onCancel={() => setCompleteConfirmOpen(false)}
          onConfirm={() => {
            setCompleteConfirmOpen(false);
            void completeLeague();
          }}
        />
        <ConfirmDialog
          open={deleteConfirmOpen}
          title="Delete this league?"
          description={DELETE_LEAGUE_WARNING}
          confirmLabel="Delete league"
          cancelLabel="Keep league"
          tone="danger"
          onCancel={() => setDeleteConfirmOpen(false)}
          onConfirm={() => {
            setDeleteConfirmOpen(false);
            void deleteLeague();
          }}
        />
      </Stack>
    </Card>
  );
}
