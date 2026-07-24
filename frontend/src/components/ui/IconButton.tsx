import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { SpinnerIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

type IconButtonSize = "icon" | "icon-sm";

export function IconButton({
  label,
  busy,
  size = "icon",
  variant = "secondary",
  className,
  children,
  disabled,
  ...props
}: Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children" | "aria-label" | "title" | "size"
> & {
  label: string;
  busy?: boolean;
  size?: IconButtonSize;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  children: ReactNode;
}) {
  return (
    <Button
      size={size}
      variant={variant}
      disabled={disabled || busy}
      className={cn(className)}
      {...props}
      aria-label={busy ? `${label} (busy)` : label}
      title={label}
      aria-busy={busy || undefined}
    >
      {busy ? <SpinnerIcon className="size-5" /> : children}
    </Button>
  );
}
