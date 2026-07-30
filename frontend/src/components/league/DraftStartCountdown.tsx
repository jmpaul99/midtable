"use client";

import { useEffect, useState } from "react";
import { formatCountdownDuration, formatDateTimeWithZone } from "@/lib/format";
import { StatusBanner } from "@/components/ui/State";

export function DraftStartCountdown({ scheduledAt }: { scheduledAt: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [scheduledAt]);

  const remaining = new Date(scheduledAt).getTime() - now;
  const overdue = remaining <= 0;

  return (
    <StatusBanner tone={overdue ? "error" : "info"}>
      {overdue ? (
        <>
          <strong>Draft starting soon</strong>
          <div className="mt-1">
            Scheduled for {formatDateTimeWithZone(scheduledAt)}. Waiting for the draft to
            open…
          </div>
        </>
      ) : (
        <>
          <strong>Draft starts in</strong>
          <div
            className="mt-1 font-mono text-2xl font-bold tabular-nums tracking-tight"
            aria-live="polite"
          >
            {formatCountdownDuration(remaining)}
          </div>
          <div className="mt-1 text-muted">{formatDateTimeWithZone(scheduledAt)}</div>
        </>
      )}
    </StatusBanner>
  );
}
