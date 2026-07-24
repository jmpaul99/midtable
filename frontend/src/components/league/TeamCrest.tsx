import { cn } from "@/lib/cn";

const sizes = {
  sm: "size-7",
  md: "size-9",
  lg: "size-12",
} as const;

/** Club crest with a compact monogram fallback when no image is available. */
export function TeamCrest({
  name,
  crestUrl,
  size = "md",
  className,
}: {
  name?: string | null;
  crestUrl?: string | null;
  size?: keyof typeof sizes;
  className?: string;
}) {
  const monogram = (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() || "")
    .join("");

  if (crestUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={crestUrl}
        alt=""
        className={cn(
          sizes[size],
          "shrink-0 rounded-lg bg-surface object-contain p-0.5",
          className,
        )}
      />
    );
  }

  return (
    <span
      aria-hidden
      className={cn(
        sizes[size],
        "inline-flex shrink-0 items-center justify-center rounded-lg border border-line bg-surface-2 text-[0.65rem] font-extrabold text-muted",
        className,
      )}
    >
      {monogram || "?"}
    </span>
  );
}
