import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BreadcrumbItem = {
  label: ReactNode;
  href?: string;
};

/** Eyebrow-styled trail: TEMPLATES / NAME */
export function Breadcrumbs({
  items,
  className,
}: {
  items: BreadcrumbItem[];
  className?: string;
}) {
  if (items.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className={cn(
        "mb-1 min-w-0 text-[10px] font-extrabold uppercase tracking-[0.1em] text-brand sm:text-[11px]",
        className,
      )}
    >
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={i} className="flex min-w-0 items-center gap-x-1">
              {i > 0 && (
                <span className="text-brand/50" aria-hidden>
                  /
                </span>
              )}
              {item.href ? (
                <Link
                  href={item.href}
                  className="truncate transition hover:text-ink"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  className={cn("truncate", last && "text-muted")}
                  aria-current={last ? "page" : undefined}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
