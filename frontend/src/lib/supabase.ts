"use client";

import { createBrowserClient } from "@supabase/ssr";
import { supabasePublishableKey } from "./supabase-env";

let client: ReturnType<typeof createBrowserClient> | undefined;

export function createBrowserSupabaseClient() {
  if (!client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = supabasePublishableKey();
    if (!url || !key) {
      throw new Error("Supabase environment variables are not configured.");
    }
    client = createBrowserClient(url, key);
  }
  return client;
}

/** Convenience alias used across the app. */
export function supabase() {
  return createBrowserSupabaseClient();
}
