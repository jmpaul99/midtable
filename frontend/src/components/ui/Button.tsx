import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

const variants = {
  primary: "bg-brand text-on-brand hover:bg-brand-dark shadow-sm",
  secondary: "bg-surface text-ink border border-line hover:bg-surface-2",
  danger: "bg-danger text-white hover:brightness-95",
  ghost: "bg-transparent text-muted hover:bg-surface-2 hover:text-ink",
} as const;

const sizes = {
  md: "min-h-11 px-4 py-2.5 text-[0.95rem]",
  sm: "min-h-9 px-3 py-2 text-sm",
  icon: "size-11 min-h-11 min-w-11 shrink-0 px-0 py-0",
  "icon-sm": "size-9 min-h-9 min-w-9 shrink-0 px-0 py-0",
} as const;

type Variant = keyof typeof variants;
type Size = keyof typeof sizes;

export const Button = forwardRef<
  HTMLButtonElement,
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "size"> & {
    variant?: Variant;
    size?: Size;
    full?: boolean;
    children?: ReactNode;
  }
>(function Button(
  { variant = "primary", size = "md", full, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-bold transition enabled:active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        full && "w-full",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
});
