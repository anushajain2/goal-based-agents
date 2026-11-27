"use client";

import { Activity, ArrowRight, Check, Hand, Plus, Sparkles, Zap } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReactNode, useState } from "react";

import { KIND_BADGE } from "@/components/ApprovalCard";
import { GoalProgress } from "@/components/goal";
import { EmployeeAvatar } from "@/components/Shell";
import { ConnectChecklist } from "@/components/ConnectChecklist";
import { TargetLine } from "@/components/Target";
import { Badge, Card, cx, ErrorNote } from "@/components/ui";
import { CATEGORY_ICON, UseCaseCard } from "@/components/UseCaseLibrary";
import { WorkLog } from "@/components/WorkLog";
import { YourRole } from "@/components/YourRole";
import { GoalPanel } from "@/components/GoalPanel";
import { StartGoal } from "@/components/StartGoal";
import { Opportunities } from "@/components/Opportunities";
import { ActivityItem, Campaign, num, Opportunity, OrgInfo, Overview, SetupInfo, timeAgo, usd, useApi, UserRequest } from "@/lib/api";
import { useCountUp, useLiteMotion } from "@/lib/motion";
import { CATEGORIES, FEATURED, findUseCase } from "@/lib/useCases";

const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });

type Gap = { f: Opportunity; goal: Campaign };

export default function HomePage() {
  const router = useRouter();
  const lite = useLiteMotion();
  const { data: ov, error, reload: reloadOv } = useApi<Overview>("/api/overview");
  const { data: goals, reload: reloadGoals } = useApi<Campaign[]>("/api/campaigns");
  const { data: requests } = useApi<UserRequest[]>("/api/requests?status=pending");
  const { data: log } = useApi<ActivityItem[]>("/api/activity?limit=60");
  const { data: org } = useApi<OrgInfo>("/api/org");
  const { data: setup } = useApi<SetupInfo>("/api/org/setup", { live: false, pollMs: 5000 });
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [panel, setPanel] = useState<Campaign | null>(null);
  const researching = setup?.setup && ["queued", "running"].includes(setup.setup.status);

  if (error) return <ErrorNote>Can&apos;t reach the backend ({error}). Is <code>./scripts/dev.sh</code> running?</ErrorNote>;
  if (!ov || !goals) return <p className="text-muted">Loading…</p>;

  const pick = (id: string) => router.push(`/goals/new?uc=${id}`);
  const changed = () => { reloadGoals(); reloadOv(); };

  const researchBanner = researching && (
    <Link href="/setup" className="flex items-center gap-3 rounded-xl border border-brand-500/30 bg-brand-50/60 px-4 py-3 text-sm hover:bg-brand-50">
      <Sparkles size={16} className="animate-pulse text-brand-600" />
      <span className="flex-1">Oton is researching {setup?.org.name} to find what you&apos;re missing out on.</span>
      <span className="font-semibold text-brand-600">See progress →</span>
    </Link>
  );
  if (goals.length === 0) return <div className="space-y-4">{researchBanner}<FirstRun onPick={pick} org={org} /></div>;

  // The company check's findings, each with the goal that fixes it: open (not on yet) or being fixed.
  const byId = new Map(goals.map((g) => [g.id, g]));
  const gaps: Gap[] = (org?.org.profile?.opportunities?.findings || [])
    .map((f) => ({ f, goal: f.goal_id ? byId.get(f.goal_id) : undefined }))
    .filter((x): x is Gap => !!x.goal);
  const open = gaps.filter((x) => x.goal.status === "draft");
  const fixing = gaps.filter((x) => x.goal.status !== "draft");
  const fixIds = new Set(gaps.map((x) => x.goal.id));
  const otherIdeas = goals.filter((g) => g.origin === "setup" && g.status === "draft" && g.can_manage !== false && !fixIds.has(g.id));

  const live = goals.filter((g) => g.status === "active");
  const onTrack = live.filter((g) => g.target?.status === "active" && g.target.target && g.target.progress != null
    && g.target.progress / g.target.target >= Math.max(0, 1 - (g.target.days_left ?? 0) / ({ week: 7, month: 30, quarter: 91 }[g.target.period || "week"]) - 0.15)).length;
  const results = goals.reduce((n, g) => n + (g.status !== "draft" ? g.results.results || 0 : 0), 0);
  const actionsEver = goals.reduce((n, g) => n + (g.actions_taken || 0), 0);

  const work = (log || []).filter((a) => a.kind !== "system");
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const firstName = (org?.me.name || "").split(" ")[0];
  const orgName = org?.org.name || "your company";

  return (
    <div className="space-y-8">
      <Pulse
        lite={lite} ov={ov} log={log || []} hello={`${hello}${firstName ? `, ${firstName}` : ""}`} orgName={orgName}
        live={live.length} onTrack={onTrack} results={results} actionsEver={actionsEver} open={open} fixing={fixing}
        ideas={otherIdeas} onStart={(g) => setStarting([g])}
      />

      {researchBanner}
      <ConnectChecklist only="missing_live" />

      {open.length > 0 && (
        <section id="found" className="scroll-mt-6">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-[20px] font-bold tracking-tight">What we found for {orgName}</h2>
              <p className="text-[13.5px] text-muted">Gaps and opportunities to grow, each with a fix ready to turn on. Nothing runs or costs anything until you do.</p>
            </div>
            <Link href="/opportunities" className="inline-flex items-center gap-0.5 text-[13px] font-semibold text-muted hover:text-ink">All findings <ArrowRight size={13} /></Link>
          </div>
          <Opportunities profile={org?.org.profile} org={org} goals={goals} orgName={orgName} canStart
            onStart={setStarting} onOpen={setPanel} titled={false} preview={3} recheck={false}
            only={(f) => !!f.goal_id && byId.get(f.goal_id)?.status === "draft"} />
        </section>
      )}

      {otherIdeas.length > 0 && (
        <Link href="/goals?tab=ideas" className="group flex items-center gap-4 rounded-2xl border border-line bg-white px-5 py-4 shadow-[var(--shadow-card)] transition hover:border-stone-300 hover:shadow-[var(--shadow-pop)]">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100"><Sparkles size={18} /></span>
          <span className="min-w-0 flex-1">
            <span className="block text-[14.5px] font-semibold">{gaps.length ? `${otherIdeas.length} more goals` : `${otherIdeas.length} suggested goals`} picked for {orgName}, ready to turn on</span>
            <span className="block truncate text-[13px] text-muted">{otherIdeas.slice(0, 3).map((g) => g.name).join(" · ")}</span>
          </span>
          <span className="inline-flex shrink-0 items-center gap-1 text-[13px] font-semibold text-brand-700">Review <ArrowRight size={14} className="transition group-hover:translate-x-0.5" /></span>
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
                  <Link key={d.id} href={dLive.length ? "/team" : "/goals?tab=ideas"} className="group rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pop)]">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-[15px] font-semibold">{d.name}</span>
                      {dLive.length > 0
                        ? health
                          ? <Badge tone={health === "on_track" ? "green" : health === "mixed" ? "amber" : "red"}>{health === "on_track" ? "On track" : health === "mixed" ? "Mixed" : "Off track"}</Badge>
                          : <Badge tone="green"><span className="signal-dot scale-75" /> Working</Badge>
                        : <Badge tone="gray">Idle</Badge>}
                    </div>
                    <div className="mt-0.5 text-[12px] text-muted">{dGoals.length} goal{dGoals.length === 1 ? "" : "s"} · {dLive.length} live</div>
                    <div className="mt-3 space-y-2.5">
                      {dLive.slice(0, 3).map((g) => (
                        <div key={g.id}>
                          <div className="mb-1 truncate text-[12.5px] font-medium text-stone-700">{g.name}</div>
                          {g.target?.target ? <TargetLine goal={g} compact /> : <GoalProgress c={g} compact />}
                        </div>
                      ))}
                      {dLive.length === 0 && (
                        <p className="flex items-center justify-between gap-2 text-[12.5px]">
                          <span className="text-muted">{dGoals.length ? "Nothing running for this team" : "No goals yet"}</span>
                          {dGoals.length > 0 && <span className="inline-flex items-center gap-0.5 font-semibold text-brand-700">{dGoals.length} ready <ArrowRight size={12} /></span>}
                        </p>
                      )}
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
              {work.length ? <WorkLog items={work.slice(0, 8)} showGoal view="highlights" />
                : <p className="px-3 py-4 text-[13px] text-muted">Work shows up here as it happens: every draft, step and result.</p>}
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

      <YourRole />

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); changed(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); changed(); }} />}
    </div>
  );
}

/** The top of Home: what Oton has done for you, or what you're missing while it sits idle, with the next move. */
function Pulse({ lite, ov, log, hello, orgName, live, onTrack, results, actionsEver, open, fixing, ideas, onStart }: {
  lite: boolean; ov: Overview; log: ActivityItem[]; hello: string; orgName: string; live: number; onTrack: number;
  results: number; actionsEver: number; open: Gap[]; fixing: Gap[]; ideas: Campaign[]; onStart: (g: Campaign) => void;
}) {
  const delivered = actionsEver > 0 || results > 0;
  const top = open.find((x) => x.goal.can_manage !== false);

  let headline: ReactNode;
  let sub: ReactNode;
  if (delivered) {
    headline = ov.actions_this_week > 0
      ? <><Num n={ov.actions_this_week} /> things done for {orgName} <span className="text-lime-300">this week</span></>
      : <><Num n={actionsEver} /> things done for {orgName} <span className="text-lime-300">so far</span></>;
    sub = <>
      {results > 0 && <><b className="font-semibold text-white">{num(results)} results</b> so far. </>}
      {live > 0 ? `${live} goal${live === 1 ? " is" : "s are"} live. ` : <span className="text-amber-200">Nothing is running right now. </span>}
      {open.length ? <span className="text-amber-200">There&apos;s more to fix, each with a fix ready to turn on.</span>
        : fixing.length ? "Everything we found is being worked on."
          : ideas.length ? `${ideas.length} more goals picked for ${orgName} are ready to turn on.` : ""}
    </>;
  } else if (live > 0) {
    headline = <>Your AI team <span className="text-lime-300">just got to work</span></>;
    sub = <>{live} goal{live === 1 ? " is" : "s are"} live; the first drafts usually land within a day.{open.length ? <> <span className="text-amber-200">More gaps we found still have nothing working on them.</span></> : ""}</>;
  } else if (open.length) {
    headline = <>We found gaps and opportunities for {orgName} to grow. <span className="text-amber-200">Nothing is working on them yet.</span></>;
    sub = <>Each one has a goal ready to go. Nothing runs, and nothing is spent, until you turn it on.</>;
  } else {
    headline = <>Your AI team is <span className="text-amber-200">waiting for its first goal</span></>;
    sub = <>{ideas.length ? `${ideas.length} goals picked for ${orgName} are ready to turn on.` : "Pick a goal and Oton starts working on it today."}</>;
  }

  // Real work only (not "suggested by setup" notes or errors), and only while something is running.
  const feed = log.filter((a) => a.kind !== "system" && a.kind !== "error").slice(0, 5);
  const showFeed = !!ov.now || (live > 0 && feed.length > 0);
  const idle = [...fixing.map((x) => x.goal), ...open.map((x) => x.goal), ...ideas].slice(0, 5);
  const quiet = !delivered && live === 0;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-ink text-white shadow-[var(--shadow-pop)]">
      <div aria-hidden className="absolute inset-0">
        {lite
          ? <div className="h-full w-full bg-[radial-gradient(60%_60%_at_80%_100%,rgba(132,204,22,0.35),transparent)]" />
          : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={0.9} bandHeight={0.2} noiseAmplitude={0.6} speed={0.8} />}
        <div className="absolute inset-0 bg-[linear-gradient(100deg,rgba(21,26,14,0.92)_0%,rgba(21,26,14,0.7)_45%,rgba(21,26,14,0.25)_100%)]" />
      </div>

      <div className="relative grid gap-8 p-6 md:p-8 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rise flex min-w-0 flex-col">
          <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-white/50">
            {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · {hello}
          </div>
          <h1 className="mt-3 max-w-[26ch] text-[28px] font-bold leading-[1.15] tracking-[-0.02em] md:text-[34px]">{headline}</h1>
          <p className="mt-3 max-w-[60ch] text-[14.5px] leading-relaxed text-white/70">{sub}</p>

          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            {ov.waiting_on_you > 0 && (
              <Link href="/approvals" className="inline-flex h-10 items-center gap-2 rounded-xl bg-amber-300 px-4 text-[14px] font-semibold text-ink transition hover:bg-amber-200">
                <Hand size={16} /> {ov.waiting_on_you} {ov.waiting_on_you === 1 ? "thing needs" : "things need"} your yes
              </Link>
            )}
            {top ? (
              <button onClick={() => onStart(top.goal)} className={cx("inline-flex h-10 items-center gap-2 rounded-xl px-4 text-[14px] font-semibold transition",
                ov.waiting_on_you ? "bg-white/10 text-white ring-1 ring-inset ring-white/20 hover:bg-white/15" : "bg-lime-300 text-ink hover:bg-lime-200")}>
                <Zap size={16} /> Turn on the top fix
              </button>
            ) : ideas.length > 0 ? (
              <Link href="/goals?tab=ideas" className="inline-flex h-10 items-center gap-2 rounded-xl bg-lime-300 px-4 text-[14px] font-semibold text-ink transition hover:bg-lime-200">
                <Sparkles size={16} /> Review {ideas.length} suggested goals
              </Link>
            ) : (
              <Link href="/goals/new" className="inline-flex h-10 items-center gap-2 rounded-xl bg-lime-300 px-4 text-[14px] font-semibold text-ink transition hover:bg-lime-200">
                <Plus size={16} /> New goal
              </Link>
            )}
            {open.length > 1 && (
              <a href="#found" className="inline-flex h-10 items-center gap-1 px-2 text-[13.5px] font-semibold text-white/70 transition hover:text-white">
                See what we found <ArrowRight size={14} />
              </a>
            )}
          </div>

          {!quiet && <div className="mt-auto grid grid-cols-2 gap-x-6 gap-y-4 pt-8 sm:grid-cols-4">
            <Mini href="/approvals" label="Needs you" value={<Num n={ov.waiting_on_you} />} hot={ov.waiting_on_you > 0} />
            <Mini href="/goals" label="Live goals on pace" value={<><Num n={onTrack} /><span className="text-white/40">/{live}</span></>} />
            <Mini href="/work" label="Done this week" value={<Num n={ov.actions_this_week} />} />
            <Mini href="/settings" label="Spent this month" value={usd(ov.spend_this_month.total)} sub={ov.budget_total ? `of ${usd(ov.budget_total)}` : undefined} />
          </div>}
        </div>

        <div className="rise min-w-0 rounded-2xl bg-white/[0.06] p-4 ring-1 ring-inset ring-white/10 backdrop-blur-sm" style={{ animationDelay: "150ms" }}>
          {showFeed ? (
            <>
              <div className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-white/50">
                {ov.now ? <><span className="signal-dot" /> Working now</> : <><Activity size={13} /> Latest from your AI team</>}
              </div>
              {ov.now && (
                <Link href="/work" className="mb-2 block rounded-xl bg-lime-300/10 px-3 py-2.5 ring-1 ring-inset ring-lime-300/25 transition hover:bg-lime-300/15">
                  <span className="block truncate text-[13.5px] font-semibold text-lime-100">{ov.now.title}</span>
                  <span className="block truncate text-[11.5px] text-white/50">{ov.now.campaign_name || "Oton"}</span>
                </Link>
              )}
              <ul className="space-y-0.5">
                {feed.filter((a) => a.id !== ov.now?.id).slice(0, ov.now ? 4 : 5).map((a, i) => (
                  <li key={a.id} className="rise" style={{ animationDelay: `${250 + i * 90}ms` }}>
                    <Link href={a.campaign_id ? `/goals/${a.campaign_id}` : "/work"} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition hover:bg-white/5">
                      <span className={cx("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", a.status === "failed" ? "bg-red-400" : "bg-lime-300")} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] text-white/90">{a.title}</span>
                        <span className="block truncate text-[11.5px] text-white/40">{a.campaign_name ? `${a.campaign_name} · ` : ""}{timeAgo(a.created_at)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <div className="mb-1 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-white/50">
                <span className="h-2 w-2 rounded-full bg-white/30" /> Right now: idle
              </div>
              <p className="mb-3 text-[12.5px] text-white/50">What Oton could be doing for {orgName} today:</p>
              <ul className="space-y-1.5">
                {idle.map((goal, i) => {
                  const on = goal.status !== "draft";
                  return (
                    <li key={goal.id} className="rise flex items-center gap-2.5 rounded-lg border border-dashed border-white/15 px-3 py-2" style={{ animationDelay: `${250 + i * 90}ms` }}>
                      <span className={cx("min-w-0 flex-1 truncate text-[13px]", on ? "text-white/90" : "text-white/55")}>{goal.name}</span>
                      {on ? <span className="rounded-full bg-lime-300/15 px-2 py-0.5 text-[11px] font-semibold text-lime-200">On</span>
                        : goal.can_manage !== false
                          ? <button onClick={() => onStart(goal)} className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-white/70 transition hover:bg-lime-300 hover:text-ink">Off · turn on</button>
                          : <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-white/50">Off</span>}
                    </li>
                  );
                })}
                {!idle.length && <li className="text-[13px] text-white/55">No goals set up yet.</li>}
              </ul>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Num({ n }: { n: number }) {
  const [ref, v] = useCountUp(n);
  return <span ref={ref} className="tabular-nums">{num(Math.round(v))}</span>;
}

function Mini({ href, label, value, sub, hot }: { href: string; label: string; value: ReactNode; sub?: string; hot?: boolean }) {
  return (
    <Link href={href} className="group min-w-0">
      <div className={cx("text-[26px] font-semibold leading-none tracking-tight", hot ? "text-amber-300" : "text-white")}>{value}</div>
      <div className="mt-1.5 truncate text-[12px] text-white/50 transition group-hover:text-white/80">{label}{sub ? ` · ${sub}` : ""}</div>
    </Link>
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
