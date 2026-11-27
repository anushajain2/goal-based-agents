"use client";

import { Check, X } from "lucide-react";

import { Campaign, num, PER_PERIOD, PERIOD_WORD, TargetView } from "@/lib/api";
import { cx } from "./ui";

/** "8 of 15 signups this week" with a bar; for a goal that hasn't started: "15 signups a week". */
export function TargetLine({ goal, compact }: { goal: Pick<Campaign, "target" | "primary_metric">; compact?: boolean }) {
  const t = goal.target;
  if (!t || !t.target || !t.period) return null;
  if (t.status !== "active" || t.progress == null) {
    return <span className="text-[12px] text-muted">Target: {num(t.target)} {goal.primary_metric} {PER_PERIOD[t.period]}</span>;
  }
  const pct = Math.min(100, Math.round((t.progress / t.target) * 100));
  const hit = t.progress >= t.target;
  return (
    <span className="block">
      <span className={cx("flex items-baseline justify-between gap-2", compact ? "text-[12px]" : "text-[12.5px]")}>
        <span className="min-w-0 truncate">
          <b className={hit ? "text-emerald-700" : "text-ink"}>{num(t.progress)}</b>
          <span className="text-muted"> of {num(t.target)} {compact ? "" : goal.primary_metric + " "}{PERIOD_WORD[t.period]}</span>
        </span>
        {!compact && t.days_left != null && <span className="shrink-0 text-[12px] text-muted">{t.days_left < 1 ? "ends today" : `${Math.ceil(t.days_left)}d left`}</span>}
      </span>
      <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-stone-100">
        <span className={cx("block h-full rounded-full", hit ? "bg-emerald-500" : "bg-brand-500")} style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

/** Past periods as small chips: "Week 1 · 17/15 ✓". */
export function TargetHistory({ target }: { target: TargetView | null }) {
  const h = target?.history || [];
  if (!h.length) return null;
  const word = { week: "Week", month: "Month", quarter: "Quarter" };
  return (
    <ul className="flex flex-wrap gap-1.5">
      {h.map((x, i) => (
        <li key={i} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold",
          x.status === "hit" ? "bg-emerald-50 text-emerald-700" : x.status === "missed" ? "bg-signal-50 text-signal-800" : "bg-stone-100 text-stone-600")}>
          {x.status === "hit" ? <Check size={11} /> : x.status === "missed" ? <X size={11} /> : null}
          {word[x.period]}: {num(x.result)} of {num(x.target)}{x.status === "replaced" ? " (changed)" : ""}
        </li>
      ))}
    </ul>
  );
}
