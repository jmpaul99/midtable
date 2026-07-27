import { Suspense } from "react";
import type { Metadata } from "next";
import { RequireAuth } from "@/lib/auth";
import { JoinForm, JoinFormFallback } from "./JoinForm";

type JoinPreview = {
  league_name: string;
  league_id: string;
  enabled: boolean;
  season_label?: string | null;
};

type PageProps = {
  searchParams: Promise<{ token?: string | string[] }>;
};

function apiBase() {
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

function tokenFrom(searchParams: { token?: string | string[] }) {
  const raw = searchParams.token;
  return typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
}

async function fetchJoinPreview(token: string): Promise<JoinPreview | null> {
  if (!token) return null;
  try {
    const res = await fetch(
      `${apiBase()}/join-links/preview?token=${encodeURIComponent(token)}`,
      { next: { revalidate: 60 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as JoinPreview;
  } catch {
    return null;
  }
}

function joinCopy(preview: JoinPreview | null) {
  if (preview?.league_name) {
    const season = preview.season_label?.trim();
    return {
      title: `Join ${preview.league_name} on Midtable`,
      description: season
        ? `${season}. Open the link to join the dugout and draft with the group.`
        : "Open the link to join the dugout and draft with the group.",
    };
  }
  return {
    title: "Join a league on Midtable",
    description: "Use a shareable Midtable link to claim a place in the dugout and start drafting.",
  };
}

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const token = tokenFrom(await searchParams);
  const preview = await fetchJoinPreview(token);
  const { title, description } = joinCopy(preview);

  return {
    title: { absolute: title },
    description,
    openGraph: {
      title,
      description,
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default function JoinLeaguePage() {
  return (
    <Suspense fallback={<JoinFormFallback />}>
      <RequireAuth>
        <JoinForm />
      </RequireAuth>
    </Suspense>
  );
}
