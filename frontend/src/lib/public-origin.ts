import type { NextRequest } from "next/server";

/** Canonical public origin for redirects (Cloud Run listens on 0.0.0.0). */
export function publicOrigin(request: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  if (configured) return configured;

  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const forwardedProto =
    request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim() || "https";
  if (forwardedHost && !forwardedHost.startsWith("0.0.0.0")) {
    return `${forwardedProto}://${forwardedHost}`;
  }

  const host = request.headers.get("host")?.split(",")[0]?.trim();
  if (host && !host.startsWith("0.0.0.0")) {
    return `${forwardedProto}://${host}`;
  }

  return new URL(request.url).origin;
}
