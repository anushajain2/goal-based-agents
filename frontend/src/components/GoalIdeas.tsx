"use client";

import { ArrowRight, CheckCircle2, Eye, Hand, Search, Sparkles, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { GoalPanel } from "./GoalPanel";
import { Opportunities } from "./Opportunities";
import { StartGoal } from "./StartGoal";
import { UseCaseLibrary } from "./UseCaseLibrary";
import { Campaign, OrgInfo, usd } from "@/lib/api";
import { USE_CASES } from "@/lib/useCases";

/** The Goals page's "Goal ideas" tab: what the company check found (with the goal that fixes
 *  each), other suggested goals not started yet, and the library of ideas. */
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
        <section className="space-y-3 rounded-3xl border border-line bg-white/60 p-5">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> Recommended for {org!.org.name}</h2>
            <p className="text-sm text-muted">
              From the check we ran{found!.scanned_at ? ` on ${new Date(found!.scanned_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : ""}.
              Nothing runs, and nothing is spent, until you turn a goal on.
            </p>
          </div>
          <Opportunities profile={org!.org.profile} org={org} goals={goals} orgName={org!.org.name} canStart
            onStart={setStarting} onOpen={setPanel} titled={false} preview={2} />
        </section>
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <How icon={<CheckCircle2 size={18} />} title="You set the finish line" text="Each goal says exactly when a result counts, so you can judge the work." />
          <How icon={<Wallet size={18} />} title="It stays within budget" text="A hard spending limit, with the cost of every work session shown." />
          <How icon={<Hand size={18} />} title="It asks first" text="Posting, messaging and spending wait for your OK until you say otherwise." />
          <How icon={<Eye size={18} />} title="You see everything" text="Every plan, step, action and decision is in the work log." />
        </div>
        <UseCaseLibrary onPick={(u) => router.push(`/goals/new?uc=${u.id}`)} onCustom={() => router.push("/goals/new")} />
      </section>

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); onChanged(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); onChanged(); }} />}
    </div>
  );
}

function How({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="text-brand-600">{icon}</div>
      <div className="mt-2 text-[13.5px] font-semibold">{title}</div>
      <div className="mt-0.5 text-xs text-muted">{text}</div>
    </div>
  );
}
