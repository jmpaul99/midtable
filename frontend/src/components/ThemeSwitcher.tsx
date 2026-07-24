"use client";

import { THEME_PREFERENCES, useTheme, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/cn";

export function ThemeSwitcher({ className }: { className?: string }) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      className={cn("inline-flex w-full items-center gap-0.5 rounded-xl border border-line bg-surface p-0.5", className)}
      role="group"
      aria-label="Color theme"
    >
      {THEME_PREFERENCES.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => setPreference(item.id as ThemePreference)}
          className={cn(
            "min-h-11 flex-1 rounded-lg px-2.5 py-2 text-sm font-bold transition",
            preference === item.id
              ? "bg-brand text-on-brand shadow-sm"
              : "text-muted hover:bg-surface-2 hover:text-ink",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
