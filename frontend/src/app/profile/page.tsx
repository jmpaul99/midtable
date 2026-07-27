"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage, json } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useToast } from "@/components/ui/ToastProvider";

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileForm />
    </RequireAuth>
  );
}

function ProfileForm() {
  const [me, setMe] = useState<Me>();
  const [displayName, setDisplayName] = useState("");
  const [loadError, setLoadError] = useState("");
  const [validation, setValidation] = useState("");
  const [busy, setBusy] = useState(false);
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

          {validation && <StatusBanner tone="error">{validation}</StatusBanner>}
        </Stack>
      </Card>
    </section>
  );
}
