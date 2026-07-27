import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
import { publicOrigin } from "@/lib/public-origin";
import { supabasePublishableKey } from "@/lib/supabase-env";

function safeNext(value: string | null): string {
  if (value?.startsWith("/") && !value.startsWith("//")) return value;
  return "/";
}

function loginErrorRedirect(origin: string, message: string, next: string) {
  const params = new URLSearchParams({ error: message });
  if (next !== "/") {
    params.set("next", next);
  }
  return NextResponse.redirect(new URL(`/login?${params.toString()}`, origin));
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const origin = publicOrigin(request);
  const code = url.searchParams.get("code");
  const next = safeNext(url.searchParams.get("next"));
  const oauthError =
    url.searchParams.get("error_description") ||
    url.searchParams.get("error") ||
    "";
  const response = NextResponse.redirect(new URL(next, origin));

  if (oauthError && !code) {
    return loginErrorRedirect(origin, oauthError, next);
  }

  if (!code) {
    return loginErrorRedirect(origin, "Authentication callback is missing a code", next);
  }

  const publishableKey = supabasePublishableKey();
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !publishableKey) {
    return loginErrorRedirect(origin, "Supabase is not configured", next);
  }

  const client = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL,
    publishableKey,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) => {
          cookiesToSet.forEach(({ name, value, options }) => {
            response.cookies.set(name, value, options);
          });
        },
      },
    },
  );

  const { error } = await client.auth.exchangeCodeForSession(code);
  if (error) {
    return loginErrorRedirect(origin, error.message, next);
  }

  return response;
}
