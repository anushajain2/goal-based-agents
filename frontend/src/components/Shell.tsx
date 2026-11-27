"use client";

import { Hand, Home, ListTree, LogOut, Plug, Radar, Settings, Target, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { api, OrgInfo, Overview, usd, useApi } from "@/lib/api";
import { cx, Dot } from "./ui";

type Status = { anthropic_configured: boolean; composio_enabled: boolean; chrome_path: string | null; agent_chrome_running: boolean };

const NAV = [
  { href: "/home", label: "Home", icon: Home, match: (p: string) => p === "/home" },
  { href: "/approvals", label: "Needs you", icon: Hand, match: (p: string) => p.startsWith("/approvals") },
  { href: "/team", label: "Team", icon: Users, match: (p: string) => p.startsWith("/team") },
  { href: "/goals", label: "Goals", icon: Target, match: (p: string) => p.startsWith("/goals") },
  { href: "/opportunities", label: "Find opportunities", icon: Radar, match: (p: string) => p.startsWith("/opportunities") || p.startsWith("/setup") },
  { href: "/work", label: "Work log", icon: ListTree, match: (p: string) => p.startsWith("/work") },
  { href: "/connections", label: "Connections", icon: Plug, match: (p: string) => p.startsWith("/connections") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p: string) => p.startsWith("/settings") },
];

/** The Oton mark: an olive tile with a target and the path that hits it. */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="9" style={{ fill: "var(--color-brand-600)" }} />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="#ffffff" strokeOpacity="0.35" strokeWidth="2" />
      <circle cx="16" cy="16" r="3" fill="#ffffff" />
      <path d="M7.5 24.5 L13.4 18.6" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

export function EmployeeAvatar({ state, size = 36 }: { state?: "working" | "waiting" | "idle"; size?: number }) {
  return (
    <span className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <BrandMark size={size} />
      {state && (
        <span
          className={cx(
            "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white",
            state === "working" ? "animate-pulse bg-emerald-500" : state === "waiting" ? "bg-signal-500" : "bg-stone-300",
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
  const goalCount = ov?.goals.total ?? 0;
  const spent = ov?.spend_this_month.total ?? 0;
  const budget = ov?.budget_total ?? 0;
  const orgName = org?.org.name || "Oton";

  const navItem = ({ href, label, icon: Icon, match }: (typeof NAV)[number]) => {
    const on = match(path);
    return (
      <Link key={href} href={href}
        className={cx("group flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] transition",
          on ? "bg-brand-50 font-semibold text-brand-700" : "font-medium text-stone-600 hover:bg-stone-50 hover:text-ink")}>
        <Icon size={17} className={on ? "text-brand-600" : "text-stone-400 group-hover:text-stone-600"} />
        <span className="flex-1">{label}</span>
        {href === "/approvals" && pending > 0 && (
          <span className="tabular grid h-5 min-w-5 place-items-center rounded-full bg-brand-600 px-1.5 text-[12px] font-bold text-white">{pending}</span>
        )}
      </Link>
    );
  };

  return (
    <div className="flex min-h-screen md:bg-[linear-gradient(to_right,#fff_247px,#eaecf0_247px,#eaecf0_248px,transparent_248px)]">
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line bg-white md:flex">
        <Link href="/home" className="m-3 flex items-center gap-3 rounded-xl p-2 transition hover:bg-stone-50">
          <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-brand-50 text-[15px] font-bold text-brand-700 ring-1 ring-inset ring-brand-100">
            {orgName.slice(0, 1).toUpperCase()}
            {state && (
              <span className={cx("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white",
                state === "working" ? "animate-pulse bg-emerald-500" : state === "waiting" ? "bg-signal-500" : "bg-stone-300")} />
            )}
          </span>
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-[14.5px] font-semibold">{orgName}</span>
            <span className="block truncate text-[12px] text-muted">
              {goalCount ? `${goalCount} goal${goalCount === 1 ? "" : "s"}` : "Workspace"}
              {state === "working" ? ", working" : state === "waiting" ? ", waiting on you" : ""}
            </span>
          </span>
        </Link>

        <nav className="flex flex-col gap-0.5 px-3">{NAV.slice(0, 5).map(navItem)}</nav>
        <div className="mx-5 mb-2 mt-5 text-[12px] font-semibold text-stone-400">More</div>
        <nav className="flex flex-col gap-0.5 px-3">{NAV.slice(5).map(navItem)}</nav>

        <div className="mt-auto space-y-3 p-3">
          {status && !status.anthropic_configured && (
            <Link href="/connections" className="flex items-center gap-2 rounded-lg bg-signal-50 px-3 py-2 text-[12px] font-medium text-signal-900 ring-1 ring-inset ring-signal-100">
              <Dot tone="amber" /> Add your Claude API key
            </Link>
          )}
          <div className="rounded-xl border border-line p-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[12px] font-medium text-muted">Spent this month</span>
              <span className="tabular text-[14px] font-semibold">{usd(spent)}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-100">
              <div className="h-full rounded-full bg-brand-600" style={{ width: `${budget ? Math.min(100, (spent / budget) * 100) : 0}%` }} />
            </div>
            <div className="tabular mt-1.5 text-[12px] text-muted">{budget ? `of ${usd(budget)} in goal budgets` : "No budgets yet"}</div>
          </div>
          {me && (
            <div className="flex items-center gap-2.5 px-1">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-stone-100 text-xs font-bold uppercase text-stone-600">
                {(me.name || me.email).slice(0, 1)}
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block truncate text-[13px] font-semibold">{me.name || me.email}</span>
                <span className="block truncate text-[12px] capitalize text-muted">{me.role}</span>
              </span>
              <button onClick={logout} title="Log out" aria-label="Log out" className="rounded-md p-1.5 text-stone-400 hover:bg-stone-100 hover:text-ink">
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur md:hidden">
          <div className="flex items-center gap-2.5 px-4 py-2.5">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-50 text-[13px] font-bold text-brand-700">{orgName.slice(0, 1).toUpperCase()}</span>
            <span className="truncate font-semibold">{orgName}</span>
            <span className="tabular ml-auto text-xs text-muted">{usd(spent)} this month</span>
            <button onClick={logout} aria-label="Log out" className="rounded-md p-1 text-muted hover:text-ink"><LogOut size={16} /></button>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className={cx("shrink-0 rounded-full px-3 py-1 text-[13px] font-semibold", n.match(path) ? "bg-brand-600 text-white" : "text-stone-600")}>
                {n.label}
                {n.href === "/approvals" && pending > 0 ? ` (${pending})` : ""}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 md:px-10 md:py-9">{children}</main>
      </div>
    </div>
  );
}
