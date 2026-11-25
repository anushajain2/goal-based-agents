import type { Metadata } from "next";
import { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Autopilot: become AI-native without teaching anyone AI",
  description:
    "Enter your website and Autopilot sets up AI employees for every team, with real goals. They do the work and show it; your people give the final yes. Human accuracy at AI speed.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
