"use client";

import { ArrowRight, Check, Plug } from "lucide-react";
import Link from "next/link";

import { useApi } from "@/lib/api";
import { cx } from "./ui";

type Overview = { tools: { key: string; label: string; status: string; live_goals: number }[]; summary: { needed: number; connected: number; missing_live: number } };

/** "Your team uses Gmail, HubSpot, LinkedIn… 2 of 7 connected" with one way in: the Connections page. */
export function ConnectChecklist({ only = "any" }: { only?: "any" | "missing_live" }) {
  const { data } = useApi<Overview>("/api/connections/overview", { live: false, pollMs: 60000 });
  if (!data || !data.summary.needed) return null;
  const s = data.summary;
  if (only === "missing_live" && !s.missing_live) return null;
  const all = s.connected >= s.needed;
  return (
    <Link href="/connections" className={cx("flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border px-5 py-4 shadow-[var(--shadow-card)] transition hover:shadow-[var(--shadow-pop)]",
      all ? "border-emerald-200 bg-gradient-to-r from-emerald-50 to-white" : "border-line bg-white")}>
      <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", all ? "bg-emerald-100 text-emerald-700" : "bg-brand-50 text-brand-600")}>
        {all ? <Check size={18} /> : <Plug size={18} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14.5px] font-semibold">
          {all ? "Every tool your team uses is connected" : only === "missing_live" ? `${s.missing_live} ${s.missing_live === 1 ? "tool your live goals use isn't" : "tools your live goals use aren't"} connected` : "Connect the tools your team uses"}
        </span>
        <span className="mt-1.5 flex flex-wrap gap-1.5">
          {data.tools.slice(0, 8).map((t) => (
            <span key={t.key} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold ring-1 ring-inset",
              t.status !== "missing" ? "bg-emerald-50 text-emerald-700 ring-emerald-100" : "bg-stone-50 text-stone-600 ring-stone-200")}>
              {t.status !== "missing" && <Check size={10} />} {t.label}
            </span>
          ))}
          {data.tools.length > 8 && <span className="text-[11.5px] text-muted">+{data.tools.length - 8} more</span>}
        </span>
      </span>
      <span className="flex items-center gap-3">
        <span className="tabular text-[13px] text-muted">{s.connected} of {s.needed} ready</span>
        {!all && <span className="inline-flex h-9 items-center gap-1 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white shadow-sm">Connect <ArrowRight size={14} /></span>}
      </span>
    </Link>
  );
}
