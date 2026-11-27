"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, Eye, Hand, Sparkles, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { GoalPanel } from "./GoalPanel";
import { StartGoal } from "./StartGoal";
import { UseCaseLibrary } from "./UseCaseLibrary";
import { Campaign, OrgInfo, usd } from "@/lib/api";
import { USE_CASES } from "@/lib/useCases";

/** The Goals page's "Goal ideas" tab: a pointer to what the company check found (on Find
 *  opportunities), other suggested goals not started yet, and the library of ideas. */
export function GoalIdeas({ org, goals, onChanged }: { org: OrgInfo | null | undefined; goals: Campaign[] | null | undefined; onChanged: () => void }) {
  const router = useRouter();
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const found = org?.org.profile?.opportunities;
  const recommended = !!found && found.findings.length > 0;
  const fixes = new Set((found?.findings || []).flatMap((f) => [f.goal_id, ...(f.milestones || []).map((m) => m.goal_id)]).filter(Boolean));
  const others = (goals || []).filter((g) => g.status === "draft" && g.origin === "setup" && !fixes.has(g.id) && g.can_manage !== false);

  return (
    <div className="space-y-10">
      {recommended && (
        <Link href="/opportunities" className="group flex items-center gap-4 rounded-2xl border border-red-200 bg-red-50/50 px-5 py-4 transition hover:bg-red-50">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-red-700 ring-1 ring-inset ring-red-200"><AlertTriangle size={18} /></span>
          <span className="min-w-0 flex-1">
            <span className="block text-[14.5px] font-semibold">{found!.findings.length} opportunities found for {org!.org.name}</span>
            <span className="block truncate text-[13px] text-muted">{found!.findings.slice(0, 3).map((f) => f.title).join(" · ")}</span>
          </span>
          <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-red-800">See them <ArrowRight size={14} /></span>
        </Link>
      )}

      {others.length > 0 && (
        <section className="space-y-3">
          <div>
            <h2 className="text-lg font-bold">Also suggested for {org?.org.name || "you"}</h2>
            <p className="text-sm text-muted">Set up from what we learned about your company. Open one to see the plan.</p>
          </div>
          <ul className="grid gap-3 md:grid-cols-2">
            {others.map((g) => (
              <li key={g.id} className="flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3.5 shadow-[var(--shadow-card)]">
                <button onClick={() => setPanel(g)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[14.5px] font-semibold">{g.name}</span>
                  <span className="block truncate text-[12.5px] text-muted">
                    {g.department?.name ? `${g.department.name} · ` : ""}{g.first_deliverable || `${usd(g.budget.total)} budget`}
                  </span>
                </button>
                <button onClick={() => setStarting([g])} className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[12.5px] font-semibold text-white hover:bg-brand-700">
                  Turn on <ArrowRight size={13} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="space-y-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Sparkles size={17} className="text-brand-600" /> {recommended || others.length ? "More ideas" : "Goal ideas"}</h2>
          <p className="text-sm text-muted">{USE_CASES.length} goals Oton works well on, across sales, marketing, research, fundraising, hiring and more. Pick one to set it up; you can change everything before it starts.</p>
        </div>
        <ul className="grid gap-x-6 gap-y-3 border-y border-line py-4 sm:grid-cols-2 lg:grid-cols-4">
          <How icon={<CheckCircle2 size={18} />} title="You set the finish line" text="Each goal says exactly when a result counts, so you can judge the work." />
          <How icon={<Wallet size={18} />} title="It stays within budget" text="A hard spending limit, with the cost of every work session shown." />
          <How icon={<Hand size={18} />} title="It asks first" text="Posting, messaging and spending wait for your OK until you say otherwise." />
          <How icon={<Eye size={18} />} title="You see everything" text="Every plan, step, action and decision is in the work log." />
        </ul>
        <UseCaseLibrary onPick={(u) => router.push(`/goals/new?uc=${u.id}`)} onCustom={() => router.push("/goals/new")} />
      </section>

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); onChanged(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); onChanged(); }} />}
    </div>
  );
}

function How({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden className="mt-0.5 shrink-0 text-brand-600">{icon}</span>
      <span className="min-w-0">
        <span className="block text-[13.5px] font-semibold">{title}</span>
        <span className="mt-0.5 block text-[13px] leading-snug text-muted">{text}</span>
      </span>
    </li>
  );
}
