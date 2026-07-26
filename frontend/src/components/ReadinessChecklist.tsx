"use client";

import type { Readiness } from "@/lib/types";
import { Loading, StatusBanner } from "@/components/ui/State";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

export function ReadinessChecklist({
  readiness,
  readyLabel = "Ready",
  readyDetail = "All blocking checks passed.",
  readyWithWarningsDetail = "warning(s) below — review before continuing.",
  notReadyDetail = "issue(s) to fix before this league is ready.",
  checksSummaryLabel = "Checks",
}: {
  readiness?: Readiness;
  readyLabel?: string;
  readyDetail?: string;
  readyWithWarningsDetail?: string;
  notReadyDetail?: string;
  checksSummaryLabel?: string;
}) {
  const checks = readiness?.checks?.length
    ? readiness.checks
    : [
        ...(readiness?.errors || []).map((detail, i) => ({
          key: `error-${i}`,
          label: detail,
          status: "error" as const,
          detail: null,
        })),
        ...(readiness?.warnings || []).map((detail, i) => ({
          key: `warning-${i}`,
          label: detail,
          status: "warning" as const,
          detail: null,
        })),
      ];
  const blocking = checks.filter((c) => c.status === "error");
  const caution = checks.filter((c) => c.status === "warning");

  if (!readiness) {
    return <Loading label="Checking readiness" />;
  }

  return (
    <>
      <StatusBanner tone={readiness.ready ? "success" : "error"}>
        <strong>
          {readiness.ready
            ? caution.length
              ? "Ready with warnings"
              : readyLabel
            : "Not ready"}
        </strong>
        <div className="mt-1 text-sm">
          {readiness.ready
            ? caution.length
              ? `${caution.length} ${readyWithWarningsDetail}`
              : readyDetail
            : `${blocking.length} ${notReadyDetail}`}
        </div>
      </StatusBanner>

      <details className="group rounded-xl border border-line bg-surface-2/40">
        <summary className="cursor-pointer list-none px-3 py-2.5 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
          <span className="flex items-center justify-between gap-2">
            <span>
              {checksSummaryLabel}
              <Muted className="ml-1.5 font-normal">
                ({checks.length}
                {blocking.length
                  ? ` · ${blocking.length} error${blocking.length === 1 ? "" : "s"}`
                  : ""}
                {caution.length
                  ? ` · ${caution.length} warning${caution.length === 1 ? "" : "s"}`
                  : ""}
                )
              </Muted>
            </span>
            <span className="text-muted transition group-open:rotate-180" aria-hidden>
              ▾
            </span>
          </span>
        </summary>
        <ul className="flex max-h-48 flex-col gap-2 overflow-y-auto overscroll-contain border-t border-line p-3">
          {checks.map((c) => (
            <li key={c.key} className="flex items-start gap-2.5 text-sm">
              <span
                className={cn(
                  "mt-0.5 grid size-5 shrink-0 place-items-center rounded-md text-xs font-extrabold",
                  c.status === "ok" && "bg-brand/15 text-brand",
                  c.status === "error" && "bg-danger/15 text-danger",
                  c.status === "warning" && "bg-warning/15 text-warning",
                )}
                aria-hidden
              >
                {c.status === "ok" ? "✓" : c.status === "error" ? "!" : "·"}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-ink">{c.label}</div>
                {c.detail && <Muted className="text-xs">{c.detail}</Muted>}
              </div>
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}
