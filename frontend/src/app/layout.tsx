import type { Metadata } from "next";
import { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Oton: what are your competitors doing that you aren't?",
  description:
    "Enter your website and see where you stand next to your competitors: on Google, in ChatGPT and other AI assistants, in reviews and on your own site. Get the few gaps worth fixing first, each with a way to fix it.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
