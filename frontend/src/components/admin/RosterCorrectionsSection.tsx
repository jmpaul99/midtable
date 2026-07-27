"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, RosterRow, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { EraserIcon, UndoIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { useToast } from "@/components/ui/ToastProvider";

type HealthInfo = { dev_tools_enabled?: boolean };

export function RosterCorrectionsSection({
  league,
  onChanged,
}: {
  league: League;
  onChanged?: () => void;
}) {
  const [rows, setRows] = useState<RosterRow[]>([]);
  const [loadError, setLoadError] = useState("");
  const [devTools, setDevTools] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const { toast } = useToast();

  const load = useCallback(() => {
    api<RosterRow[]>(`/leagues/${league.id}/rosters`)
      .then((data) => {
        setRows(data);
        setLoadError("");
      })
      .catch((e) => setLoadError(errorMessage(e)));
  }, [league.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api<HealthInfo>("/health")
      .then((h) => setDevTools(Boolean(h.dev_tools_enabled)))
      .catch(() => setDevTools(false));
  }, []);

  async function undoLast() {
    try {
      const res = await api<{ undone_pick_number: number }>(
        `/leagues/${league.id}/draft/picks/last`,
        { method: "DELETE" },
      );
      toast({ message: `Undid pick #${res.undone_pick_number}.` });
      load();
      onChanged?.();
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  async function resetDraft() {
    if (
      !confirm(
        "Reset draft? This clears all picks and draft rosters, returns the league to pre-draft, and keeps draft order and preassigns. Scoring data is not cleared.",
      )
    ) {
      return;
    }
    setResetBusy(true);
    try {
      await api(`/leagues/${league.id}/draft/reset`, { method: "POST" });
      toast({ message: "Draft reset. League is back in pre-draft." });
      load();
      onChanged?.();
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setResetBusy(false);
    }
  }

  async function reassign(entryId: UUID, memberId: UUID) {
    if (!confirm("Reassign this team to a different manager?")) return;
    try {
      await api(`/leagues/${league.id}/rosters/${entryId}`, json("PATCH", { member_id: memberId }));
      toast({ message: "Roster ownership updated." });
      load();
      onChanged?.();
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  const filled = rows.filter((r) => r.id && r.team_id);
  const lastPick = filled
    .filter((r) => r.draft_pick_number != null)
    .sort((a, b) => (b.draft_pick_number ?? 0) - (a.draft_pick_number ?? 0))[0];
  const canUndo = Boolean(lastPick);

  return (
    <Card>
      <Stack>
        <div>
          <h2>Fix picks</h2>
          <Muted>
            Undo reverses the most recent draft selection. After the draft, reassign ownership here
            (points stay with the roster).
          </Muted>
        </div>
        {loadError && (
          <Muted className="text-danger">{loadError}</Muted>
        )}
        <div className="flex flex-wrap items-center justify-start gap-2">
          <Button type="button" variant="primary" disabled={!canUndo} onClick={undoLast}>
            <UndoIcon />
            {lastPick?.team_name
              ? `Undo pick #${lastPick.draft_pick_number}: ${lastPick.team_name}`
              : "Undo last pick"}
          </Button>
          {devTools && (
            <IconButton
              type="button"
              label="Reset draft (dev)"
              variant="danger"
              busy={resetBusy}
              onClick={resetDraft}
            >
              <EraserIcon />
            </IconButton>
          )}
        </div>
        <Stack gap="sm">
          {filled.map((r) => (
            <div
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface-2/50 p-3"
              key={r.id}
            >
              <div>
                <strong>{r.team_name}</strong>
                <Muted>
                  {r.display_name} · {r.pool_name} · {r.acquired_via}
                </Muted>
              </div>
              <Label>
                Owner
                <Select
                  value={r.member_id}
                  onChange={(e) => r.id && reassign(r.id, e.target.value)}
                >
                  {league.members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {managerLabel(m, m.id)}
                    </option>
                  ))}
                </Select>
              </Label>
            </div>
          ))}
        </Stack>
      </Stack>
    </Card>
  );
}
