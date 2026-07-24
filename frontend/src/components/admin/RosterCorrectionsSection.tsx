"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, RosterRow, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { EraserIcon, UndoIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";

type HealthInfo = { dev_tools_enabled?: boolean };

export function RosterCorrectionsSection({
  league,
  onChanged,
}: {
  league: League;
  onChanged?: () => void;
}) {
  const [rows, setRows] = useState<RosterRow[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [devTools, setDevTools] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);

  const load = useCallback(() => {
    api<RosterRow[]>(`/leagues/${league.id}/rosters`)
      .then(setRows)
      .catch((e) => setError(errorMessage(e)));
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
    setError("");
    setMessage("");
    try {
      const res = await api<{ undone_pick_number: number }>(
        `/leagues/${league.id}/draft/picks/last`,
        { method: "DELETE" },
      );
      setMessage(`Undid pick #${res.undone_pick_number}.`);
      load();
      onChanged?.();
    } catch (e) {
      setError(errorMessage(e));
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
    setError("");
    setMessage("");
    setResetBusy(true);
    try {
      await api(`/leagues/${league.id}/draft/reset`, { method: "POST" });
      setMessage("Draft reset. League is back in pre-draft.");
      load();
      onChanged?.();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setResetBusy(false);
    }
  }

  async function reassign(entryId: UUID, memberId: UUID) {
    if (!confirm("Reassign this team to a different manager?")) return;
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}/rosters/${entryId}`, json("PATCH", { member_id: memberId }));
      setMessage("Roster ownership updated.");
      load();
      onChanged?.();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const filled = rows.filter((r) => r.id && r.team_id);

  return (
    <Card>
      <Stack>
        <Muted>
          While drafting, undo the last pick. After the draft completes, reassign ownership (points
          follow the roster).
        </Muted>
        {error && <StatusBanner tone="error">{error}</StatusBanner>}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}
        <div className="flex justify-start gap-2">
          <IconButton type="button" label="Undo last draft pick" variant="primary" onClick={undoLast}>
            <UndoIcon />
          </IconButton>
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
