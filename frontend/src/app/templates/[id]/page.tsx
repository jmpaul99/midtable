"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { use } from "react";
import { RequireAuth } from "@/lib/auth";
import { Loading } from "@/components/ui/State";

/** Legacy /templates/[id] → create-league template editor. */
export default function TemplateDetailRedirectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  useEffect(() => {
    router.replace(`/leagues/new/templates/${id}`);
  }, [router, id]);

  return (
    <RequireAuth>
      <Loading label="Redirecting" />
    </RequireAuth>
  );
}
