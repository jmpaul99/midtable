"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, json } from "@/lib/api";
import type { League } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";

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
  const [completeConfirmOpen, setCompleteConfirmOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const isComplete = league.status === "complete";
  const { toast } = useToast();

  async function completeLeague() {
    setBusy(true);
    try {
      await api(`/leagues/${league.id}/complete`, json("POST"));
      toast({ message: "League marked complete." });
      onSaved?.();
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

  async function deleteLeague() {
    setBusy(true);
    try {
      await api(`/leagues/${league.id}`, json("DELETE"));
      router.push("/");
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      setBusy(false);
    }
  }

  return (
    <Card>
      <Stack>
        <Muted>Mark the league complete or permanently remove it.</Muted>
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
