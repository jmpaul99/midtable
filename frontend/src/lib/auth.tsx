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

function jwtLooksAdmin(user: User | null | undefined): boolean {
  return ["admin", "service_role"].includes(String(user?.app_metadata?.role));
}

interface AuthContextValue {
  user: User | null;
  session: Session | null;
  loading: boolean;
  isAdmin: boolean;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

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
      return;
    }

    setIsAdmin(jwtLooksAdmin(session.user));
    api<Me>("/auth/me")
      .then((me) => {
        if (!cancelled) setIsAdmin(Boolean(me.is_platform_admin));
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(jwtLooksAdmin(session.user));
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
      signOut,
      refresh,
    }),
    [session, loading, isAdmin, signOut, refresh],
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
