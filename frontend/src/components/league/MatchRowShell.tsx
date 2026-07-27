"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const SHELL_CLASS = cn(
  "block min-w-0 cursor-pointer rounded-xl border border-line bg-surface-2/50 p-3 transition",
  "hover:border-brand/40 hover:bg-surface active:scale-[0.99] sm:p-3.5",
  "focus-visible:border-brand/40 focus-visible:outline-none",
);

/** Clickable match-row chrome shared by match log and team fixtures. */
export function MatchRowShell({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  const router = useRouter();
  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => router.push(href)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          router.push(href);
        }
      }}
      className={cn(SHELL_CLASS, className)}
    >
      {children}
    </div>
  );
}
