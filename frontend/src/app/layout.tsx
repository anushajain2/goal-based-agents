import type { Metadata } from "next";
import { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Autopilot: set a goal and a budget, it gets it done",
  description:
    "Hire an AI employee for the work that grows your company. Set a goal and a budget; Autopilot plans, does the work, checks with you on what matters and logs every step.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
