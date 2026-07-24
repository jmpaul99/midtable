"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { RequireAuth } from "@/lib/auth";
import { Loading } from "@/components/ui/State";

/** Legacy /templates → create-league templates hub. */
export default function TemplatesRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/leagues/new");
  }, [router]);

  return (
    <RequireAuth>
      <Loading label="Redirecting" />
    </RequireAuth>
  );
}
