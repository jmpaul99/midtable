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
import { usePathname, useRouter } from "next/navigation";
import type { AuthChangeEvent, Session, User } from "@supabase/supabase-js";
import { api } from "./api";
import type { Me } from "./types";
import { supabase } from "./supabase";
import { Loading } from "@/components/ui/State";

function AuthLoading() {
  return <Loading label="Checking your session" />;
}

interface AuthContextValue {
  user: User | null;
  session: Session | null;
  loading: boolean;
  isAdmin: boolean;
  /** False until /auth/me has resolved platform-admin status for the current session. */
  adminReady: boolean;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminReady, setAdminReady] = useState(false);

  const refresh = useCallback(async () => {
    const { data } = await supabase().auth.getSession();
    setSession(data.session);
  }, []);

  useEffect(() => {
    let mounted = true;
    supabase()
      .auth.getSession()
      .then(({ data }: { data: { session: Session | null } }) => {
        if (mounted) {
          setSession(data.session);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) setLoading(false);
      });

    const { data } = supabase().auth.onAuthStateChange(
      (_event: AuthChangeEvent, next: Session | null) => {
        setSession(next);
        setLoading(false);
      },
    );

    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!session) {
      setIsAdmin(false);
      setAdminReady(true);
      return;
    }

    setIsAdmin(false);
    setAdminReady(false);
    api<Me>("/auth/me")
      .then((me) => {
        if (!cancelled) {
          setIsAdmin(Boolean(me.is_platform_admin));
          setAdminReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIsAdmin(false);
          setAdminReady(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [session]);

  const signOut = useCallback(async () => {
    await supabase().auth.signOut();
    setSession(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: session?.user ?? null,
      session,
      loading,
      isAdmin,
      adminReady,
      signOut,
      refresh,
    }),
    [session, loading, isAdmin, adminReady, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!session) {
      const next = `${pathname}${typeof window !== "undefined" ? window.location.search : ""}`;
      if (next === "/" || next === "") {
        router.replace("/");
        return;
      }
      router.replace(`/?next=${encodeURIComponent(next)}`);
    }
  }, [loading, session, router, pathname]);

  if (loading || !session) {
    return <AuthLoading />;
  }

  return children;
}

export function RequirePlatformAdmin({ children }: { children: ReactNode }) {
  const { session, loading, isAdmin, adminReady } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading || !session || !adminReady) return;
    if (!isAdmin) {
      router.replace("/");
    }
  }, [loading, session, adminReady, isAdmin, router]);

  if (loading || !session || !adminReady) {
    return <AuthLoading />;
  }

  if (!isAdmin) {
    return <Loading label="Checking admin access" />;
  }

  return children;
}
