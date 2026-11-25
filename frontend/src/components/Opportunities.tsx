"use client";

import { ArrowRight, Bot, Check, ExternalLink, Flag, Loader2, Plug, Search, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, Campaign, CompanyProfile, Milestone, OrgInfo, Opportunity, usd, Visibility } from "@/lib/api";
import { TeamTag } from "./team";
import { cx, ErrorNote } from "./ui";

const CONFIDENCE: Record<Opportunity["confidence"], string> = { high: "Clear signal", medium: "Likely", low: "Worth a look" };

function teamName(kind: string, org: OrgInfo | null | undefined) {
  const d = org?.departments.find((x) => x.kind === kind);
  return d?.name || kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

function host(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

const weeks = (w: number) => (w >= 8 && w % 4 === 0 ? `${w / 4} months` : `${w} week${w === 1 ? "" : "s"}`);

/** "What you're missing out on": how customers find you, and gaps with the goals that fix them. */
export function Opportunities({ profile, org, goals, orgName, onStart, onOpen, canStart }: {
  profile: CompanyProfile | null | undefined; org: OrgInfo | null | undefined; goals: Campaign[] | null | undefined; orgName: string;
  onStart: (goals: Campaign[]) => void; onOpen: (goal: Campaign) => void; canStart: boolean;
}) {
  const found = profile?.opportunities;
  const has = !!found && (found.findings.length > 0 || found.deeper.length > 0);
  const [made, setMade] = useState<Record<string, string>>({});  // "finding:step" -> goal made just now
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {  // arriving from Home's "Turn on fixes" link
    if (has && window.location.hash === "#missing") document.getElementById("missing")?.scrollIntoView({ behavior: "smooth" });
  }, [has]);
  if (!found || !has) return null;
  const byId = new Map((goals || []).map((g) => [g.id, g]));
  const firstSteps = found.findings.map((f) => (f.goal_id ? byId.get(f.goal_id) : undefined))
    .filter((g): g is Campaign => !!g && g.status === "draft" && g.can_manage !== false);
  const unique = [...new Map(firstSteps.map((g) => [g.id, g])).values()];

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
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> What you&apos;re missing out on</h2>
          <p className="text-sm text-muted">What we found about {orgName}, with evidence. Each gap has a goal ready to turn on, and big ones come in steps with their price.</p>
        </div>
        {canStart && unique.length > 1 && (
          <button onClick={() => onStart(unique)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            Start {unique.length} first steps <ArrowRight size={15} />
          </button>
        )}
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}

      {found.visibility && (found.visibility.search.length > 0 || found.visibility.ai.length > 0) && <Findable v={found.visibility} name={orgName} />}

      <div className="grid gap-3 md:grid-cols-2">
        {found.findings.map((f, i) => {
          const steps = f.milestones || [];
          const goal = f.goal_id ? byId.get(f.goal_id) : undefined;
          return (
            <article key={i} className={cx("flex flex-col rounded-2xl border border-line bg-white p-5 shadow-[var(--shadow-card)]", steps.length > 1 && "md:col-span-2")}>
              <div className="flex items-center gap-2">
                <TeamTag name={teamName(f.team_kind, org)} />
                <span className="text-[11.5px] font-medium text-muted">{CONFIDENCE[f.confidence]}</span>
              </div>
              <h3 className="mt-3 text-[16px] font-semibold leading-snug tracking-[-0.01em]">{f.title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-stone-700">{f.evidence}</p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{f.impact}</p>
              {f.estimate && (
                <div className="mt-3 rounded-xl bg-brand-50 px-3 py-2 ring-1 ring-inset ring-brand-100">
                  <div className="flex items-center gap-1.5 text-[13.5px] font-semibold text-brand-700"><TrendingUp size={14} /> {f.estimate}</div>
                  {f.assumption && <div className="mt-0.5 text-[12px] text-brand-700/80">Estimate: {f.assumption}</div>}
                </div>
              )}
              {f.sources.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
                  {f.sources.map((u) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-muted hover:text-ink">
                      <ExternalLink size={11} />{host(u)}
                    </a>
                  ))}
                </div>
              )}
              <div className="mt-auto pt-4">
                {steps.length > 1 ? (
                  <Steps steps={steps} total={f.total_usd || 0} goalFor={(si) => byId.get(steps[si].goal_id || made[`${i}:${si}`] || "")}
                    canStart={canStart} busy={busy?.startsWith(`${i}:`) ? Number(busy.split(":")[1]) : null}
                    onStart={(g) => onStart([g])} onOpen={onOpen} onFurther={(si) => goFurther(i, si)} />
                ) : goal ? (
                  <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                    <button onClick={() => onOpen(goal)} className="min-w-0 flex-1 truncate text-left text-[13px] text-muted hover:text-ink">
                      Goal: <span className="font-semibold text-ink">{goal.name}</span>
                      {steps[0] && <span className="tabular"> · {usd(steps[0].total_usd)}</span>}
                    </button>
                    <TurnOn goal={goal} canStart={canStart} onStart={() => onStart([goal])} />
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-2 border-t border-line pt-3 text-[13px]">
                    <span className="text-muted">Needs a {teamName(f.team_kind, org)} team</span>
                    <Link href="/team" className="font-semibold text-brand-700 hover:underline">Add it</Link>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {found.deeper.length > 0 && (
        <div className="rounded-2xl border border-dashed border-stone-300 bg-white/60 p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold"><Plug size={15} className="text-brand-600" /> Connect for a deeper check</div>
          <p className="text-[12.5px] text-muted">With your own data, your AI employees can measure these for real.</p>
          <ul className="mt-2.5 flex flex-wrap gap-2">
            {found.deeper.map((d) => (
              <li key={d.check}>
                <Link href="/connections" title={d.why} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-[12.5px] hover:border-stone-300">
                  <b className="font-semibold">{d.label}</b><span className="text-muted">{d.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
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

/** A big fix in steps: what each gets you, how long, and what it costs. Start small, go further later. */
function Steps({ steps, total, goalFor, canStart, busy, onStart, onOpen, onFurther }: {
  steps: Milestone[]; total: number; goalFor: (i: number) => Campaign | undefined; canStart: boolean; busy: number | null;
  onStart: (g: Campaign) => void; onOpen: (g: Campaign) => void; onFurther: (i: number) => void;
}) {
  const allWeeks = steps.reduce((t, m) => t + m.weeks, 0);
  return (
    <div className="border-t border-line pt-3">
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
        <span><b className="font-semibold">Fixing it fully:</b> <span className="tabular">{usd(total)}</span> over {weeks(allWeeks)}</span>
        <span className="text-muted">Start with step 1 for <b className="tabular font-semibold text-ink">{usd(steps[0].total_usd)}</b>. Go further only if it works.</span>
      </div>
      <ol className="grid gap-2 lg:grid-cols-3">
        {steps.map((m, i) => {
          const goal = goalFor(i);
          return (
            <li key={i} className={cx("flex flex-col rounded-xl p-3.5 ring-1 ring-inset", i === 0 ? "bg-brand-50/60 ring-brand-100" : "bg-canvas ring-line")}>
              <div className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-[0.05em] text-muted">
                {i === steps.length - 1 ? <Flag size={12} /> : <span className="grid h-4 w-4 place-items-center rounded-full bg-white text-[10px] ring-1 ring-line">{i + 1}</span>}
                {i === 0 ? "Start here" : i === steps.length - 1 ? "Full result" : `Step ${i + 1}`} · {weeks(m.weeks)}
              </div>
              <div className="mt-1.5 text-[14px] font-semibold leading-snug">{m.name}</div>
              {m.outcome && <div className="mt-0.5 text-[12.5px] leading-snug text-muted">{m.outcome}</div>}
              <div className="mt-2 text-[12px] text-stone-600">
                <span className="tabular text-[15px] font-semibold text-ink">{usd(m.total_usd)}</span>
                <span className="text-muted"> · AI work {usd(m.ai_usd)}{m.paid_usd ? ` + ${usd(m.paid_usd)} spend` : ""}</span>
                {m.paid_items.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-[11.5px] text-muted">{m.paid_items.map((p) => <li key={p.item}>· {p.item}: {usd(p.usd)}</li>)}</ul>
                )}
              </div>
              <div className="mt-auto flex items-center justify-between gap-2 pt-3">
                {goal ? (
                  <>
                    <button onClick={() => onOpen(goal)} className="text-[12px] text-muted hover:text-ink">See goal</button>
                    <TurnOn goal={goal} canStart={canStart} onStart={() => onStart(goal)} />
                  </>
                ) : canStart ? (
                  <button onClick={() => onFurther(i)} disabled={busy === i}
                    className="ml-auto inline-flex h-8 items-center gap-1 rounded-lg border border-line bg-white px-3 text-[12.5px] font-semibold hover:border-stone-300 disabled:opacity-60">
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

/** Where they show up when customers search or ask an AI assistant, next to competitors. */
function Findable({ v, name }: { v: Visibility; name: string }) {
  const rows = [...new Set([...v.search.map((s) => s.query), ...v.ai.map((a) => a.query)])];
  const seen = v.search.filter((s) => s.rank).length + v.ai.filter((a) => a.rank).length;
  const asked = v.search.length + v.ai.length;
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-line px-5 py-3.5">
        <div>
          <div className="text-[15px] font-semibold">How customers find you</div>
          <div className="text-[12.5px] text-muted">What people looking for what you sell type in, without your name. Checked live.</div>
        </div>
        <span className={cx("rounded-full px-2.5 py-1 text-[12px] font-semibold", seen === 0 ? "bg-red-50 text-red-700" : seen < asked ? "bg-signal-50 text-signal-800" : "bg-emerald-50 text-emerald-700")}>
          {name} shows up in {seen} of {asked}
        </span>
      </div>
      <div className="hidden grid-cols-[1.3fr_1fr_1fr] gap-4 border-b border-line bg-canvas px-5 py-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-muted md:grid">
        <div>Search</div><div className="flex items-center gap-1"><Search size={11} /> Web search</div><div className="flex items-center gap-1"><Bot size={11} /> AI assistant</div>
      </div>
      <ul className="divide-y divide-line">
        {rows.map((q) => {
          const s = v.search.find((x) => x.query === q);
          const a = v.ai.find((x) => x.query === q);
          return (
            <li key={q} className="grid gap-2 px-5 py-3 md:grid-cols-[1.3fr_1fr_1fr] md:gap-4">
              <div>
                <div className="text-[13.5px] font-semibold">&ldquo;{q}&rdquo;</div>
                {s?.intent && <div className="text-[12px] text-muted">{s.intent}</div>}
              </div>
              <div className="text-[12.5px]">
                {s ? (
                  <>
                    <Rank rank={s.rank} miss={`Not in the top ${s.checked}`} />
                    {s.competitors_ahead.length > 0 && <div className="mt-1 text-muted">Ahead of you: {s.competitors_ahead.join(", ")}</div>}
                    {!s.rank && !s.competitors_ahead.length && s.results.length > 0 && <div className="mt-1 truncate text-muted">Top: {s.results.slice(0, 3).map((r) => r.who || r.domain).join(", ")}</div>}
                  </>
                ) : <span className="text-muted">Not checked</span>}
              </div>
              <div className="text-[12.5px]">
                {a ? (
                  <>
                    <Rank rank={a.rank} miss="Not recommended" prefix="Recommended" />
                    {a.recommended.length > 0 && (
                      <div className="mt-1 truncate text-muted">Suggests: {a.recommended.filter((r) => !r.you).slice(0, 3).map((r) => r.name).join(", ")}</div>
                    )}
                  </>
                ) : <span className="text-muted">Not checked</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Rank({ rank, miss, prefix = "Rank" }: { rank: number | null; miss: string; prefix?: string }) {
  if (!rank) return <span className="inline-flex rounded-md bg-red-50 px-2 py-0.5 font-semibold text-red-700">{miss}</span>;
  return (
    <span className={cx("inline-flex rounded-md px-2 py-0.5 font-semibold", rank <= 3 ? "bg-emerald-50 text-emerald-700" : "bg-signal-50 text-signal-800")}>
      {prefix} #{rank}
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
    <Link href="/setup#missing" className="group flex items-start gap-4 rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition hover:border-stone-300">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100"><Search size={17} /></span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14.5px] font-semibold">{open.length} thing{open.length === 1 ? "" : "s"} you&apos;re missing out on</span>
        <span className="mt-0.5 block truncate text-[13px] text-muted">{open.slice(0, 3).map((f) => f.title).join(" · ")}</span>
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 self-center text-[13px] font-semibold text-brand-700">Turn on fixes <ArrowRight size={14} className="transition group-hover:translate-x-0.5" /></span>
    </Link>
  );
}
