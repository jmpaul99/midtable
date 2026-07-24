"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function Nav() {
  const { user, loading, isAdmin, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    await signOut();
    router.replace("/");
    router.refresh();
  }

  return (
    <header className="topbar">
      <div className="shell topbar-inner">
        <Link className="brand" href="/">
          <i className="brand-mark" aria-hidden />
          <span>Draft League</span>
        </Link>
        <nav className="nav" aria-label="Primary">
          {!loading && user ? (
            <>
              <Link href="/" className={pathname === "/" ? "active" : undefined}>
                Leagues
              </Link>
              {isAdmin && (
                <Link href="/templates" className={pathname.startsWith("/templates") ? "active" : undefined}>
                  Templates
                </Link>
              )}
              <button type="button" className="secondary" onClick={handleSignOut}>
                Sign out
              </button>
            </>
          ) : (
            !loading && (
              <Link className="button" href="/login">
                Sign in
              </Link>
            )
          )}
        </nav>
      </div>
    </header>
  );
}

export function LeagueNav({ leagueId, role }: { leagueId: string; role?: string }) {
  const pathname = usePathname();
  const commissioner = role === "owner" || role === "commissioner";
  const items = [
    { href: `/leagues/${leagueId}`, label: "Standings", exact: true },
    { href: `/leagues/${leagueId}/draft`, label: "Draft" },
    { href: `/leagues/${leagueId}/roster`, label: "Roster" },
    { href: `/leagues/${leagueId}/matches`, label: "Matches" },
    { href: `/leagues/${leagueId}/stats`, label: "Stats" },
    ...(commissioner ? [{ href: `/leagues/${leagueId}/admin`, label: "Admin" }] : []),
  ];

  return (
    <nav className="tabs league-subnav" aria-label="League sections">
      {items.map((item) => {
        const active = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link key={item.href} href={item.href} className={active ? "active" : undefined}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
