import Link from "next/link";
import type { ReactNode } from "react";
import type { UUID } from "@/lib/types";
import { cn } from "@/lib/cn";

export function teamHref(leagueId: UUID, teamId: UUID | string | null | undefined) {
  if (!teamId) return null;
  return `/leagues/${leagueId}/teams/${teamId}`;
}

/** Inline team name that links to the team page when an id is available. */
export function TeamLink({
  leagueId,
  teamId,
  children,
  className,
}: {
  leagueId: UUID;
  teamId?: UUID | string | null;
  children: ReactNode;
  className?: string;
}) {
  const href = teamHref(leagueId, teamId);
  if (!href) {
    return <span className={className}>{children}</span>;
  }
  return (
    <Link
      href={href}
      className={cn(
        "font-bold text-brand underline decoration-brand/40 underline-offset-2 transition hover:text-brand-dark hover:decoration-brand",
        className,
      )}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </Link>
  );
}
