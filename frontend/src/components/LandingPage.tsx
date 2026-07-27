"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { MidtableLogo } from "@/components/MidtableLogo";
import { Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

function safeNext(value: string | null): string | null {
  if (!value?.startsWith("/") || value.startsWith("//")) return null;
  return value;
}

const howItWorks = [
  {
    step: "01",
    title: "Draft your clubs",
    body: "Take turns picking real teams. On the clock.",
  },
  {
    step: "02",
    title: "Play the competition",
    body: "Every result hits the leaderboard. Upset bonuses when the underdog bites — plus custom bonuses your league defines.",
  },
  {
    step: "03",
    title: "Climb the table",
    body: "Track standings and the race to the top.",
  },
] as const;

const pillars = [
  {
    title: "The draft",
    body: "Build your roster before the competition kicks off.",
  },
  {
    title: "Matchday scoring",
    body: "Follow your clubs every matchday. Points for results; upset bonuses when lower-ranked clubs steal points; custom bonuses on top.",
  },
  {
    title: "Multi-competition leagues",
    body: "One league can span across all the top leagues in Europe.",
  },
] as const;

function CtaLink({
  href,
  children,
  variant = "primary",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary";
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold transition active:scale-[0.98]",
        variant === "primary"
          ? "bg-brand text-on-brand hover:bg-brand-dark shadow-sm"
          : "border border-line bg-surface text-ink hover:bg-surface-2",
      )}
    >
      {children}
    </Link>
  );
}

export function LandingPage() {
  const search = useSearchParams();
  const next = safeNext(search.get("next"));
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  return (
    <div className="flex flex-col gap-16 sm:gap-20 pb-8">
      <section className="relative flex min-h-[min(72dvh,640px)] flex-col items-center justify-center gap-8 py-8 text-center animate-in sm:py-12">
        <MidtableLogo className="h-20 w-auto sm:h-28 md:h-32" />
        <div className="mx-auto max-w-2xl">
          <Eyebrow>Football draft leagues</Eyebrow>
          <h1 className="mt-2 text-3xl tracking-tight sm:text-4xl md:text-5xl">
            Every result moves the table.
          </h1>
          <Muted className="mx-auto mt-3 max-w-xl text-base sm:text-[1.05rem]">
            Draft real clubs, then score every matchday — wins, draws, upsets, and custom
            bonuses.
          </Muted>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <CtaLink href={loginHref}>Sign in</CtaLink>
          </div>
        </div>
      </section>

      <section className="animate-in" style={{ animationDelay: "60ms" }}>
        <Eyebrow>How it works</Eyebrow>
        <h2 className="mt-1 text-2xl sm:text-3xl">From draft to the top of the table</h2>
        <ol className="mt-6 grid gap-6 sm:grid-cols-3 sm:gap-5">
          {howItWorks.map((item) => (
            <li key={item.step} className="flex flex-col gap-2">
              <span className="text-xs font-extrabold uppercase tracking-[0.12em] text-brand">
                {item.step}
              </span>
              <h3 className="text-lg sm:text-xl">{item.title}</h3>
              <Muted>{item.body}</Muted>
            </li>
          ))}
        </ol>
      </section>

      <section className="animate-in" style={{ animationDelay: "120ms" }}>
        <Eyebrow>The game</Eyebrow>
        <h2 className="mt-1 text-2xl sm:text-3xl">Built for the competition</h2>
        <ul className="mt-6 grid gap-8 sm:grid-cols-3 sm:gap-6">
          {pillars.map((pillar) => (
            <li key={pillar.title} className="flex flex-col gap-2 border-t border-line pt-4">
              <h3 className="text-lg sm:text-xl">{pillar.title}</h3>
              <Muted>{pillar.body}</Muted>
            </li>
          ))}
        </ul>
      </section>

      <section className="animate-in border-t border-line py-12 text-center sm:py-16" style={{ animationDelay: "180ms" }}>
        <Stack gap="md" className="mx-auto max-w-xl items-center">
          <div>
            <h2 className="text-2xl sm:text-3xl">Ready for kickoff?</h2>
            <Muted className="mt-2 text-base">Start your managerial career.</Muted>
          </div>
          <CtaLink href={loginHref}>Sign in to play</CtaLink>
        </Stack>
      </section>
    </div>
  );
}
