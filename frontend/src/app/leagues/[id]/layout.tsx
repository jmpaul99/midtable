"use client";

import { use } from "react";
import { LeagueShell } from "@/components/LeagueShell";

export default function LeagueLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <LeagueShell leagueId={id}>{children}</LeagueShell>;
}
