"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const THEME_STORAGE_KEY = "midtable-theme";

export const THEME_PREFERENCES = [
  { id: "system", label: "System" },
  { id: "matchday", label: "Light" },
  { id: "pitch", label: "Dark" },
] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number]["id"];
export type ResolvedTheme = "matchday" | "pitch";

const PREFERENCE_IDS = new Set<string>(THEME_PREFERENCES.map((t) => t.id));

export function isThemePreference(value: string | null | undefined): value is ThemePreference {
  return !!value && PREFERENCE_IDS.has(value);
}

/** Resolve stored value; legacy `signal` maps to pitch. Missing → system. */
export function resolvePreference(value: string | null | undefined): ThemePreference {
  if (value === "signal") return "pitch";
  if (isThemePreference(value)) return value;
  return "system";
}

export function systemResolvedTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "matchday";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "pitch" : "matchday";
}

export function resolveAppliedTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return systemResolvedTheme();
  return preference;
}

export function applyTheme(theme: ResolvedTheme) {
  document.documentElement.setAttribute("data-theme", theme);
}

type ThemeContextValue = {
  preference: ThemePreference;
  theme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [theme, setThemeState] = useState<ResolvedTheme>("matchday");

  const syncApplied = useCallback((pref: ThemePreference) => {
    const applied = resolveAppliedTheme(pref);
    setThemeState(applied);
    applyTheme(applied);
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    const resolved = resolvePreference(stored);
    setPreferenceState(resolved);
    syncApplied(resolved);
    if (stored === "signal") {
      window.localStorage.setItem(THEME_STORAGE_KEY, "pitch");
    }
  }, [syncApplied]);

  useEffect(() => {
    if (preference !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => syncApplied("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference, syncApplied]);

  const setPreference = useCallback(
    (next: ThemePreference) => {
      setPreferenceState(next);
      syncApplied(next);
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    },
    [syncApplied],
  );

  const value = useMemo(
    () => ({ preference, theme, setPreference }),
    [preference, theme, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}

/** Inline script to apply stored theme before paint (avoids FOUC). Default: system. */
export const themeInitScript = `(function(){try{var k=${JSON.stringify(THEME_STORAGE_KEY)};var t=localStorage.getItem(k);if(t==="signal")t="pitch";var ok=${JSON.stringify([...PREFERENCE_IDS])};if(ok.indexOf(t)===-1)t="system";var applied=t==="system"?(window.matchMedia("(prefers-color-scheme: dark)").matches?"pitch":"matchday"):t;document.documentElement.setAttribute("data-theme",applied);}catch(e){document.documentElement.setAttribute("data-theme","matchday");}})();`;
