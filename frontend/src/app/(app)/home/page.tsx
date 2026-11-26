"use client";

import { ArrowRight, Check, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { KIND_BADGE } from "@/components/ApprovalCard";
import { GoalProgress } from "@/components/goal";
import { EmployeeAvatar } from "@/components/Shell";
import { ConnectChecklist } from "@/components/ConnectChecklist";
import { TargetLine } from "@/components/Target";
import { Badge, Card, cx, ErrorNote, PageHeader } from "@/components/ui";
import { CATEGORY_ICON, UseCaseCard } from "@/components/UseCaseLibrary";
import { WorkLog } from "@/components/WorkLog";
import { YourRole } from "@/components/YourRole";
import { MissingSummary } from "@/components/Opportunities";
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

  if (error) return <ErrorNote>Can&apos;t reach the backend ({error}). Is <code>./scripts/dev.sh</code> running?</ErrorNote>;
  if (!ov || !goals) return <p className="text-muted">Loading…</p>;

  const pick = (id: string) => router.push(`/goals/new?uc=${id}`);

  const researchBanner = researching && (
    <Link href="/setup" className="flex items-center gap-3 rounded-xl border border-brand-500/30 bg-brand-50/60 px-4 py-3 text-sm hover:bg-brand-50">
      <Sparkles size={16} className="animate-pulse text-brand-600" />
      <span className="flex-1">Oton is researching {setup?.org.name} to suggest goals for every team.</span>
      <span className="font-semibold text-brand-600">See progress →</span>
    </Link>
  );
  if (goals.length === 0) return <div className="space-y-4">{researchBanner}<FirstRun onPick={pick} org={org} /></div>;
  const suggested = goals.filter((g) => g.origin === "setup" && g.status === "draft" && g.can_manage !== false);

  const state = ov.working_on.length ? "working" : ov.waiting_on_you ? "waiting" : "idle";
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const live = goals.filter((g) => g.status === "active");
  const onTrack = live.filter((g) => g.target?.status === "active" && g.target.target && g.target.progress != null
    && g.target.progress / g.target.target >= Math.max(0, 1 - (g.target.days_left ?? 0) / ({ week: 7, month: 30, quarter: 91 }[g.target.period || "week"]) - 0.15)).length;
  const firstName = (org?.me.name || "").split(" ")[0];

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        title={`${hello}${firstName ? `, ${firstName}` : ""}`}
        subtitle={<>
          {live.length} live goal{live.length === 1 ? "" : "s"}
          {ov.waiting_on_you ? <> · <Link href="/approvals" className="font-semibold text-signal-700 hover:underline">{ov.waiting_on_you} {ov.waiting_on_you === 1 ? "thing needs" : "things need"} you</Link></> : " · nothing needs you"}
        </>}
        actions={<Link href="/goals/new" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white shadow-sm hover:bg-brand-600"><Plus size={16} /> New goal</Link>}
      />

      {state === "working" && ov.now && (
        <div className="flex items-center gap-3 rounded-2xl border border-brand-100 bg-gradient-to-r from-brand-50 to-white px-4 py-3">
          <span className="signal-dot" />
          <span className="min-w-0 flex-1 truncate text-[13.5px]"><b className="font-semibold">Working now</b> <span className="text-stone-600">· {ov.now.title}</span></span>
          <Link href="/work" className="shrink-0 text-[13px] font-semibold text-brand-700 hover:underline">Watch</Link>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat href="/approvals" label="Needs you" value={`${ov.waiting_on_you}`} sub={ov.waiting_on_you ? "Waiting for a yes" : "All caught up"} tone={ov.waiting_on_you ? "amber" : undefined} />
        <Stat href="/goals" label="On target" value={`${onTrack}/${live.length}`} sub="live goals on pace" />
        <Stat href="/work" label="Done this week" value={num(ov.actions_this_week)} sub="actions taken" />
        <Stat href="/settings" label="Spent this month" value={usd(ov.spend_this_month.total)} sub={ov.budget_total ? `of ${usd(ov.budget_total)} budgeted` : "No budgets yet"} />
      </div>

      <YourRole />
      <MissingSummary profile={org?.org.profile} goals={goals} />
      {researchBanner}
      <ConnectChecklist only="missing_live" />
      {suggested.length > 0 && (
        <Link href="/setup" className="flex items-center gap-4 rounded-2xl bg-brand-600 px-5 py-4 text-white shadow-[var(--shadow-pop)] transition hover:brightness-105">
          <Sparkles size={20} className="shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="block font-semibold">{suggested.length} suggested {suggested.length === 1 ? "goal is" : "goals are"} ready to start</span>
            <span className="block text-[13px] text-white/80">Picked for where {org?.org.name || "your company"} is right now</span>
          </span>
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/15 px-3 py-1.5 text-sm font-semibold">Review <ArrowRight size={14} /></span>
        </Link>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-8">
          <section>
            <SectionTitle title="Needs you" href="/approvals" link="Open inbox" />
            {requests && requests.length > 0 ? (
              <Card className="divide-y divide-line overflow-hidden">
                {requests.slice(0, 4).map((r) => {
                  const k = KIND_BADGE[r.kind] || KIND_BADGE.action;
                  return (
                    <Link key={r.id} href={`/approvals?id=${r.id}`} className="flex items-center gap-3 px-4 py-3 transition hover:bg-stone-50">
                      <EmployeeAvatar size={32} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-medium">{r.kind === "question" ? r.preview.question || r.title : r.title}</span>
                        <span className="block truncate text-[12px] text-muted">{r.campaign_name || "Oton"} · {timeAgo(r.created_at)}</span>
                      </span>
                      <Badge tone={k.tone}>{k.label}</Badge>
                      <ArrowRight size={15} className="shrink-0 text-stone-300" />
                    </Link>
                  );
                })}
              </Card>
            ) : (
              <Card className="flex items-center gap-3 px-4 py-4 text-[14px] text-muted">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-emerald-50 text-emerald-600"><Check size={16} /></span>
                You&apos;re all caught up. Oton will ask here before anything important.
              </Card>
            )}
          </section>

          <section>
            <SectionTitle title="Your teams" href="/team" link="Org chart" />
            <div className="grid gap-3 sm:grid-cols-2">
              {(org?.departments || []).filter((d) => d.agents.length).map((d) => {
                const dGoals = goals.filter((g) => d.agents.some((a) => a.id === g.agent?.id));
                const dLive = dGoals.filter((g) => g.status === "active");
                const health = d.lead?.last?.status === "done" ? d.lead.last.health : "";
                return (
                  <Link key={d.id} href="/team" className="group rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pop)]">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-[15px] font-semibold">{d.name}</span>
                      {health && <Badge tone={health === "on_track" ? "green" : health === "mixed" ? "amber" : "red"}>{health === "on_track" ? "On track" : health === "mixed" ? "Mixed" : "Off track"}</Badge>}
                    </div>
                    <div className="mt-0.5 text-[12px] text-muted">{dGoals.length} goal{dGoals.length === 1 ? "" : "s"} · {dLive.length} live</div>
                    <div className="mt-3 space-y-2.5">
                      {dLive.slice(0, 3).map((g) => (
                        <div key={g.id}>
                          <div className="mb-1 truncate text-[12.5px] font-medium text-stone-700">{g.name}</div>
                          {g.target?.target ? <TargetLine goal={g} compact /> : <GoalProgress c={g} compact />}
                        </div>
                      ))}
                      {dLive.length === 0 && <p className="text-[12.5px] text-muted">{dGoals.length ? `${dGoals.length} goal${dGoals.length === 1 ? "" : "s"} ready to start` : "No goals yet"}</p>}
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        </div>

        <aside className="space-y-8">
          <section>
            <SectionTitle title="Latest work" href="/work" link="Work log" />
            <Card className="p-2">
              <WorkLog items={(log || []).slice(0, 8)} showGoal view="highlights" />
            </Card>
          </section>
          <section>
            <SectionTitle title="Goal ideas" href="/goals?tab=ideas" link="Browse" />
            <Card className="divide-y divide-line overflow-hidden">
              {FEATURED.slice(0, 3).map((id) => {
                const uc = findUseCase(id)!;
                return (
                  <button key={id} onClick={() => pick(id)} className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-stone-50">
                    <span className="mt-0.5 text-stone-400">{CATEGORY_ICON[uc.categoryKey]}</span>
                    <span className="text-[13px] leading-snug">{uc.goal}</span>
                  </button>
                );
              })}
            </Card>
          </section>
        </aside>
      </div>
    </div>
  );
}

function SectionTitle({ title, href, link }: { title: string; href: string; link: string }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[16px] font-semibold">{title}</h2>
      <Link href={href} className="inline-flex items-center gap-0.5 text-[13px] font-semibold text-muted hover:text-ink">{link} <ArrowRight size={13} /></Link>
    </div>
  );
}

function Stat({ label, value, sub, tone, href }: { label: string; value: string; sub?: string; tone?: "amber"; href: string }) {
  return (
    <Link href={href} className={cx("rounded-2xl border bg-white p-4 shadow-[var(--shadow-card)] transition hover:shadow-[var(--shadow-pop)]",
      tone === "amber" ? "border-signal-200 bg-gradient-to-b from-signal-50 to-white" : "border-line")}>
      <div className="text-[12.5px] font-medium text-muted">{label}</div>
      <div className={cx("tabular mt-1 text-[28px] font-semibold leading-none tracking-tight", tone === "amber" && "text-signal-700")}>{value}</div>
      {sub && <div className="mt-1.5 text-[12px] text-muted">{sub}</div>}
    </Link>
  );
}

function FirstRun({ onPick, org }: { onPick: (id: string) => void; org: OrgInfo | null }) {
  return (
    <div className="space-y-8">
      <div className="rounded-3xl bg-brand-600 p-10 text-white shadow-[var(--shadow-pop)]">
        <EmployeeAvatar size={56} />
        <h1 className="mt-4 text-3xl font-bold tracking-tight">{org ? `Oton is ready to work for ${org.org.name}` : "Meet Oton"}</h1>
        <p className="mt-2 max-w-2xl text-white/85">
          Give it a goal with a clear finish line and a budget, like &quot;book 20 qualified meetings&quot; or &quot;get 500 waitlist signups&quot;. It plans,
          does the work, asks the right people on your team before anything important, and logs every step so you always know what it did and what it cost.
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
          <Link href="/goals?tab=ideas" className="text-sm font-semibold text-brand-600">See all {CATEGORIES.length} areas →</Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURED.map((id) => <UseCaseCard key={id} uc={findUseCase(id)!} onPick={(u) => onPick(u.id)} />)}
        </div>
      </section>
    </div>
  );
}
