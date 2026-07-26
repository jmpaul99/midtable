import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
import { publicOrigin } from "@/lib/public-origin";
import { supabasePublishableKey } from "@/lib/supabase-env";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const origin = publicOrigin(request);
  const code = url.searchParams.get("code");
  const requestedNext = url.searchParams.get("next");
  const next =
    requestedNext?.startsWith("/") && !requestedNext.startsWith("//") ? requestedNext : "/";
  const response = NextResponse.redirect(new URL(next, origin));

  if (!code) {
    return NextResponse.redirect(
      new URL("/login?error=Authentication%20callback%20is%20missing%20a%20code", origin),
    );
  }

  const publishableKey = supabasePublishableKey();
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !publishableKey) {
    return NextResponse.redirect(
      new URL("/login?error=Supabase%20is%20not%20configured", origin),
    );
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
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(error.message)}`, origin),
    );
  }

  return response;
}
