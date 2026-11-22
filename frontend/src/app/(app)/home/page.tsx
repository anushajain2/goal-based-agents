"use client";

import { ArrowRight, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { GoalProgress, GoalStatus } from "@/components/goal";
import { EmployeeAvatar } from "@/components/Shell";
import { Card, CardHeader, ErrorNote } from "@/components/ui";
import { CATEGORY_ICON, UseCaseCard } from "@/components/UseCaseLibrary";
import { ViewToggle, WorkLog } from "@/components/WorkLog";
import { AgentAvatar } from "@/components/team";
import { ActivityItem, Campaign, num, OrgInfo, Overview, SetupInfo, timeAgo, usd, useApi, UserRequest } from "@/lib/api";
import { CATEGORIES, FEATURED, findUseCase } from "@/lib/useCases";

export default function HomePage() {
  const router = useRouter();
  const { data: ov, error } = useApi<Overview>("/api/overview");
  const { data: goals } = useApi<Campaign[]>("/api/campaigns");
  const { data: requests, reload: reloadRequests } = useApi<UserRequest[]>("/api/requests?status=pending");
  const { data: log } = useApi<ActivityItem[]>("/api/activity?limit=60");
  const { data: org } = useApi<OrgInfo>("/api/org");
  const { data: setup } = useApi<SetupInfo>("/api/org/setup", { live: false, pollMs: 5000 });
  const researching = setup?.setup && ["queued", "running"].includes(setup.setup.status);
  const [view, setView] = useState<"highlights" | "everything">("highlights");

  if (error) return <ErrorNote>Can&apos;t reach the backend ({error}). Is <code>./scripts/dev.sh</code> running?</ErrorNote>;
  if (!ov || !goals) return <p className="text-muted">Loading…</p>;

  const pick = (id: string) => router.push(`/goals/new?uc=${id}`);

  const researchBanner = researching && (
    <Link href="/setup" className="flex items-center gap-3 rounded-xl border border-brand-500/30 bg-brand-50/60 px-4 py-3 text-sm hover:bg-brand-50">
      <Sparkles size={16} className="animate-pulse text-brand-600" />
      <span className="flex-1">Autopilot is researching {setup?.org.name} to set up your AI team and suggest goals.</span>
      <span className="font-semibold text-brand-600">See progress →</span>
    </Link>
  );
  if (goals.length === 0) return <div className="space-y-4">{researchBanner}<FirstRun onPick={pick} org={org} /></div>;
  const suggested = goals.filter((g) => g.origin === "setup" && g.status === "draft" && g.can_manage !== false);
  const team = (org?.departments || []).flatMap((d) => d.agents.map((a) => ({ ...a, dept: d.name })));

  const state = ov.working_on.length ? "working" : ov.waiting_on_you ? "waiting" : "idle";
  return (
    <div className="space-y-6">
      {/* The employee, at a glance */}
      <Card className="flex flex-wrap items-center gap-4 p-5">
        <EmployeeAvatar state={state} size={52} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-muted">{org ? `${org.org.name} · ${team.length} AI employees` : "Your AI team"}</div>
          <div className="mt-0.5 text-xl font-bold leading-snug">
            {state === "working" ? <>Working on {ov.working_on.join(", ")}</>
              : state === "waiting" ? <>Waiting on you for {ov.waiting_on_you} {ov.waiting_on_you === 1 ? "decision" : "decisions"}</>
              : ov.goals.active ? <>Between work sessions{ov.next_check_in ? <>: next check-in {timeAgo(ov.next_check_in)}</> : null}</>
              : <>No active goals right now</>}
          </div>
          {ov.now && state === "working" && (
            <div className="mt-1 flex items-center gap-2 text-sm text-brand-700">
              <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-brand-500" />
              <span className="truncate">{ov.now.title}</span>
            </div>
          )}
        </div>
        <Link href="/goals/new" className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600">
          <Plus size={16} /> New goal
        </Link>
        {team.length > 0 && (
          <div className="flex w-full flex-wrap gap-2 border-t border-line pt-3">
            {team.map((a) => (
              <Link key={a.id} href={`/team/agents/${a.id}`} className="inline-flex items-center gap-2 rounded-full border border-line py-1 pl-1 pr-3 text-xs hover:bg-gray-50">
                <AgentAvatar name={a.name} size={24} state={a.working ? "working" : a.needs_you ? "waiting" : "idle"} />
                <span className="font-semibold">{a.name}</span>
                <span className="text-muted">{a.working ? "working" : a.needs_you ? "needs a yes" : a.active_goals ? `${a.active_goals} active` : "idle"}</span>
              </Link>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Spent this month" value={usd(ov.spend_this_month.total)} sub={`AI ${usd(ov.spend_this_month.ai_usage)} · other ${usd(ov.spend_this_month.other)}`} />
        <Stat label="Actions this week" value={num(ov.actions_this_week)} sub={`${num(ov.steps_this_week)} ${ov.steps_this_week === 1 ? "step" : "steps"} in total`} />
        <Stat label="Active goals" value={`${ov.goals.active}`} sub={`${ov.goals.total} in total`} />
        <Stat label="Needs you" value={`${ov.waiting_on_you}`} sub={ov.waiting_on_you ? "Approvals and sign-ins" : "Nothing waiting"} highlight={ov.waiting_on_you > 0} />
      </div>

      {researchBanner}
      {suggested.length > 0 && (
        <Card>
          <CardHeader
            title={<span className="flex items-center gap-2"><Sparkles size={15} className="text-brand-600" /> {suggested.length} suggested {suggested.length === 1 ? "goal is" : "goals are"} ready to start</span>}
            subtitle="Picked for where your company is right now. Review, then start the ones you want."
            action={<Link href="/setup" className="text-sm font-semibold text-brand-600">Review all →</Link>}
          />
          <ul className="divide-y divide-line">
            {suggested.slice(0, 4).map((g) => (
              <li key={g.id}>
                <Link href={`/goals/${g.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[13px] hover:bg-gray-50">
                  <span className="min-w-0 flex-1 font-semibold">{g.name}</span>
                  <span className="text-xs text-muted">{g.agent?.name} · {usd(g.budget.total)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {requests && requests.length > 0 && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[15px] font-bold">Needs you</h2>
            {requests.length > 2 && <Link href="/approvals" className="text-sm font-semibold text-brand-600">All {requests.length} →</Link>}
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {requests.slice(0, 2).map((r) => <ApprovalCard key={r.id} req={r} onDone={reloadRequests} showCampaign />)}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader
            title="Work log"
            subtitle="Everything your AI employees have done recently, across all goals"
            action={<ViewToggle value={view} onChange={setView} />}
          />
          <div className="p-3">
            <WorkLog items={log || []} showGoal view={view} />
          </div>
          <Link href="/work" className="flex items-center justify-center gap-1 border-t border-line py-2.5 text-sm font-semibold text-brand-600 hover:bg-gray-50">
            Full work log <ArrowRight size={14} />
          </Link>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Goals" action={<Link href="/goals" className="text-sm font-semibold text-brand-600">All →</Link>} />
            <ul className="divide-y divide-line">
              {goals.slice(0, 6).map((c) => (
                <li key={c.id}>
                  <Link href={`/goals/${c.id}`} className="block px-4 py-3 hover:bg-gray-50">
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate text-[13.5px] font-semibold">{c.name}</span>
                        {c.client_name && <span className="text-xs text-muted">for {c.client_name}</span>}
                      </span>
                      <GoalStatus c={c} />
                    </div>
                    <div className="mt-2 grid grid-cols-[1fr_auto] items-end gap-3">
                      <GoalProgress c={c} compact />
                      <span className="tabular text-xs text-muted">{usd(c.budget.spent)} / {usd(c.budget.total)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="More it can do" subtitle="Ideas founders and agencies give their AI employees" action={<Link href="/capabilities" className="text-sm font-semibold text-brand-600">Browse →</Link>} />
            <ul className="divide-y divide-line">
              {FEATURED.slice(0, 4).map((id) => {
                const uc = findUseCase(id)!;
                return (
                  <li key={id}>
                    <button onClick={() => pick(id)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50">
                      <span className="mt-0.5 text-gray-400">{CATEGORY_ICON[uc.categoryKey]}</span>
                      <span className="text-[13px] leading-snug">{uc.goal}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <Card className={highlight ? "border-amber-300 bg-amber-50/50 p-4" : "p-4"}>
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

function FirstRun({ onPick, org }: { onPick: (id: string) => void; org: OrgInfo | null }) {
  const count = (org?.departments || []).reduce((n, d) => n + d.agents.length, 0);
  return (
    <div className="space-y-8">
      <div className="rounded-2xl bg-gradient-to-br from-brand-500 to-violet-600 p-8 text-white">
        <EmployeeAvatar size={56} />
        <h1 className="mt-4 text-3xl font-bold tracking-tight">{org ? `${org.org.name} has ${count} AI employees ready to work` : "Meet your AI team"}</h1>
        <p className="mt-2 max-w-2xl text-white/85">
          Give one a goal with a clear finish line and a budget, like &quot;book 20 qualified meetings&quot; or &quot;get 500 waitlist signups&quot;. It plans,
          does the work, asks the people in its department before anything important, and logs every step so you always know what it did and what it cost.
        </p>
        <Link href="/goals/new" className="mt-5 inline-flex h-10 items-center gap-1.5 rounded-lg bg-white px-4 text-sm font-semibold text-brand-700 hover:bg-white/90">
          <Plus size={16} /> Give the first goal
        </Link>
      </div>
      <section>
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 className="text-lg font-bold">Popular first goals</h2>
            <p className="text-sm text-muted">Pick one to start; you can change everything before it begins.</p>
          </div>
          <Link href="/capabilities" className="text-sm font-semibold text-brand-600">See all {CATEGORIES.length} areas →</Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURED.map((id) => <UseCaseCard key={id} uc={findUseCase(id)!} onPick={(u) => onPick(u.id)} />)}
        </div>
      </section>
    </div>
  );
}
