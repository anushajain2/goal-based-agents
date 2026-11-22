"use client";

import { Bot, Hand, Home, ListTree, LogOut, Settings, Sparkles, Target, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { api, OrgInfo, Overview, usd, useApi } from "@/lib/api";
import { cx, Dot } from "./ui";

type Status = { anthropic_configured: boolean; composio_enabled: boolean; chrome_path: string | null; agent_chrome_running: boolean };

const NAV = [
  { href: "/home", label: "Home", icon: Home, match: (p: string) => p === "/home" },
  { href: "/team", label: "Team", icon: Users, match: (p: string) => p.startsWith("/team") },
  { href: "/goals", label: "Goals", icon: Target, match: (p: string) => p.startsWith("/goals") },
  { href: "/work", label: "Work log", icon: ListTree, match: (p: string) => p.startsWith("/work") },
  { href: "/approvals", label: "Needs you", icon: Hand, match: (p: string) => p.startsWith("/approvals") },
  { href: "/capabilities", label: "What it can do", icon: Sparkles, match: (p: string) => p.startsWith("/capabilities") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p: string) => p.startsWith("/settings") },
];

export function EmployeeAvatar({ state, size = 36 }: { state?: "working" | "waiting" | "idle"; size?: number }) {
  return (
    <span className="relative inline-grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-500 to-violet-500 text-white" style={{ width: size, height: size }}>
      <Bot size={size * 0.52} />
      {state && (
        <span
          className={cx(
            "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white",
            state === "working" ? "animate-pulse bg-emerald-500" : state === "waiting" ? "bg-amber-500" : "bg-gray-300",
          )}
        />
      )}
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { data: ov } = useApi<Overview>("/api/overview");
  const { data: status } = useApi<Status>("/api/status", { pollMs: 30000, live: false });
  const { data: org } = useApi<OrgInfo>("/api/org", { pollMs: 120000 });
  const me = org?.me;

  async function logout() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => null);
    window.location.href = "/";
  }
  const pending = ov?.waiting_on_you || 0;
  const state = ov ? (ov.working_on.length ? "working" : pending ? "waiting" : "idle") : undefined;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-white md:flex">
        <Link href="/home" className="flex items-center gap-3 px-4 pb-3 pt-4">
          <EmployeeAvatar state={state} />
          <span className="leading-tight">
            <span className="block max-w-[150px] truncate text-[16px] font-bold tracking-tight">{org?.org.name || "Autopilot"}</span>
            <span className="block text-xs text-muted">
              {state === "working" ? "AI employees working" : state === "waiting" ? "Waiting on you" : "Powered by Autopilot"}
            </span>
          </span>
        </Link>
        <nav className="mt-2 flex flex-col gap-0.5 px-2">
          {NAV.map(({ href, label, icon: Icon, match }) => (
            <Link
              key={href}
              href={href}
              className={cx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-semibold transition",
                match(path) ? "bg-brand-50 text-brand-700" : "text-gray-700 hover:bg-gray-100",
              )}
            >
              <Icon size={17} />
              <span className="flex-1">{label}</span>
              {href === "/approvals" && pending > 0 && <span className="rounded-full bg-amber-500 px-1.5 text-[11px] font-bold text-white">{pending}</span>}
            </Link>
          ))}
        </nav>

        <div className="mx-3 mt-auto rounded-xl bg-gray-50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Spent this month</div>
          <div className="tabular mt-0.5 text-lg font-bold">{usd(ov?.spend_this_month.total ?? 0)}</div>
          <div className="text-xs text-muted">
            AI {usd(ov?.spend_this_month.ai_usage ?? 0)} · other {usd(ov?.spend_this_month.other ?? 0)}
          </div>
        </div>
        <div className="space-y-1 px-4 py-3 text-xs text-muted">
          <StatusLine ok={!!status?.anthropic_configured} label="Claude API key" />
          <StatusLine ok={!!status?.composio_enabled} label="App connectors" optional />
          <StatusLine ok={!!status?.chrome_path} label="Agent Chrome" />
        </div>
        {me && (
          <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gray-100 text-xs font-bold uppercase text-gray-600">
              {(me.name || me.email).slice(0, 1)}
            </span>
            <span className="min-w-0 flex-1 leading-tight">
              {me.name && <span className="block truncate text-[13px] font-semibold">{me.name}</span>}
              <span className="block truncate text-xs text-muted">{me.email} · {me.role}</span>
            </span>
            <button onClick={logout} title="Log out" aria-label="Log out" className="rounded-md p-1.5 text-muted hover:bg-gray-100 hover:text-ink">
              <LogOut size={16} />
            </button>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-white md:hidden">
          <div className="flex items-center gap-2 px-4 py-2.5">
            <EmployeeAvatar state={state} size={28} />
            <span className="truncate font-bold">{org?.org.name || "Autopilot"}</span>
            <span className="tabular ml-auto text-xs text-muted">{usd(ov?.spend_this_month.total ?? 0)} this month</span>
            <button onClick={logout} aria-label="Log out" className="rounded-md p-1 text-muted hover:text-ink"><LogOut size={16} /></button>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-2 pb-2">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className={cx("shrink-0 rounded-full px-3 py-1 text-[13px] font-semibold", n.match(path) ? "bg-brand-50 text-brand-700" : "text-gray-600")}>
                {n.label}
                {n.href === "/approvals" && pending > 0 ? ` (${pending})` : ""}
              </Link>
            ))}
          </nav>
        </header>
        {status && !status.anthropic_configured && (
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-900">
            Add <code className="font-mono">ANTHROPIC_API_KEY</code> to the <code className="font-mono">.env</code> file and restart the app so Autopilot can work.
          </div>
        )}
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}

function StatusLine({ ok, label, optional }: { ok: boolean; label: string; optional?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <Dot tone={ok ? "green" : optional ? "gray" : "red"} />
      {label}
      {!ok && optional && <span className="text-gray-400">(optional)</span>}
    </div>
  );
}
