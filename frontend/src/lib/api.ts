"use client";

import { supabase } from "./supabase";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc: unknown[] }).loc.join(".")
            : "";
          return loc ? `${loc}: ${(item as { msg: string }).msg}` : String((item as { msg: string }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === "string") {
      const extras: string[] = [];
      if (Array.isArray(obj.blockers) && obj.blockers.length) {
        extras.push(`${obj.blockers.length} blocker(s)`);
      }
      if (obj.pool_key) extras.push(`competition ${String(obj.pool_key)}`);
      if (obj.provider_message) extras.push(String(obj.provider_message));
      return extras.length ? `${obj.message} (${extras.join("; ")})` : obj.message;
    }
    return JSON.stringify(detail);
  }
  return "";
}

async function getAccessToken(refresh = false): Promise<string | null> {
  const client = supabase();
  if (refresh) {
    const { data } = await client.auth.refreshSession();
    return data.session?.access_token ?? null;
  }
  const {
    data: { session },
  } = await client.auth.getSession();
  return session?.access_token ?? null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = formatDetail(detail) || `Request failed (${response.status})`;
    throw new ApiError(response.status, message, detail);
  }
  return payload as T;
}

function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Unauthenticated API call (no Bearer token). */
export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });

  return parseResponse<T>(response);
}

export async function api<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const token = await getAccessToken(false);
  if (!token) throw new ApiError(401, "Please sign in to continue.");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });

  if (response.status === 401 && !retried) {
    const refreshed = await getAccessToken(true);
    if (refreshed) {
      return api<T>(path, init, true);
    }
    await supabase().auth.signOut();
    throw new ApiError(401, "Session expired. Please sign in again.");
  }

  return parseResponse<T>(response);
}

export const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export { formatDate, formatNumber } from "./format";
