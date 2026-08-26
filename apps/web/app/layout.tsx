import type { Metadata } from "next";
import { AppShell } from "@/components/shell/AppShell";
import { plexMono, plexSans } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "MarketPilot AI",
  description:
    "AI-powered market intelligence and paper-trading platform. Paper-trading infrastructure only — no real financial transactions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
