"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { IconButton } from "@/components/ui/IconButton";
import { MidtableLogo } from "@/components/MidtableLogo";
import { LogInIcon, LogOutIcon, MenuIcon, XIcon } from "@/components/ui/icons";
import { LeagueBottomNav, LeagueDesktopTabs, leagueNavItems } from "@/components/ui/BottomNav";

export function Nav() {
  const { user, loading, isAdmin, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  async function handleSignOut() {
    await signOut();
    setOpen(false);
    router.replace("/");
    router.refresh();
  }

  const links = user
    ? [
        ...(isAdmin
          ? [
              {
                href: "/leagues/new",
                label: "Create a league",
                active: pathname.startsWith("/leagues/new"),
              },
            ]
          : []),
        { href: "/profile", label: "Profile", active: pathname.startsWith("/profile") },
      ]
    : [];

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/90 backdrop-blur-md safe-pt">
      <div className="mx-auto flex min-h-14 max-w-[1180px] items-center justify-between gap-3 px-4 sm:min-h-16 sm:px-5 [padding-left:max(1rem,env(safe-area-inset-left))] [padding-right:max(1rem,env(safe-area-inset-right))]">
        <Link
          href="/"
          className="inline-flex h-8 items-center overflow-visible sm:h-9"
          aria-label="Midtable home"
        >
          <MidtableLogo variant="nav" className="h-full" />
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {!loading && user ? (
            <>
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-lg px-3 py-2.5 text-sm font-bold transition",
                    link.active ? "bg-surface-2 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  {link.label}
                </Link>
              ))}
              <IconButton type="button" variant="secondary" label="Sign out" onClick={handleSignOut}>
                <LogOutIcon />
              </IconButton>
            </>
          ) : (
            !loading && (
              <Link
                href="/login"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-on-brand hover:bg-brand-dark"
              >
                <LogInIcon className="size-4" />
                Sign in
              </Link>
            )
          )}
        </nav>

        <div className="md:hidden">
          {!loading && (
            <IconButton
              type="button"
              variant="secondary"
              label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              aria-controls="mobile-menu"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <XIcon /> : <MenuIcon />}
            </IconButton>
          )}
        </div>
      </div>

      {open && (
        <div
          id="mobile-menu"
          className="animate-in border-t border-line bg-bg px-4 py-3 md:hidden [padding-left:max(1rem,env(safe-area-inset-left))] [padding-right:max(1rem,env(safe-area-inset-right))]"
        >
          <div className="flex flex-col gap-1">
            {!loading && user ? (
              <>
                {links.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "rounded-xl px-3 py-3 text-sm font-bold",
                      link.active ? "bg-surface-2 text-ink" : "text-muted",
                    )}
                  >
                    {link.label}
                  </Link>
                ))}
                <div className="pt-1">
                  <IconButton
                    type="button"
                    variant="secondary"
                    label="Sign out"
                    onClick={handleSignOut}
                  >
                    <LogOutIcon />
                  </IconButton>
                </div>
              </>
            ) : (
              !loading && (
                <Link
                  href="/login"
                  onClick={() => setOpen(false)}
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-on-brand"
                >
                  <LogInIcon className="size-4" />
                  Sign in
                </Link>
              )
            )}
          </div>
        </div>
      )}
    </header>
  );
}

export function LeagueNav({
  leagueId,
  role,
  status,
  onTheClock = false,
}: {
  leagueId: string;
  role?: string;
  status?: string;
  onTheClock?: boolean;
}) {
  const commissioner = role === "owner" || role === "commissioner";
  const items = leagueNavItems(leagueId, commissioner, status, onTheClock);
  return (
    <>
      <LeagueDesktopTabs items={items} />
      <LeagueBottomNav items={items} />
    </>
  );
}
