"use client";

import { Bell, LayoutGrid, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { useApi } from "@/lib/api";
import { cx, Dot } from "./ui";

type Status = {
  anthropic_configured: boolean;
  composio_enabled: boolean;
  chrome_path: string | null;
  agent_chrome_running: boolean;
  manual_signin_mode: boolean;
};

const NAV = [
  { href: "/", label: "Campaigns", icon: LayoutGrid, match: (p: string) => p === "/" || p.startsWith("/campaigns") },
  { href: "/approvals", label: "Approvals", icon: Bell, match: (p: string) => p.startsWith("/approvals") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p: string) => p.startsWith("/settings") },
];

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { data: pending } = useApi<unknown[]>("/api/requests?status=pending");
  const { data: status } = useApi<Status>("/api/status", { pollMs: 30000, live: false });
  const count = pending?.length || 0;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-white md:flex">
        <Link href="/" className="flex items-center gap-2 px-4 py-4">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-white">
            <Sparkles size={17} />
          </span>
          <span className="text-[17px] font-bold tracking-tight">Autopilot</span>
        </Link>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map(({ href, label, icon: Icon, match }) => (
            <Link
              key={href}
              href={href}
              className={cx(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold",
                match(path) ? "bg-brand-50 text-brand-700" : "text-ink hover:bg-gray-100",
              )}
            >
              <Icon size={18} />
              <span className="flex-1">{label}</span>
              {label === "Approvals" && count > 0 && (
                <span className="rounded-full bg-red-500 px-1.5 text-xs font-bold text-white">{count}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-1.5 border-t border-line px-4 py-3 text-xs text-muted">
          <StatusLine ok={!!status?.anthropic_configured} label="Claude API key" />
          <StatusLine ok={!!status?.composio_enabled} label="App connectors" warn />
          <StatusLine ok={!!status?.chrome_path} label={status?.agent_chrome_running ? "Agent Chrome open" : "Agent Chrome"} />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-line bg-white px-4 py-2 md:hidden">
          <span className="font-bold">Autopilot</span>
          <nav className="ml-auto flex gap-3 text-sm font-semibold">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className={n.match(path) ? "text-brand-600" : ""}>
                {n.label}
                {n.label === "Approvals" && count > 0 ? ` (${count})` : ""}
              </Link>
            ))}
          </nav>
        </header>
        {status && !status.anthropic_configured && (
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-900">
            Add <code className="font-mono">ANTHROPIC_API_KEY</code> to <code className="font-mono">.env</code> and restart the worker so the agent can run.
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6">{children}</main>
      </div>
    </div>
  );
}

function StatusLine({ ok, label, warn }: { ok: boolean; label: string; warn?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <Dot tone={ok ? "green" : warn ? "amber" : "red"} />
      {label}
      {!ok && warn && <span className="text-gray-400">(optional)</span>}
    </div>
  );
}
