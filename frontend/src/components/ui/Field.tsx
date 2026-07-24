import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const field =
  "w-full min-h-11 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-base text-ink transition placeholder:text-muted/70 disabled:opacity-50";

export function Label({
  children,
  className,
  htmlFor,
}: {
  children: React.ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <label htmlFor={htmlFor} className={cn("grid gap-1.5 text-sm font-semibold text-muted", className)}>
      {children}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(field, className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(field, "pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(field, "min-h-28 resize-y", className)} {...props} />;
}

export function Checkbox({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className={cn("size-5 shrink-0 rounded border-line accent-brand", className)}
      {...props}
    />
  );
}

export function Switch({
  className,
  size = "md",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & { size?: "sm" | "md" }) {
  const sm = size === "sm";
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center",
        sm ? "h-5 w-9" : "h-7 w-12",
        className,
      )}
    >
      <input
        type="checkbox"
        role="switch"
        className="peer absolute inset-0 z-10 cursor-pointer opacity-0 disabled:cursor-not-allowed"
        {...props}
      />
      <span
        className={cn(
          "pointer-events-none rounded-full bg-surface-2 ring-1 ring-line transition peer-checked:bg-brand peer-checked:ring-brand/40 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand peer-disabled:opacity-50",
          sm ? "h-5 w-9" : "h-7 w-12",
        )}
        aria-hidden
      />
      <span
        className={cn(
          "pointer-events-none absolute rounded-full bg-white shadow-sm ring-1 ring-black/5 transition",
          sm
            ? "left-0.5 top-0.5 size-4 peer-checked:translate-x-4"
            : "left-0.5 top-0.5 size-6 peer-checked:translate-x-5",
        )}
        aria-hidden
      />
    </span>
  );
}
