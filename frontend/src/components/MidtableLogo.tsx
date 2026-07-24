import { cn } from "@/lib/cn";

type MidtableLogoProps = {
  className?: string;
  /** Full wordmark + rank mark, or mark only */
  variant?: "lockup" | "mark";
};

/**
 * Theme-aware Midtable logo. Swaps via `data-theme` on `<html>` so it
 * tracks Matchday / Pitch Night without waiting on client hydration.
 */
export function MidtableLogo({ className, variant = "lockup" }: MidtableLogoProps) {
  const matchday =
    variant === "mark" ? "/brand/mark-matchday.svg" : "/brand/lockup-matchday.svg";
  const pitch =
    variant === "mark" ? "/brand/mark-pitch-night.svg" : "/brand/lockup-pitch-night.svg";

  return (
    <span className={cn("relative inline-flex items-center", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={matchday}
        alt="Midtable"
        className="h-full w-auto [[data-theme=pitch]_&]:hidden"
        draggable={false}
      />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={pitch}
        alt=""
        aria-hidden
        className="hidden h-full w-auto [[data-theme=pitch]_&]:block"
        draggable={false}
      />
    </span>
  );
}
