import { useId } from "react";
import { cn } from "@/lib/cn";

type MidtableLogoProps = {
  className?: string;
  /** Full stack, rank mark, wordmark, or horizontal nav lockup */
  variant?: "lockup" | "mark" | "wordmark" | "nav";
};

function RankMark({ frameId, className }: { frameId: string; className?: string }) {
  return (
    <g className={className}>
      <rect x="-73" y="12" width="36" height="36" fill="var(--logo-fill)" />
      <rect x="-27" y="-6" width="54" height="54" fill={`url(#${frameId})`} />
      <rect x="-22" y="-1" width="44" height="44" fill="var(--logo-gap)" />
      <rect x="-18" y="3" width="36" height="36" fill="var(--logo-fill)" />
      <rect x="37" y="12" width="36" height="36" fill="var(--logo-fill)" />
    </g>
  );
}

function WordmarkText() {
  return (
    <text
      fontSize="46"
      fontWeight="800"
      letterSpacing="-0.02em"
      fill="var(--logo-wordmark)"
    >
      <tspan x="-95" y="-4">
        Mid
      </tspan>
      <tspan x="-14" y="4">
        table
      </tspan>
    </text>
  );
}

/**
 * Theme-aware Midtable logo rendered as inline SVG so the wordmark
 * uses the same Outfit face as the rest of the app (`--font-display`).
 */
export function MidtableLogo({ className, variant = "lockup" }: MidtableLogoProps) {
  const uid = useId().replace(/:/g, "");
  const frameId = `logo-frame-${uid}`;

  const gradient = (
    <linearGradient id={frameId} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="var(--logo-frame-top)" />
      <stop offset="100%" stopColor="var(--logo-frame-bot)" />
    </linearGradient>
  );

  if (variant === "mark") {
    return (
      <svg
        viewBox="0 0 160 72"
        className={cn("h-full w-auto overflow-visible", className)}
        role="img"
        aria-label="Midtable"
      >
        <defs>{gradient}</defs>
        <g transform="translate(80, 12)">
          <RankMark frameId={frameId} />
        </g>
      </svg>
    );
  }

  if (variant === "wordmark") {
    return (
      <svg
        viewBox="0 0 210 72"
        className={cn("h-full w-auto overflow-visible", className)}
        role="img"
        aria-label="Midtable"
        style={{ fontFamily: "var(--font-display)" }}
      >
        <g transform="translate(105, 42)">
          <WordmarkText />
        </g>
      </svg>
    );
  }

  // Horizontal lockup: box bottoms share the "table" baseline
  if (variant === "nav") {
    return (
      <svg
        viewBox="0 0 380 72"
        className={cn("h-full w-auto overflow-visible", className)}
        role="img"
        aria-label="Midtable"
        style={{ fontFamily: "var(--font-display)" }}
      >
        <defs>{gradient}</defs>
        {/* Mark bottom at y=60 (12+48); table baseline at y=4 → translate y = 56 */}
        <g transform="translate(80, 12)">
          <RankMark frameId={frameId} />
        </g>
        <g transform="translate(272, 56)">
          <WordmarkText />
        </g>
      </svg>
    );
  }

  return (
    <svg
      viewBox="0 0 240 150"
      className={cn("h-full w-auto overflow-visible", className)}
      role="img"
      aria-label="Midtable"
      style={{ fontFamily: "var(--font-display)" }}
    >
      <defs>{gradient}</defs>
      <g transform="translate(120, 48)">
        <WordmarkText />
        <g transform="translate(0, 36)">
          <RankMark frameId={frameId} />
        </g>
      </g>
    </svg>
  );
}
