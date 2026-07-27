"use client";

import { FormEvent, useMemo, useState } from "react";
import { formatNumber } from "@/lib/format";
import { Empty } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon, PencilIcon, PlusIcon, TrashIcon, XIcon } from "@/components/ui/icons";
import { Muted, Stack } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Field";
import { slugifyKey, uniqueKey, type BonusTypeDef } from "./types";

export type BonusTypeListItem = BonusTypeDef & {
  /** Stable row id for list keys / inline edit. Defaults to `key` when omitted. */
  id?: string;
};

function rowId(t: BonusTypeListItem, index: number): string {
  return t.id || t.key || `bonus-${index}`;
}

export function BonusTypesListEditor({
  value,
  onChange,
  onCreate,
  onUpdate,
  onDelete,
  readOnly = false,
  emptyHint = "Add types below, or use a template that includes them.",
}: {
  value: BonusTypeListItem[];
  /** Controlled local updates (template wizard). Ignored when persist handlers are set. */
  onChange?: (next: BonusTypeListItem[]) => void;
  /** Persist a new type (commissioner). */
  onCreate?: (item: {
    key: string;
    label: string;
    default_points: number;
    sort_order: number;
  }) => void | Promise<unknown>;
  /** Persist an edit (commissioner). `id` is the row id. */
  onUpdate?: (
    id: string,
    patch: { label: string; default_points: number },
  ) => void | Promise<unknown>;
  /** Persist a delete (commissioner). `id` is the row id. */
  onDelete?: (id: string) => void | Promise<unknown>;
  readOnly?: boolean;
  emptyHint?: string;
}) {
  const sorted = useMemo(
    () =>
      [...value]
        .map((t, index) => ({ t, index, id: rowId(t, index) }))
        .sort(
          (a, b) =>
            (a.t.sort_order ?? 0) - (b.t.sort_order ?? 0) ||
            (a.t.label || "").localeCompare(b.t.label || ""),
        ),
    [value],
  );

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editPoints, setEditPoints] = useState("");
  const [adding, setAdding] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newPoints, setNewPoints] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ id: string; label: string } | null>(
    null,
  );

  const persistMode = Boolean(onCreate || onUpdate || onDelete);

  function startEdit(t: BonusTypeListItem, id: string) {
    setEditingId(id);
    setEditLabel(t.label);
    setEditPoints(String(t.default_points));
  }

  async function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    const label = editLabel.trim();
    if (!label) return;
    const default_points = Number(editPoints);
    setBusy(true);
    try {
      if (persistMode) {
        await onUpdate?.(editingId, { label, default_points });
      } else {
        onChange?.(
          value.map((t, index) =>
            rowId(t, index) === editingId ? { ...t, label, default_points } : t,
          ),
        );
      }
      setEditingId(null);
    } finally {
      setBusy(false);
    }
  }

  async function createType(e: FormEvent) {
    e.preventDefault();
    const label = newLabel.trim();
    if (!label) return;
    const key = uniqueKey(
      slugifyKey(label) || "bonus",
      value.map((t) => t.key),
      undefined,
      "bonus",
    );
    const default_points = Number(newPoints);
    const sort_order = value.length + 1;
    setBusy(true);
    try {
      if (persistMode) {
        await onCreate?.({ key, label, default_points, sort_order });
      } else {
        onChange?.([
          ...value,
          {
            id: `temp-${crypto.randomUUID()}`,
            key,
            label,
            default_points,
            sort_order,
          },
        ]);
      }
      setNewLabel("");
      setNewPoints("");
      setAdding(false);
    } finally {
      setBusy(false);
    }
  }

  async function confirmRemoveType() {
    if (!pendingDelete) return;
    const { id } = pendingDelete;
    setPendingDelete(null);
    setBusy(true);
    try {
      if (persistMode) {
        await onDelete?.(id);
      } else {
        onChange?.(
          value
            .filter((t, index) => rowId(t, index) !== id)
            .map((t, i) => ({ ...t, sort_order: i + 1 })),
        );
      }
      if (editingId === id) setEditingId(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack gap="sm">
      {!sorted.length ? (
        <Empty title="No bonus types yet">{emptyHint}</Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
          {sorted.map(({ t, id }) =>
            editingId === id && !readOnly ? (
              <li key={id} className="bg-surface-2/50 p-3">
                <form className="flex items-center gap-2" onSubmit={saveEdit}>
                  <Input
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    required
                    aria-label="Label"
                    className="min-w-0 flex-1"
                    disabled={busy}
                  />
                  <Input
                    type="number"
                    step="0.5"
                    value={editPoints}
                    onChange={(e) => setEditPoints(e.target.value)}
                    required
                    aria-label="Points"
                    className="w-[5.5rem] shrink-0"
                    disabled={busy}
                  />
                  <IconButton
                    type="submit"
                    label="Save"
                    variant="primary"
                    size="icon-sm"
                    busy={busy}
                  >
                    <CheckIcon className="size-4" />
                  </IconButton>
                  <IconButton
                    type="button"
                    label="Cancel"
                    variant="ghost"
                    size="icon-sm"
                    disabled={busy}
                    onClick={() => setEditingId(null)}
                  >
                    <XIcon className="size-4" />
                  </IconButton>
                </form>
              </li>
            ) : (
              <li
                key={id}
                className="flex flex-col gap-2 bg-surface-2/30 px-3 py-2.5 sm:flex-row sm:items-center"
              >
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-sm">{t.label}</strong>
                  <Muted className="truncate text-xs">
                    {formatNumber(t.default_points)} pts
                  </Muted>
                </div>
                {!readOnly && (
                  <div className="flex gap-1">
                    <IconButton
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      label={`Edit ${t.label}`}
                      disabled={busy}
                      onClick={() => startEdit(t, id)}
                    >
                      <PencilIcon className="size-4" />
                    </IconButton>
                    <IconButton
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      label={`Delete ${t.label}`}
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      disabled={busy}
                      onClick={() => setPendingDelete({ id, label: t.label })}
                    >
                      <TrashIcon className="size-4" />
                    </IconButton>
                  </div>
                )}
              </li>
            ),
          )}
        </ul>
      )}

      {!readOnly &&
        (adding ? (
          <form
            className="flex items-center gap-2 rounded-xl border border-dashed border-line p-3"
            onSubmit={createType}
          >
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Name"
              required
              aria-label="Name"
              className="min-w-0 flex-1"
              disabled={busy}
            />
            <Input
              type="number"
              step="0.5"
              value={newPoints}
              onChange={(e) => setNewPoints(e.target.value)}
              placeholder="Pts"
              required
              aria-label="Points"
              className="w-[5.5rem] shrink-0"
              disabled={busy}
            />
            <IconButton
              type="submit"
              label="Add type"
              variant="primary"
              size="icon-sm"
              busy={busy}
            >
              <PlusIcon className="size-4" />
            </IconButton>
            <IconButton
              type="button"
              label="Cancel"
              variant="ghost"
              size="icon-sm"
              disabled={busy}
              onClick={() => setAdding(false)}
            >
              <XIcon className="size-4" />
            </IconButton>
          </form>
        ) : (
          <div className="flex justify-start">
            <IconButton
              type="button"
              variant="secondary"
              label="Add bonus type"
              disabled={busy}
              onClick={() => setAdding(true)}
            >
              <PlusIcon />
            </IconButton>
          </div>
        ))}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete bonus type?"
        description={
          pendingDelete
            ? `Delete bonus type “${pendingDelete.label}”?`
            : undefined
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmRemoveType()}
      />
    </Stack>
  );
}
