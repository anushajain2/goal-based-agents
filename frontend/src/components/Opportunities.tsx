"use client";

import { AlertTriangle, ArrowRight, Bot, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Flag, Loader2, Plug, RefreshCw, Search, ShieldCheck, Target, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { andMore, api, Campaign, CompanyProfile, Milestone, OrgInfo, Opportunity, ScoreRow, SocialUsed, usd, useApi, Visibility } from "@/lib/api";
import { ProfilesUsed, profileLabel } from "./SocialProfiles";
import { TeamTag } from "./team";
import { cx, ErrorNote } from "./ui";

const CONFIDENCE: Record<Opportunity["confidence"], string> = { high: "Clear signal", medium: "Likely", low: "Worth a look" };

const TEAM_NAMES: Record<string, string> = {
  it: "IT & Security", legal: "Legal & Compliance", hiring: "People & Hiring", store: "Online store", pr: "PR & Comms",
  revops: "Revenue Operations", success: "Customer Success", support: "Customer Support", exec: "Founder's office",
  data: "Data & Analytics", delivery: "Client delivery",
};

function teamName(kind: string, org: OrgInfo | null | undefined) {
  const d = org?.departments.find((x) => x.kind === kind);
  return d?.name || TEAM_NAMES[kind] || kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

/** What we found, as short facts: the scan's bullets, or older scans' paragraph split into sentences. */
function factsOf(f: { points?: string[]; evidence: string }): string[] {
  if (f.points && f.points.length) return f.points;
  const parts = (f.evidence || "").split(/(?<=[.!?])\s+(?=[A-Z0-9"'])/).map((s) => s.trim()).filter(Boolean);
  return parts.length ? parts.slice(0, 5) : [f.evidence];
}

const weeks = (w: number) => (w >= 8 && w % 4 === 0 ? `${w / 4} months` : `${w} week${w === 1 ? "" : "s"}`);

/** "What you're missing out on": how customers find you, and gaps with the goals that fix them. */
export function Opportunities({ profile, org, goals, orgName, onStart, onOpen, canStart, titled = true, preview, only, recheck = true, details = true }: {
  profile: CompanyProfile | null | undefined; org: OrgInfo | null | undefined; goals: Campaign[] | null | undefined; orgName: string;
  onStart: (goals: Campaign[]) => void; onOpen: (goal: Campaign) => void; canStart: boolean;
  titled?: boolean;  // false where the page title already says it (onboarding)
  preview?: number;  // show only this many findings until "Show all"
  only?: (f: Opportunity) => boolean;  // which findings to show (e.g. only the ones not being fixed yet)
  recheck?: boolean;  // offer "Check again" (runs the whole check again)
  details?: boolean;  // also show what was checked and the measurements (off: the findings directly)
}) {
  const found = profile?.opportunities;
  const has = !!found && (found.findings.length > 0 || (found.unlock || []).length > 0 || (found.scorecard || []).length > 0);
  const [made, setMade] = useState<Record<string, string>>({});  // "finding:step" -> goal made just now
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {  // arriving from Home's "Turn on fixes" link
    if (has && window.location.hash === "#missing") document.getElementById("missing")?.scrollIntoView({ behavior: "smooth" });
  }, [has]);
  if (!found || !has) return null;
  const collapsed = !!preview && !expanded;
  // Keep each finding's position in the saved list: going further on a milestone refers to it.
  const isNew = (f: Opportunity) => (found.rounds || 1) > 1 && !!f.found_at && f.found_at === found.scanned_at;
  const listed = found.findings.map((f, i) => ({ f, i })).filter((x) => !only || only(x.f))
    .sort((a, b) => Number(isNew(b.f)) - Number(isNew(a.f)));  // the latest finds first
  const shownFindings = collapsed ? listed.slice(0, preview) : listed;
  const hiddenCount = listed.length - shownFindings.length;
  const extras = [
    details && found.visibility && (found.visibility.search.length > 0 || found.visibility.ai.length > 0) ? "how customers find you" : "",
    details && (found.scorecard || []).length > 0 ? "you vs competitors" : "",
    (found.unlock || []).length > 0 ? "what connecting your tools unlocks" : "",
  ].filter(Boolean);
  const byId = new Map((goals || []).map((g) => [g.id, g]));
  const goalFor = (fi: number, si: number) => byId.get(found.findings[fi].milestones?.[si]?.goal_id || made[`${fi}:${si}`] || "");
  const firstSteps = found.findings.map((f) => (f.goal_id ? byId.get(f.goal_id) : undefined))
    .filter((g): g is Campaign => !!g && g.status === "draft" && g.can_manage !== false);
  const unique = [...new Map(firstSteps.map((g) => [g.id, g])).values()];

  async function checkAgain() {
    setBusy("recheck");
    setErr(null);
    try {
      await api("/api/org/setup", { method: "POST", json: {} });
      window.location.href = "/setup";  // shows the check's progress, then the new results
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  }

  async function goFurther(fi: number, si: number) {
    const key = `${fi}:${si}`;
    setBusy(key);
    setErr(null);
    try {
      const { goal_id } = await api<{ goal_id: string }>(`/api/org/opportunities/${fi}/milestones/${si}/goal`, { method: "POST" });
      setMade((m) => ({ ...m, [key]: goal_id }));
      onStart([await api<Campaign>(`/api/campaigns/${goal_id}`)]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section id="missing" className="scroll-mt-6 space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        {titled ? (
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> What you&apos;re missing out on</h2>
            <p className="text-sm text-muted">What we found about {orgName}, with evidence. Each gap has a goal ready to turn on, and big ones come in steps with their price.</p>
          </div>
        ) : <div />}
        <div className="flex flex-wrap items-center gap-2">
        {canStart && recheck && (
          <button onClick={checkAgain} disabled={busy === "recheck"} title="Run the company check again with the latest checks (your goals stay)"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-stone-700 hover:bg-stone-50 disabled:opacity-60">
            {busy === "recheck" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Check again
          </button>
        )}
        {canStart && unique.length > 1 && (
          <button onClick={() => onStart(unique)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            Start {unique.length} first steps <ArrowRight size={15} />
          </button>
        )}
        </div>
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      {details && !collapsed && (found.checks || []).some((c) => c.why) && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
          <span className="text-muted">What we checked, and why:</span>
          {found.checks!.map((c) => (
            <span key={c.key} title={c.why ? `${c.why}${c.expect ? ` · Expected: ${c.expect}` : ""}` : undefined}
              className="cursor-help rounded-full border border-line bg-white px-2.5 py-0.5 font-medium text-stone-700">{c.title}</span>
          ))}
        </div>
      )}

      {details && !collapsed && found.visibility && (found.visibility.search.length > 0 || found.visibility.ai.length > 0) && <Findable v={found.visibility} name={orgName} />}
      {details && !collapsed && (found.scorecard || []).length > 0 && <Scorecard rows={found.scorecard!} name={orgName} social={found.social} canEdit={canStart} />}

      <div className="space-y-4">
        {shownFindings.map(({ f, i }) => {
          const steps = f.milestones || [];
          const goal = f.goal_id ? byId.get(f.goal_id) : undefined;
          const facts = factsOf(f);
          return (
            <article key={i} className="overflow-hidden rounded-3xl border border-line bg-white shadow-[var(--shadow-card)]">
              <div className="grid lg:grid-cols-[minmax(0,1fr)_360px]">
                {/* The problem, and the proof */}
                <div className="min-w-0 p-6 md:p-7">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-1 text-[12px] font-semibold text-red-700 ring-1 ring-inset ring-red-100">
                      <AlertTriangle size={12} /> Gap
                    </span>
                    <Pull n={f.pull} />
                    <span className="text-[12px] font-medium text-stone-400">{CONFIDENCE[f.confidence]}</span>
                    {isNew(f) && <span className="rounded-full bg-lime-200 px-2 py-0.5 text-[12px] font-bold text-lime-900">New</span>}
                  </div>
                  <h3 className="display mt-3 max-w-[40ch] text-[24px] leading-[1.15] text-red-700">{f.title}</h3>
                  {f.impact && <p className="mt-3 max-w-[62ch] text-[15px] leading-relaxed text-stone-700">{f.impact}</p>}

                  <div className="mt-6 text-[12px] font-bold text-muted">What we found</div>
                  <ul className="mt-2.5 divide-y divide-dashed divide-line">
                    {facts.map((x, k) => (
                      <li key={k} className="flex gap-3 py-2 text-[14px] leading-relaxed text-stone-800">
                        <span aria-hidden className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />
                        <span>{x}</span>
                      </li>
                    ))}
                  </ul>
                  {f.check === "social_performance" && <ProfilesUsed used={f.profiles || found.social} orgName={orgName} canEdit={canStart} />}
                </div>

                {/* The prize: what fixing it gets you, and the one move to start */}
                <Prize f={f} goal={steps.length > 1 ? goalFor(i, 0) ?? goal : goal} steps={steps} canStart={canStart}
                  onStart={(g) => onStart([g])} onOpen={onOpen} />
              </div>

              {steps.length > 1 ? (
                <Steps steps={steps} total={f.total_usd || 0} goalFor={(si) => goalFor(i, si)}
                  canStart={canStart} busy={busy?.startsWith(`${i}:`) ? Number(busy.split(":")[1]) : null}
                  onStart={(g) => onStart([g])} onOpen={onOpen} onFurther={(si) => goFurther(i, si)} />
              ) : !goal ? (
                <div className="flex items-center justify-between gap-2 border-t border-line px-6 py-3 text-[13px]">
                  <span className="text-muted">No goal for this yet</span>
                  <Link href="/goals/new" className="font-semibold text-brand-700 hover:underline">Set one up</Link>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {!collapsed && (found.unlock || []).length > 0 && (
        <Unlock groups={found.unlock!} org={org} goals={goals || []} canStart={canStart} onStart={onStart} onOpen={onOpen} />
      )}

      {preview && (hiddenCount > 0 || extras.length > 0) && (
        <button onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 bg-white/70 px-4 py-3 text-[13.5px] font-semibold text-brand-700 transition hover:border-stone-400 hover:bg-white">
          {expanded ? <>Show less <ChevronUp size={15} /></> : (
            <>
              Show all{hiddenCount > 0 ? " findings" : ""}
              {extras.length > 0 && <span className="font-normal text-muted">{hiddenCount > 0 ? ", plus " : ": "}{extras.join(", ")}</span>}
              <ChevronDown size={15} />
            </>
          )}
        </button>
      )}
    </section>
  );
}

/** Connect your tools: per team, the tools that let Oton look at your own data and suggest more goals. */
function Unlock({ groups, org }: {
  groups: NonNullable<NonNullable<CompanyProfile["opportunities"]>["unlock"]>; org: OrgInfo | null | undefined;
  goals?: Campaign[]; canStart?: boolean; onStart?: (g: Campaign[]) => void; onOpen?: (g: Campaign) => void;
}) {
  const { data: conn, reload } = useApi<{ composio_enabled: boolean; apps: { app: string; status?: string }[] }>("/api/connections", { live: false });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const connected = new Set((conn?.apps || []).filter((a) => (a.status || "").toUpperCase() === "ACTIVE").map((a) => a.app.toLowerCase()));
  useEffect(() => {  // back from the tool's sign-in tab
    const f = () => reload();
    window.addEventListener("focus", f);
    return () => window.removeEventListener("focus", f);
  }, [reload]);

  async function connect(tool: string, checkKey: string) {
    setBusy(tool);
    setErr(null);
    try {
      // The check becomes a suggested goal for that team (nothing runs until someone turns it on),
      // then the tool's own sign-in opens in a new tab.
      await api(`/api/org/unlock/${checkKey}`, { method: "POST" }).catch(() => null);
      const r = await api<{ redirect_url: string }>(`/api/connections/${tool}/connect?back=${encodeURIComponent(window.location.pathname)}`, { method: "POST" });
      window.open(r.redirect_url, "_blank", "noopener");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const row = useRef<HTMLDivElement>(null);
  const scroll = (dir: number) => row.current?.scrollBy({ left: dir * 300, behavior: "smooth" });
  const teams = groups.map((g) => ({
    kind: g.team_kind,
    tools: [...new Map(g.checks.map((c) => [c.tool, { tool: c.tool, label: c.label, key: c.key }])).values()],
  })).filter((t) => t.tools.length > 0);
  return (
    <div className="overflow-hidden rounded-2xl border border-brand-200 bg-brand-50/60 p-5 md:p-6">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-600 text-white"><Plug size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[17px] font-bold leading-snug">Want more areas of improvement?</div>
          <p className="mt-0.5 text-[14px] text-stone-700">Connect your tools so we can analyze more information and suggest goals.</p>
        </div>
        {teams.length > 1 && (
          <div className="hidden shrink-0 gap-1 sm:flex">
            <button onClick={() => scroll(-1)} aria-label="Previous teams" className="grid h-9 w-9 place-items-center rounded-full border border-line bg-white text-stone-500 hover:text-ink"><ChevronLeft size={16} /></button>
            <button onClick={() => scroll(1)} aria-label="More teams" className="grid h-9 w-9 place-items-center rounded-full border border-line bg-white text-stone-500 hover:text-ink"><ChevronRight size={16} /></button>
          </div>
        )}
      </div>
      {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
      <div ref={row} className="-mx-5 mt-5 flex snap-x snap-mandatory scroll-px-5 gap-3 overflow-x-auto px-5 pb-1 [scrollbar-width:thin] md:-mx-6 md:scroll-px-6 md:px-6">
        {teams.map((t) => (
          <div key={t.kind} className="w-[280px] shrink-0 snap-start rounded-xl bg-white p-4 ring-1 ring-inset ring-line">
            <TeamTag name={teamName(t.kind, org)} />
            <div className="mt-3 flex flex-wrap gap-2">
              {t.tools.map((x) => connected.has(x.tool.toLowerCase()) ? (
                <span key={x.tool} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-50 px-3 text-[13px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200">
                  <Check size={14} /> {x.label} connected
                </span>
              ) : (
                <button key={x.tool} onClick={() => connect(x.tool, x.key)} disabled={busy === x.tool}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-[13px] font-semibold text-ink transition hover:border-brand-300 hover:bg-brand-50 disabled:opacity-60">
                  {busy === x.tool ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} className="text-brand-600" />} Connect {x.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TurnOn({ goal, canStart, onStart }: { goal: Campaign; canStart: boolean; onStart: () => void }) {
  if (goal.status !== "draft") return <span className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-emerald-700"><Check size={14} /> Live</span>;
  if (!canStart || goal.can_manage === false) return null;
  return (
    <button onClick={onStart} className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[12.5px] font-semibold text-white hover:bg-brand-700">
      Turn on <ArrowRight size={13} />
    </button>
  );
}

/** "Email records set" -> "email records set", so "3 of 3 email records set" reads as a sentence (keeps acronyms). */
const lower = (x: string) => (/^[A-Z][A-Z]/.test(x) ? x : x.charAt(0).toLowerCase() + x.slice(1));

/** How much they'll want to fix it (the check's 1-5 "pull"), as an impact meter. */
function Pull({ n }: { n?: number }) {
  if (!n) return null;
  const label = n >= 4 ? "High impact" : n === 3 ? "Medium impact" : "Worth fixing";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-canvas px-2.5 py-1 text-[12px] font-semibold text-stone-700 ring-1 ring-inset ring-line">
      <span className="flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3, 4, 5].map((k) => <span key={k} className={cx("w-[3px] rounded-sm", k <= n ? "bg-brand-600" : "bg-stone-200")} style={{ height: 4 + k * 1.5 }} />)}
      </span>
      {label}
    </span>
  );
}

/** The right side of a finding: the goal that fixes it, what it gets you, and the one move to start. */
function Prize({ f, goal, steps, canStart, onStart, onOpen }: {
  f: Opportunity; goal: Campaign | undefined; steps: Milestone[]; canStart: boolean; onStart: (g: Campaign) => void; onOpen: (g: Campaign) => void;
}) {
  const multi = steps.length > 1;
  const price = steps[0]?.total_usd ?? goal?.budget?.total;
  const total = f.total_usd || steps.reduce((t, m) => t + m.total_usd, 0);
  const span = steps.reduce((t, m) => t + m.weeks, 0);
  return (
    <aside className="relative flex min-w-0 flex-col overflow-hidden bg-ink p-6 text-white md:p-7">
      <div aria-hidden className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-lime-300/20 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-emerald-500/20 blur-3xl" />
      <div className="relative text-[12px] font-bold text-lime-300">{multi ? "The goal for step 1" : "The goal that fixes it"}</div>

      {goal ? (
        <button onClick={() => onOpen(goal)}
          className="group relative mt-3 flex w-full items-start gap-3 rounded-2xl bg-white/[0.07] p-4 text-left ring-1 ring-inset ring-white/15 transition hover:bg-white/[0.1]">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-lime-300 text-ink"><Target size={17} /></span>
          <span className="min-w-0">
            <span className="block text-[16px] font-semibold leading-snug text-white">{goal.name}</span>
            <span className="mt-1 inline-flex items-center gap-0.5 text-[12px] text-white/50 transition group-hover:text-white/80">See the plan <ChevronRight size={12} /></span>
          </span>
        </button>
      ) : <p className="relative mt-3 text-[14px] text-white/60">No goal for this yet.</p>}

      {f.metric_goal && (
        <div className="relative mt-5">
          <div className="text-[12px] font-semibold text-white/50">After the fix</div>
          <div className="mt-0.5 leading-snug">
            <span className="text-[22px] font-bold text-lime-300">{f.metric_goal}</span>
            {f.metric_name && <span className="text-[13.5px] text-white/70"> {lower(f.metric_name)}</span>}
          </div>
        </div>
      )}

      {f.estimate && (
        <div className="relative mt-4 rounded-xl bg-lime-300/10 px-3.5 py-2.5 ring-1 ring-inset ring-lime-300/25">
          <div className="text-[14px] font-semibold leading-snug text-lime-100">{f.estimate}</div>
          {f.assumption && <div className="mt-0.5 text-[12px] leading-snug text-white/45">{f.assumption}</div>}
        </div>
      )}

      <div className="relative mt-auto pt-6">
        {goal && goal.status !== "draft" ? (
          <button onClick={() => onOpen(goal)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-lime-300/15 py-3 text-[14px] font-semibold text-lime-200 ring-1 ring-inset ring-lime-300/30 transition hover:bg-lime-300/20">
            <span className="signal-dot" /> AI is working on this goal
          </button>
        ) : goal && canStart && goal.can_manage !== false ? (
          <>
            <button onClick={() => onStart(goal)} className="group flex w-full items-center justify-center gap-2 rounded-xl bg-lime-300 px-3 py-3 text-[14.5px] font-bold text-ink shadow-[0_8px_24px_-8px_rgba(190,242,100,0.6)] transition hover:bg-lime-200">
              {multi ? "Set up AI to work on step 1" : "Set up AI to work on this goal"}
              <ArrowRight size={16} className="shrink-0 transition group-hover:translate-x-0.5" />
            </button>
            {price ? (
              <div className="mt-3 text-center">
                <p className="flex items-center justify-center gap-1.5 text-[14px] text-white/80">
                  <ShieldCheck size={15} className="shrink-0 text-lime-300" />
                  <span><b className="tabular text-[15px] font-bold text-white">{usd(price)}</b> budget, a hard limit</span>
                </p>
                <p className="mt-0.5 text-[13px] text-white/60">Nothing runs until you say so.</p>
              </div>
            ) : null}
          </>
        ) : null}
        {multi && <p className="mt-3 text-center text-[13px] text-white/60">The full fix: <b className="tabular font-semibold text-white/85">{usd(total)}</b> over {weeks(span)}. Go further only if it works.</p>}
      </div>
    </aside>
  );
}

/** A big fix in steps, as a roadmap: what each gets you, how long, and what it costs. Step 1 starts from the card above. */
function Steps({ steps, total, goalFor, canStart, busy, onStart, onOpen, onFurther }: {
  steps: Milestone[]; total: number; goalFor: (i: number) => Campaign | undefined; canStart: boolean; busy: number | null;
  onStart: (g: Campaign) => void; onOpen: (g: Campaign) => void; onFurther: (i: number) => void;
}) {
  const allWeeks = steps.reduce((t, m) => t + m.weeks, 0);
  return (
    <div className="border-t border-line bg-canvas/70 px-6 py-5 md:px-7">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[12px] font-bold text-muted">The path to fixing it</span>
        <span className="tabular text-[12.5px] text-muted">{usd(total)} over {weeks(allWeeks)} in all</span>
      </div>
      <ol className="grid gap-3 lg:auto-cols-fr lg:grid-flow-col">
        {steps.map((m, i) => {
          const goal = goalFor(i);
          const last = i === steps.length - 1;
          const live = goal && goal.status !== "draft";
          return (
            <li key={i} className={cx("relative flex flex-col rounded-2xl bg-white p-4 shadow-[var(--shadow-card)] ring-1 ring-inset",
              i === 0 ? "ring-2 ring-brand-500/40" : "ring-line")}>
              {!last && (
                <span aria-hidden className="absolute -right-[14px] top-1/2 z-10 hidden h-6 w-6 -translate-y-1/2 place-items-center rounded-full bg-white text-stone-400 shadow-sm ring-1 ring-line lg:grid">
                  <ChevronRight size={14} />
                </span>
              )}
              <div className="flex items-center gap-2 text-[12px] font-bold">
                <span className={cx("grid h-5 w-5 place-items-center rounded-full text-[12px]", live ? "bg-emerald-500 text-white" : i === 0 ? "bg-brand-600 text-white" : "bg-stone-100 text-stone-500")}>
                  {live ? <Check size={11} strokeWidth={3} /> : last ? <Flag size={10} /> : i + 1}
                </span>
                <span className={i === 0 ? "text-brand-700" : "text-muted"}>{i === 0 ? "Start here" : last ? "Full result" : `Step ${i + 1}`}</span>
                <span className="font-semibold normal-case tracking-normal text-stone-400">· {weeks(m.weeks)}</span>
              </div>
              <div className="mt-2 text-[14.5px] font-semibold leading-snug">{m.name}</div>
              {m.outcome && <div className="mt-0.5 text-[12.5px] leading-snug text-muted">{m.outcome}</div>}
              {(m.does || []).length > 0 && (
                <ul className="mt-2.5 space-y-1 text-[12px] text-stone-700">
                  {m.does!.slice(0, 3).map((d) => <li key={d} className="flex gap-1.5"><Check size={12} className="mt-[2px] shrink-0 text-brand-600" /><span className="line-clamp-1">{d}</span></li>)}
                </ul>
              )}
              <div className="mt-auto flex items-end justify-between gap-2 pt-4">
                <div className="min-w-0">
                  <div className="tabular text-[17px] font-bold leading-none text-ink">{usd(m.total_usd)}</div>
                  <div className="mt-1 truncate text-[12px] text-muted" title={m.paid_items.map((p) => `${p.item}: ${usd(p.usd)}`).join(", ")}>
                    AI work {usd(m.ai_usd)}{m.paid_usd ? ` + ${usd(m.paid_usd)} spend` : ""}
                  </div>
                </div>
                {goal ? (
                  i === 0 && !live ? (
                    <button onClick={() => onOpen(goal)} className="shrink-0 text-[12px] font-semibold text-muted hover:text-ink">See plan</button>
                  ) : (
                    <span className="flex shrink-0 items-center gap-2">
                      <button onClick={() => onOpen(goal)} className="text-[12px] text-muted hover:text-ink">See goal</button>
                      <TurnOn goal={goal} canStart={canStart} onStart={() => onStart(goal)} />
                    </span>
                  )
                ) : canStart ? (
                  <button onClick={() => onFurther(i)} disabled={busy === i}
                    className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-line bg-white px-3 text-[12.5px] font-semibold hover:border-stone-300 disabled:opacity-60">
                    {busy === i ? <Loader2 size={13} className="animate-spin" /> : null} Go further <ArrowRight size={13} />
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Where they show up when customers search on Google (by country) or ask AI assistants. */
function Findable({ v, name }: { v: Visibility; name: string }) {
  const queries = [...new Set([...v.search.map((s) => s.query), ...v.ai.map((a) => a.query)])];
  const markets = v.source === "google" ? (v.markets || [...new Set(v.search.map((s) => s.market || ""))]) : ["Web"];
  const assistants = [...new Set(v.ai.map((a) => a.assistant || "AI assistant"))];
  const seen = v.search.filter((s) => s.rank).length;
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-line px-5 py-3.5">
        <div>
          <div className="text-[15px] font-semibold">How customers find you</div>
          <div className="text-[12.5px] text-muted">
            {v.source === "google" ? `Real Google results in ${markets.join(", ")}` : "Web search results"}, for what people looking for what you sell type in, without your name.
          </div>
        </div>
        {v.search.length > 0 && (
          <span className={cx("rounded-full px-2.5 py-1 text-[12px] font-semibold", seen === 0 ? "bg-red-50 text-red-700" : seen < v.search.length ? "bg-signal-50 text-signal-800" : "bg-emerald-50 text-emerald-700")}>
            {name} shows up in {seen} of {v.search.length} searches
          </span>
        )}
      </div>
      {(v.highlights || []).length > 0 && (
        <ul className="space-y-1.5 border-b border-line bg-brand-50/50 px-5 py-3">
          {v.highlights!.map((h) => <li key={h} className="flex gap-2 text-[13px] font-medium text-brand-900"><TrendingUp size={14} className="mt-0.5 shrink-0 text-brand-600" />{h}</li>)}
        </ul>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-line bg-canvas text-[12px] font-semibold text-muted">
              <th className="px-5 py-2 font-semibold">Search</th>
              {markets.map((m) => <th key={m} className="px-3 py-2 font-semibold"><span className="inline-flex items-center gap-1"><Search size={11} />{v.source === "google" ? `Google ${m}` : "Web search"}</span></th>)}
              {assistants.length > 0 && <th className="px-3 py-2 font-semibold"><span className="inline-flex items-center gap-1"><Bot size={11} /> AI assistants</span></th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {queries.map((q) => {
              const intent = v.search.find((x) => x.query === q)?.intent;
              return (
                <tr key={q} className="align-top">
                  <td className="px-5 py-3">
                    <div className="text-[13.5px] font-semibold">&ldquo;{q}&rdquo;</div>
                    {intent && <div className="text-[12px] text-muted">{intent}</div>}
                  </td>
                  {markets.map((m) => {
                    const s = v.search.find((x) => x.query === q && (v.source !== "google" || x.market === m));
                    return (
                      <td key={m} className="px-3 py-3 text-[12.5px]">
                        {s ? (
                          <div className="space-y-1">
                            <Rank rank={s.rank} miss={`Not in top ${s.checked}`} />
                            {(s.volume != null || s.difficulty != null) && (
                              <div className="text-muted">
                                {s.volume != null && <span className="tabular">{s.volume.toLocaleString()}/mo</span>}
                                {s.volume != null && s.difficulty != null && " · "}
                                {s.difficulty != null && <span>difficulty {s.difficulty}</span>}
                              </div>
                            )}
                            {s.competitors_ahead.length > 0 && <div className="text-muted">Ahead: {s.competitors_ahead.join(", ")}</div>}
                            {s.ai_overview && (
                              <div className={cx("text-[12px] font-medium", s.ai_overview.mentioned ? "text-emerald-700" : "text-red-700")}>
                                AI Overview {s.ai_overview.mentioned ? "cites you" : s.ai_overview.competitors.length ? `cites ${s.ai_overview.competitors.join(", ")}` : "doesn't cite you"}
                              </div>
                            )}
                          </div>
                        ) : <span className="text-muted">-</span>}
                      </td>
                    );
                  })}
                  {assistants.length > 0 && (
                    <td className="px-3 py-3 text-[12.5px]">
                      <ul className="space-y-1">
                        {assistants.map((who) => {
                          const a = v.ai.find((x) => x.query === q && (x.assistant || "AI assistant") === who);
                          if (!a) return null;
                          const others = a.recommended.filter((r) => !r.you).slice(0, 2).map((r) => r.name).join(", ");
                          return (
                            <li key={who} className="flex flex-wrap items-center gap-1.5">
                              <span className="w-[74px] shrink-0 font-medium text-stone-700">{who}</span>
                              <Rank rank={a.rank} miss="Not named" prefix="" />
                              {!a.rank && others && <span className="truncate text-muted">{others}</span>}
                            </li>
                          );
                        })}
                      </ul>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {(v.local || []).length > 0 && (
        <div className="border-t border-line px-5 py-3">
          <div className="mb-2 text-[12px] font-semibold text-muted">Google Maps results</div>
          <ul className="grid gap-2 sm:grid-cols-3">
            {v.local!.map((l) => (
              <li key={l.city} className="rounded-xl bg-canvas p-3 text-[12.5px]">
                <div className="font-semibold">{l.city}</div>
                <div className="mt-1"><Rank rank={l.rank} miss="Not in the map results" /></div>
                {l.results[0] && !l.results[0].you && (
                  <div className="mt-1 truncate text-muted">#1 {l.results[0].title}{l.results[0].rating ? ` · ${l.results[0].rating}★ (${l.results[0].reviews ?? 0})` : ""}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The website, domain and presence, measured next to competitors. */
function Scorecard({ rows, name, social, canEdit }: { rows: ScoreRow[]; name: string; social?: SocialUsed; canEdit: boolean }) {
  const names = [...new Set(rows.flatMap((r) => r.others.map((o) => o.name)))].slice(0, 3);
  const bad = rows.filter((r) => r.you.status === "bad").length;
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-line px-5 py-3.5">
        <div>
          <div className="text-[15px] font-semibold">Your website and presence, measured</div>
          <div className="text-[12.5px] text-muted">Checked live, next to {names.length ? names.join(", ") : "your competitors"}.</div>
        </div>
        <span className={cx("rounded-full px-2.5 py-1 text-[12px] font-semibold", bad ? "bg-signal-50 text-signal-800" : "bg-emerald-50 text-emerald-700")}>
          {bad ? `${bad} to fix` : "All good"}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[12.5px]">
          <thead>
            <tr className="border-b border-line bg-canvas text-[12px] font-semibold text-muted">
              <th className="px-5 py-2 font-semibold">Check</th>
              <th className="px-3 py-2 font-semibold">{name}</th>
              {names.map((n) => <th key={n} className="px-3 py-2 font-semibold">{n}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.key} className="align-top">
                <td className="px-5 py-2.5">
                  <div className="font-semibold text-ink">{r.label}</div>
                  {r.note && <div className="text-[12px] text-muted">{r.note}</div>}
                </td>
                <td className="px-3 py-2.5">
                  <span className={cx("inline-flex items-start gap-1.5 font-medium", r.you.status === "bad" ? "text-red-700" : r.you.status === "good" ? "text-emerald-700" : "text-ink")}>
                    <span className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", r.you.status === "bad" ? "bg-red-500" : r.you.status === "good" ? "bg-emerald-500" : "bg-stone-300")} />
                    {r.you.display}
                  </span>
                  {r.you.url && (
                    <a href={r.you.url} target="_blank" rel="noreferrer" className="mt-0.5 block truncate pl-3 text-[11.5px] text-muted underline decoration-stone-300 underline-offset-2 hover:text-ink">
                      {profileLabel(r.key === "social_x" ? "x" : "linkedin", r.you.url)}
                    </a>
                  )}
                </td>
                {names.map((n) => <td key={n} className="px-3 py-2.5 text-stone-600">{r.others.find((o) => o.name === n)?.display ?? <span className="text-stone-300">-</span>}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((r) => r.key.startsWith("social_")) && (
        <div className="border-t border-line px-5 pb-4"><ProfilesUsed used={social} orgName={name} canEdit={canEdit} /></div>
      )}
    </div>
  );
}

function Rank({ rank, miss, prefix = "Rank" }: { rank: number | null; miss: string; prefix?: string }) {
  if (!rank) return <span className="inline-flex rounded-md bg-red-50 px-2 py-0.5 font-semibold text-red-700">{miss}</span>;
  return (
    <span className={cx("inline-flex rounded-md px-2 py-0.5 font-semibold", rank <= 3 ? "bg-emerald-50 text-emerald-700" : "bg-signal-50 text-signal-800")}>
      {prefix ? `${prefix} ` : ""}#{rank}
    </span>
  );
}

/** On Home: the gaps whose first step isn't on yet. */
export function MissingSummary({ profile, goals }: { profile: CompanyProfile | null | undefined; goals: Campaign[] }) {
  const found = profile?.opportunities?.findings || [];
  const byId = new Map(goals.map((g) => [g.id, g]));
  const open = found.filter((f) => f.goal_id && byId.get(f.goal_id)?.status === "draft");
  if (!open.length) return null;
  return (
    <Link href="/goals?tab=ideas#missing" className="group flex items-start gap-4 rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition hover:border-stone-300">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100"><Search size={17} /></span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14.5px] font-semibold">{open.length} thing{open.length === 1 ? "" : "s"} you&apos;re missing out on</span>
        <span className="mt-0.5 block truncate text-[13px] text-muted">{andMore(open.map((f) => f.title))}</span>
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 self-center text-[13px] font-semibold text-brand-700">Turn on fixes <ArrowRight size={14} className="transition group-hover:translate-x-0.5" /></span>
    </Link>
  );
}
