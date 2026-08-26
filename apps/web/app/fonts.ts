import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

// IBM Plex Sans (UI) + IBM Plex Mono (all numerical/financial data) —
// see docs/ui-design-system.md §2. Self-hosted via next/font at build time.
export const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

export const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});
