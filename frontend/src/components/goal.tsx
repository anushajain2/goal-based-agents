"use client";

import { TargetLine } from "./Target";
import { Campaign, num } from "@/lib/api";
import { cx, Dot, Tone } from "./ui";

export const GOAL_STATUS: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Not started", tone: "gray" },
  active: { label: "Active", tone: "green" },
  paused: { label: "Paused", tone: "gray" },
  out_of_budget: { label: "Out of budget", tone: "red" },
  completed: { label: "Finished", tone: "blue" },
};

/** Live state of the employee on this goal, from its latest work session. */
export function goalActivity(c: Campaign): { label: string; tone: Tone; live: boolean } {
  const run = c.current_run;
  if (c.status === "active" && run && ["queued", "running"].includes(run.status)) return { label: "Working now", tone: "blue", live: true };
  if (run?.status === "waiting" || c.pending_requests > 0) return { label: "Needs you", tone: "amber", live: false };
  const s = GOAL_STATUS[c.status] || { label: c.status, tone: "gray" as Tone };
  return { ...s, live: false };
}

export function GoalStatus({ c }: { c: Campaign }) {
  const s = goalActivity(c);
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[13px]">
      {s.live ? <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" /> : <Dot tone={s.tone} />}
      <span className={cx(s.tone === "amber" && "font-semibold text-amber-700", s.live && "font-semibold text-brand-700")}>{s.label}</span>
    </span>
  );
}

/** Results so far toward the target (results = change in the primary metric since the first reading). */
export function progressOf(c: Campaign): { done: number | null; target: number | null; pct: number | null } {
  const done = c.results.results;
  const target = c.target_value;
  const pct = target && done !== null ? Math.max(0, Math.min(100, (done / target) * 100)) : null;
  return { done, target, pct };
}

export function ProgressBar({ pct, className, tone = "brand" }: { pct: number | null; className?: string; tone?: "brand" | "gray" }) {
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-gray-100", className)}>
      <div className={cx("h-full rounded-full transition-all", tone === "brand" ? "bg-brand-500" : "bg-gray-400")} style={{ width: `${pct ?? 0}%` }} />
    </div>
  );
}

export function GoalProgress({ c, compact }: { c: Campaign; compact?: boolean }) {
  if (c.target?.status === "active" && c.target.target) {
    return <div className={compact ? "" : "min-w-36"}><TargetLine goal={c} compact={compact} /></div>;
  }
  const p = progressOf(c);
  return (
    <div className={compact ? "" : "min-w-36"}>
      <div className="flex items-baseline justify-between gap-2 text-[13px]">
        <span className="tabular font-semibold">
          {p.done === null ? "—" : num(p.done)}
          {p.target ? <span className="font-normal text-muted"> / {num(p.target)}</span> : null}
        </span>
        {p.pct !== null && <span className="tabular text-xs text-muted">{Math.round(p.pct)}%</span>}
      </div>
      <ProgressBar pct={p.pct} className="mt-1" />
      {!compact && <div className="mt-0.5 truncate text-[11px] text-muted">{c.primary_metric}</div>}
    </div>
  );
}
