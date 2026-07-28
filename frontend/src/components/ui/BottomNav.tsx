"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

export type NavItem = {
  href: string;
  label: string;
  exact?: boolean;
  /** Stronger visual weight — used while the draft is live. */
  emphasized?: boolean;
  /** Extra path prefixes that should mark this item active. */
  alsoActiveFor?: string[];
};

export function leagueNavItems(
  leagueId: string,
  commissioner: boolean,
  leagueStatus?: string,
  onTheClock = false,
): NavItem[] {
  const draftIncomplete =
    leagueStatus === "pre_draft" || leagueStatus === "drafting";
  const draftLive = leagueStatus === "drafting";
  // Hidden by default for members; only show while draft is still open.
  // Commissioners always see Draft.
  const showDraft = commissioner || draftIncomplete;
  const draftOnRight = commissioner && Boolean(leagueStatus) && !draftIncomplete;

  const draftItem: NavItem = {
    href: `/leagues/${leagueId}/draft`,
    label: "Draft",
    emphasized: draftLive || onTheClock,
  };
  const core: NavItem[] = [
    { href: `/leagues/${leagueId}`, label: "Standings", exact: true },
    {
      href: `/leagues/${leagueId}/roster`,
      label: "Rosters",
      alsoActiveFor: [
        `/leagues/${leagueId}/managers`,
        `/leagues/${leagueId}/teams`,
      ],
    },
    { href: `/leagues/${leagueId}/matches`, label: "Matches" },
    { href: `/leagues/${leagueId}/stats`, label: "Stats" },
  ];
  const commissionerItem: NavItem[] = commissioner
    ? [{ href: `/leagues/${leagueId}/admin`, label: "Commissioner" }]
    : [];

  if (!showDraft) return [...core, ...commissionerItem];
  if (draftOnRight) return [...core, ...commissionerItem, draftItem];
  return [draftItem, ...core, ...commissionerItem];
}

function isActive(pathname: string, item: NavItem) {
  if (item.exact) return pathname === item.href;
  if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return true;
  return (item.alsoActiveFor ?? []).some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function LeagueDesktopTabs({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  return (
    <nav
      className="hidden gap-1 overflow-x-auto px-1.5 py-1.5 md:flex md:snap-x"
      aria-label="League sections"
    >
      {items.map((item) => {
        const active = isActive(pathname, item);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "snap-start whitespace-nowrap rounded-xl px-3.5 py-2.5 text-sm font-bold transition min-h-11 inline-flex items-center gap-1.5",
              item.emphasized && !active && "bg-brand text-on-brand shadow-sm hover:bg-brand-dark",
              item.emphasized && active && "bg-brand-dark text-on-brand shadow-sm ring-2 ring-brand/40",
              !item.emphasized && active && "bg-surface text-ink shadow-sm ring-1 ring-line",
              !item.emphasized && !active && "text-muted hover:bg-surface-2 hover:text-ink",
            )}
          >
            {item.emphasized && (
              <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-on-brand" aria-hidden />
            )}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function LeagueBottomNav({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const activeRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    activeRef.current?.scrollIntoView({
      inline: "center",
      block: "nearest",
      behavior: "smooth",
    });
  }, [pathname, items]);

  if (!mounted) return null;

  return createPortal(
    <nav
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/95 backdrop-blur-md md:hidden [padding-left:max(0.25rem,env(safe-area-inset-left))] [padding-right:max(0.25rem,env(safe-area-inset-right))]"
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
      aria-label="League sections"
    >
      <div className="mx-auto flex max-w-3xl gap-1 overflow-x-auto overscroll-x-contain px-2 pt-1.5 snap-x [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {items.map((item) => {
          const active = isActive(pathname, item);
          return (
            <Link
              key={item.href}
              href={item.href}
              ref={active ? activeRef : undefined}
              className={cn(
                "snap-start inline-flex min-h-12 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-1.5 text-sm font-bold transition",
                item.emphasized && "bg-brand text-on-brand shadow-sm",
                !item.emphasized && active && "bg-brand/10 text-brand",
                !item.emphasized && !active && "text-muted",
              )}
            >
              {item.emphasized && (
                <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-on-brand" aria-hidden />
              )}
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>,
    document.body,
  );
}
