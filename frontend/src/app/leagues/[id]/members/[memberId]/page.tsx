"use client";

import { use } from "react";
import { redirect } from "next/navigation";

/** Legacy URL — redirects to /managers/:id */
export default function LegacyMemberRedirect({
  params,
}: {
  params: Promise<{ id: string; memberId: string }>;
}) {
  const { id, memberId } = use(params);
  redirect(`/leagues/${id}/managers/${memberId}`);
}
