"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireAuth, useAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useToast } from "@/components/ui/ToastProvider";

const DELETE_ACCOUNT_WARNING =
  "This permanently deletes your account, sign-in, and league memberships. Leagues you alone commission that are still setting up or already finished will also be deleted. If you alone commission a league that is drafting or in season, resolve that first by promoting another commissioner or deleting the league.";

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileForm />
    </RequireAuth>
  );
}

function ProfileForm() {
  const router = useRouter();
  const { signOut } = useAuth();
  const [me, setMe] = useState<Me>();
  const [displayName, setDisplayName] = useState("");
  const [loadError, setLoadError] = useState("");
  const [validation, setValidation] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const { toast } = useToast();
  const load = useCallback(() => {
    setLoadError("");
    api<Me>("/auth/me")
      .then((profile) => {
        setMe(profile);
        setDisplayName(profile.display_name);
      })
      .catch((e) => setLoadError(errorMessage(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const name = displayName.trim();
    if (!name) {
      setValidation("Display name is required.");
      return;
    }
    setBusy(true);
    setValidation("");
    try {
      const updated = await api<Me>("/auth/me", json("PATCH", { display_name: name }));
      setMe(updated);
      setDisplayName(updated.display_name);
      toast({ message: "Profile saved." });
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

  async function deleteAccount() {
    setDeleteBusy(true);
    try {
      await api("/auth/me", json("DELETE"));
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 8000,
        dismissible: true,
      });
      setDeleteBusy(false);
      return;
    }
    // Account is already gone; sign-out is best-effort so a local session
    // failure does not look like a failed deletion.
    try {
      await signOut();
    } catch {
      /* ignore */
    }
    router.replace("/");
    router.refresh();
  }
  if (loadError && !me) {
    return <ErrorState error={loadError} retry={load} />;
  }

  if (!me) {
    return <Loading label="Loading profile" />;
  }

  return (
    <section className="mx-auto max-w-md py-2 animate-in">
      <Card>
        <Stack gap="md">
          <div>
            <Eyebrow>Account</Eyebrow>
            <h1 className="text-2xl sm:text-3xl md:text-4xl">Profile</h1>
            <Muted className="mt-1">
              How you appear across leagues. Fantasy team names are set per league on the Roster page.
            </Muted>
          </div>

          <form className="flex flex-col gap-3" onSubmit={submit}>
            <Label>
              Display name
              <Input
                type="text"
                name="display_name"
                autoComplete="nickname"
                required
                maxLength={80}
                minLength={1}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </Label>
            <Label>
              Email
              <Input type="email" value={me.email} disabled readOnly />
            </Label>
            <div className="flex justify-start">
              <IconButton
                type="submit"
                label="Save profile"
                variant="primary"
                busy={busy}
                disabled={!displayName.trim()}
              >
                <SaveIcon />
              </IconButton>
            </div>
          </form>

          <div className="border-t border-line pt-4">
            <p className="text-sm font-semibold text-muted">Appearance</p>
            <Muted className="mt-1 mb-2">
              Follow your device setting, or lock light or dark.
            </Muted>
            <ThemeSwitcher />
          </div>

          <div className="border-t border-line pt-4">
            <p className="text-sm font-semibold text-muted">Delete account</p>
            <Muted className="mt-1 mb-3">
              Permanently remove your account and sign-in. This cannot be undone.
            </Muted>
            <Button
              type="button"
              variant="danger"
              disabled={busy || deleteBusy}
              onClick={() => setDeleteConfirmOpen(true)}
            >
              Delete account
            </Button>
          </div>

          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}
        </Stack>
      </Card>

      <ConfirmDialog
        open={deleteConfirmOpen}
        title="Delete your account?"
        description={DELETE_ACCOUNT_WARNING}
        confirmLabel="Delete account"
        cancelLabel="Keep account"
        tone="danger"
        onCancel={() => setDeleteConfirmOpen(false)}
        onConfirm={() => {
          setDeleteConfirmOpen(false);
          void deleteAccount();
        }}
      />
    </section>
  );
}
