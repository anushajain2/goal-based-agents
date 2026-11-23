"use client";

import { Calculator } from "lucide-react";
import { useEffect, useState } from "react";

import { api, BudgetBasis, Campaign, usd } from "@/lib/api";
import { Button } from "./ui";

const every = (h: number) => (h === 1 ? "every hour" : h % 24 === 0 && h >= 24 ? (h === 24 ? "once a day" : `every ${h / 24} days`) : `every ${h} hours`);

/** "How was this budget worked out?" in one short block. */
export function BudgetBreakdown({ basis, total, pace, compact }: {
  basis: BudgetBasis; total?: number; pace?: Campaign["pace"]; compact?: boolean;
}) {
  const per = basis.basis === "history"
    ? `~${usd(basis.per_session_usd)} each (your average over the last ${basis.history_sessions} sessions)`
    : `~${usd(basis.per_session_usd)} each (a typical session, mostly AI usage)`;
  return (
    <div className="space-y-1 text-[12.5px] leading-relaxed text-stone-700">
      <div>
        {basis.starter && "First week: "}<b>{basis.sessions} work sessions</b> ({every(basis.cycle_hours)} for {Math.round(basis.days)} days) × {per} = {usd(basis.ai_usd)}
      </div>
      {basis.paid_spend_usd > 0 && <div>+ {usd(basis.paid_spend_usd)} it may spend on ads or purchases</div>}
      <div>
        = <b>{usd(basis.suggested_usd)}</b> suggested{basis.suggested_usd > basis.ai_usd + basis.paid_spend_usd + 0.01 ? " (rounded up)" : ""}
        {total !== undefined && Math.abs(total - basis.suggested_usd) >= 0.5 && <> · you set <b>{usd(total)}</b></>}
      </div>
      {basis.starter && basis.full_usd ? (
        <div>The whole goal ({Math.round(basis.full_days || 30)} days) would take about {usd(basis.full_usd)}. Add more once you&apos;ve seen results.</div>
      ) : null}
      {pace && (
        <div className="text-brand-700">
          So far it costs ~{usd(pace.per_session_usd)} a session, so the rest covers about {pace.sessions_left} more sessions (~{pace.days_left} days).
        </div>
      )}
      {!compact && <div className="text-muted">It&apos;s a hard limit: when it runs out, work pauses. Quiet sessions cost less than busy ones.</div>}
    </div>
  );
}

/** For the new-goal form: suggest a budget from the schedule, and let people take it. */
export function BudgetCalculator({ cycleHours, endDate, onUse }: { cycleHours: string; endDate: string; onUse: (usd: number) => void }) {
  const [basis, setBasis] = useState<BudgetBasis | null>(null);
  const days = endDate ? Math.max(1, (new Date(endDate + "T23:59:00").getTime() - Date.now()) / 86400000) : 30;
  useEffect(() => {
    api<BudgetBasis>(`/api/estimate?cycle_hours=${cycleHours}&days=${days.toFixed(1)}`).then(setBasis).catch(() => setBasis(null));
  }, [cycleHours, days]);
  if (!basis) return null;
  return (
    <div className="rounded-lg border border-line bg-stone-50 p-3">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[13px] font-semibold"><Calculator size={14} /> How much it will likely need</span>
        <Button size="sm" type="button" onClick={() => onUse(basis.suggested_usd)}>Use {usd(basis.suggested_usd)}</Button>
      </div>
      <BudgetBreakdown basis={basis} compact />
      <p className="mt-1 text-[11.5px] text-muted">Add more if it will run ads or buy things. {endDate ? "" : "Assumes it runs for 30 days; set a deadline to change that."}</p>
    </div>
  );
}
