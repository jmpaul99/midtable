"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, errorMessage, json } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input, Label, Textarea } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/State";

export type RankingCatalogOption = {
  id: string;
  key: string;
  label: string;
  kind: string;
  source: string;
  as_of?: string | null;
};

export function CustomRankingListModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (catalog: RankingCatalogOption) => void;
}) {
  const titleId = useId();
  const labelRef = useRef<HTMLInputElement>(null);
  const [label, setLabel] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLabel("");
    setText("");
    setError("");
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    labelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<RankingCatalogOption>(
        "/ranking-catalogs",
        json("POST", { label: label.trim(), text }),
      );
      onCreated(created);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <button
        type="button"
        aria-label="Dismiss"
        className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex w-full max-w-lg flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-lg"
        onSubmit={submit}
      >
        <h2 id={titleId} className="font-display text-lg font-extrabold text-ink">
          Custom ranking list
        </h2>
        <p className="text-sm text-muted">
          Paste a ranked list (one team per line, or <code>1,Team</code>). Only you can reuse this
          list.
        </p>
        {error && <ErrorState error={error} />}
        <Label>
          Name
          <Input
            ref={labelRef}
            required
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="My tournament rankings"
          />
        </Label>
        <Label>
          Rankings
          <Textarea
            required
            rows={10}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"1,Argentina\n2,France\n3,England"}
            className="font-mono text-sm"
          />
        </Label>
        <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Saving…" : "Save list"}
          </Button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
