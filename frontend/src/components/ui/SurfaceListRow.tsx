import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Shared surface tile used for list rows and compact settings blocks. */
export function SurfaceListRow({
  children,
  className,
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li" | "section";
} & Omit<HTMLAttributes<HTMLElement>, "className" | "children">) {
  return (
    <Tag
      className={cn(
        "rounded-xl border border-line bg-surface-2/50 p-3",
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}
