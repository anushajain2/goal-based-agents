import type { Metadata } from "next";
import { ReactNode } from "react";

import { Shell } from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Autopilot",
  description: "Set a goal and a budget. AI agents work toward it, with your approval on what matters.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
