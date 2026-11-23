"use client";

import { ArrowRight, Flag, Lock, Play, Sparkles, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, Campaign, Playbook, usd } from "@/lib/api";
import { StepList, teamName, usePermissions } from "./GoalPlan";
import { AgentAvatar } from "./team";
import { Button } from "./ui";

/** One goal, explained in the order people want to know it: what you get, how, what it costs. */
export function GoalPanel({ goal, onClose, onStart, onRemoved }: {
  goal: Campaign; onClose: () => void; onStart?: (g: Campaign) => void; onRemoved?: () => void;
}) {
  const [book, setBook] = useState<Playbook | null>(null);
  const { perms } = usePermissions(goal.id);
  useEffect(() => {
    api<Playbook>(`/api/campaigns/${goal.id}/playbook`, { method: "POST" }).then(setBook).catch(() => setBook(null));
  }, [goal.id]);
  const modeOf = (k: string) => perms?.action_types.find((p) => p.key === k)?.mode ?? "ask";
  const team = perms ? teamName(perms) : "your team";
  const basis = goal.budget_basis;
  const draft = goal.status === "draft" && goal.can_manage !== false;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="flex h-full w-full max-w-md flex-col bg-white shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-3">
          {goal.agent && <AgentAvatar name={goal.agent.name} size={30} />}
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{goal.agent?.name}</div>
            <div className="text-xs text-muted">{goal.department?.name}</div>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-gray-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <h2 className="text-lg font-bold leading-snug">{goal.name}</h2>

          <section className="rounded-xl bg-brand-50 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-wide text-brand-700">{goal.first_deliverable ? "In your first week you get" : "The goal"}</div>
            <p className="mt-1 text-[15px] leading-snug text-ink">{goal.first_deliverable || goal.goal_description}</p>
          </section>

          <section>
            <h3 className="mb-2.5 text-[11px] font-bold uppercase tracking-wide text-muted">How it works</h3>
            {book && perms ? <StepList steps={book.steps} modeOf={modeOf} team={team} /> : <p className="text-sm text-muted">Working out the steps…</p>}
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-900">
              <Lock size={14} className="mt-0.5 shrink-0" /> Nothing goes out without a yes from {team}. You see each message, post or payment first and can edit it.
            </p>
          </section>

          {goal.done_when && (
            <section>
              <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-muted">Counts as done when</h3>
              <p className="flex gap-1.5 text-[13px]"><Flag size={13} className="mt-0.5 shrink-0 text-muted" /> {goal.done_when}</p>
            </section>
          )}

          <section>
            <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-muted">Cost</h3>
            {basis?.starter ? (
              <p className="text-[13px]">
                <b>{usd(goal.budget.total)}</b> covers the first week (about {basis.sessions} work sessions). The whole goal would take about{" "}
                {usd(basis.full_usd || 0)} over {Math.round(basis.full_days || 30)} days; add more once you&apos;ve seen results.
              </p>
            ) : (
              <p className="text-[13px]"><b>{usd(goal.budget.total)}</b> in total{basis ? ` (about ${basis.sessions} work sessions)` : ""}. Work pauses if it runs out.</p>
            )}
          </section>

          {goal.suggested_reason && (
            <section>
              <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-muted">Why this goal</h3>
              <p className="flex gap-1.5 text-[13px] text-gray-700"><Sparkles size={13} className="mt-0.5 shrink-0 text-brand-600" /> {goal.suggested_reason}</p>
            </section>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
          {draft && onStart && <Button variant="primary" onClick={() => onStart(goal)}><Play size={15} /> Start</Button>}
          <Link href={`/goals/${goal.id}`} className="inline-flex h-9 items-center gap-1 rounded-lg px-3 text-sm font-semibold text-brand-600 hover:bg-brand-50">
            Full details <ArrowRight size={14} />
          </Link>
          {draft && onRemoved && (
            <button className="ml-auto inline-flex items-center gap-1 text-sm text-muted hover:text-red-600"
              onClick={async () => { if (confirm(`Remove "${goal.name}"?`)) { await api(`/api/campaigns/${goal.id}`, { method: "DELETE" }); onRemoved(); } }}>
              <Trash2 size={14} /> Remove
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}
