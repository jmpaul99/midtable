"use client";

import type { DependencyList } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";

export function useApiQuery<T>(
  path: string | null,
  deps: DependencyList = [],
): {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  const prevPathRef = useRef<string | null>(null);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!path) {
      prevPathRef.current = null;
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const pathChanged = prevPathRef.current !== path;
    prevPathRef.current = path;
    setLoading(true);
    setError(null);
    // Drop stale payload when the resource identity changes; keep it on reload().
    if (pathChanged) setData(null);
    api<T>(path)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(errorMessage(e));
        setData(null);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Caller-provided deps plus path/tick control refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);

  return { data, error, loading, reload };
}
