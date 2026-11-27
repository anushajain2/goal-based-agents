"use client";

import { Check, CircleAlert, Loader2, Minus } from "lucide-react";

import { SetupStep } from "@/lib/api";
import { cx } from "./ui";

/** The steps of a research run ("Suggest more goals", "Find more opportunities"), live. */
export function RunProgress({ steps, className }: { steps: SetupStep[]; className?: string }) {
  return (
    <ol className={cx("space-y-2.5", className)}>
      {steps.map((s) => (
        <li key={s.key} className="flex items-start gap-3">
          <StepIcon status={s.status} />
          <div className="min-w-0 flex-1">
            <div className={cx("text-[14px] font-semibold", s.status === "pending" && "text-muted")}>{s.label}</div>
            {s.detail && <div className="text-xs text-muted">{s.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function StepIcon({ status }: { status: SetupStep["status"] }) {
  const base = "grid h-6 w-6 shrink-0 place-items-center rounded-full";
  if (status === "done") return <span className={cx(base, "bg-emerald-600 text-white")}><Check size={14} /></span>;
  if (status === "running") return <span className={cx(base, "bg-brand-50 text-brand-600")}><Loader2 size={15} className="animate-spin" /></span>;
  if (status === "failed") return <span className={cx(base, "bg-signal-100 text-signal-700")}><CircleAlert size={14} /></span>;
  if (status === "skipped") return <span className={cx(base, "bg-stone-100 text-stone-400")}><Minus size={14} /></span>;
  return <span className={cx(base, "border-2 border-stone-200")} />;
}
