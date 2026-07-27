"use client";

import { FormEvent, useEffect, useState, type ReactNode } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { Manager, UUID } from "@/lib/types";
import { StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon, PencilIcon, XIcon } from "@/components/ui/icons";
import { Muted } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { useToast } from "@/components/ui/ToastProvider";
import { cn } from "@/lib/cn";

export function TeamNameEditor({
  leagueId,
  memberId,
  teamName,
  displayName,
  canEdit,
  titleAs: TitleTag = "h1",
  titleClassName,
  titleContent,
  onSaved,
}: {
  leagueId: UUID;
  memberId: UUID;
  teamName: string;
  displayName?: string | null;
  canEdit: boolean;
  titleAs?: "h1" | "h2" | "h3" | "strong" | "span";
  titleClassName?: string;
  titleContent?: ReactNode;
  onSaved?: (updated: Manager) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(teamName);
  const [busy, setBusy] = useState(false);
  const [validation, setValidation] = useState("");
  const { toast } = useToast();

  useEffect(() => {
    setDraft(teamName);
  }, [teamName]);

  useEffect(() => {
    if (!canEdit) setEditing(false);
  }, [canEdit]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!canEdit) {
      setValidation("Only you or a commissioner can rename this team.");
      return;
    }
    const next = draft.trim();
    if (!next) {
      setValidation("Team name is required.");
      return;
    }
    if (next === teamName) {
      setEditing(false);
      return;
    }
    setBusy(true);
    setValidation("");
    try {
      const updated = await api<Manager>(
        `/leagues/${leagueId}/members/${memberId}`,
        json("PATCH", { team_name: next }),
      );
      setEditing(false);
      toast({ message: "Team name updated." });
      onSaved?.(updated);
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
    <div className="min-w-0">
      {validation && (
        <StatusBanner tone="error" className="mb-2">
          {validation}
        </StatusBanner>
      )}
      {canEdit && editing ? (
        <form className="flex flex-col gap-1.5" onSubmit={save}>
          <div className="flex items-center gap-1.5">
            <Input
              type="text"
              name="team_name"
              maxLength={80}
              required
              autoFocus
              aria-label="Team name"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <IconButton
              type="submit"
              label="Save team name"
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
              onClick={() => {
                setEditing(false);
                setDraft(teamName);
                setValidation("");
              }}
            >
              <XIcon className="size-4" />
            </IconButton>
          </div>
          {displayName ? <Muted className="text-sm">{displayName}</Muted> : null}
        </form>
      ) : (
        <>
          <div className="flex items-center gap-1.5">
            <TitleTag className={cn("min-w-0 truncate font-extrabold leading-snug", titleClassName)}>
              {titleContent ?? teamName}
            </TitleTag>
            {canEdit && (
              <IconButton
                type="button"
                label="Edit team name"
                variant="ghost"
                size="icon-sm"
                onClick={() => setEditing(true)}
              >
                <PencilIcon className="size-4" />
              </IconButton>
            )}
          </div>
          {displayName ? <Muted className="mt-0.5 truncate text-sm">{displayName}</Muted> : null}
        </>
      )}
    </div>
  );
}
