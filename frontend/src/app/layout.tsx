import type { CSSProperties, ReactNode } from "react";
import type { Metadata } from "next";
import { DM_Sans, Fraunces } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import { Nav } from "@/components/Nav";
import "./globals.css";

const sans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-sans-loaded",
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display-loaded",
});

export const metadata: Metadata = {
  title: "Football Draft League",
  description: "Draft clubs, follow every result, and settle the table.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const fontVars = {
    "--font-sans": "var(--font-sans-loaded), 'Segoe UI', sans-serif",
    "--font-display": "var(--font-display-loaded), Georgia, serif",
  } as CSSProperties;

  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body style={fontVars}>
        <AuthProvider>
          <Nav />
          <main className="shell">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
