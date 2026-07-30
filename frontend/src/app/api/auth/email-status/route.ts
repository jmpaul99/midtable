import { NextRequest, NextResponse } from "next/server";
import { clientIpFromHeaders, rateLimitExceeded } from "@/lib/rate-limit";

const WINDOW_MS = 60_000;
const LIMIT = 10;

function apiBase(): string {
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

export async function POST(request: NextRequest) {
  const ip = clientIpFromHeaders(request.headers);
  if (rateLimitExceeded(`email-status:${ip}`, LIMIT, WINDOW_MS)) {
    return NextResponse.json(
      { detail: "Too many requests. Try again shortly." },
      { status: 429 },
    );
  }

  const secret = process.env.INTERNAL_API_SECRET?.trim();
  if (!secret) {
    return NextResponse.json(
      { detail: "Server misconfigured" },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const email = String((body as { email?: unknown }).email ?? "")
    .trim()
    .toLowerCase();
  const turnstileToken = String(
    (body as { turnstile_token?: unknown }).turnstile_token ?? "",
  ).trim();
  const turnstileRequired = process.env.NODE_ENV !== "development";

  if (!email || (turnstileRequired && !turnstileToken)) {
    return NextResponse.json(
      {
        detail: turnstileRequired
          ? "email and turnstile_token are required"
          : "email is required",
      },
      { status: 400 },
    );
  }

  const upstream = await fetch(`${apiBase()}/auth/email-status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": secret,
      ...(ip !== "unknown" ? { "X-Forwarded-For": ip } : {}),
    },
    body: JSON.stringify({
      email,
      turnstile_token: turnstileToken || "dev-bypass",
    }),
    cache: "no-store",
  });

  const payload = await upstream.json().catch(() => ({ detail: "Upstream error" }));
  return NextResponse.json(payload, { status: upstream.status });
}
