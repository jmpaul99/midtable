import Link from "next/link";
import type { ReactNode } from "react";
import type { UUID } from "@/lib/types";
import { cn } from "@/lib/cn";

export function managerHref(leagueId: UUID, managerId: UUID | string | null | undefined) {
  if (!managerId) return null;
  return `/leagues/${leagueId}/managers/${managerId}`;
}

/** Fantasy team / manager name that links to the manager detail page. */
export function ManagerLink({
  leagueId,
  managerId,
  children,
  className,
}: {
  leagueId: UUID;
  managerId?: UUID | string | null;
  children: ReactNode;
  className?: string;
}) {
  const href = managerHref(leagueId, managerId);
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
