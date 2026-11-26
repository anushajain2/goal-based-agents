"use client";

import { ArrowRight, Beaker, CheckCircle2, ChevronDown, ChevronRight, Gauge, Lightbulb, Loader2, Ruler, ShieldCheck, Sparkles, TrendingUp, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { api, Campaign, GoalApproach, GoalUpdate, Pace, timeAgo } from "@/lib/api";
import { cx } from "./ui";

const fmt = (v: number | null | undefined) => (v == null ? "—" : Number.isInteger(v) ? v.toLocaleString() : v.toFixed(1));

/** The goal as a funnel: each stage's number now, its benchmark, and the bottleneck being worked on. */
export function Funnel({ a, compact }: { a: GoalApproach; compact?: boolean }) {
  const stages = a.model.stages;
  return (
    <div>
      <div className="flex flex-wrap items-stretch gap-1.5">
        {stages.map((s, i) => {
          const stuck = s.name === a.model.bottleneck;
          return (
            <div key={s.name} className="flex min-w-0 flex-1 items-center gap-1.5">
              <div className={cx("min-w-[110px] flex-1 rounded-xl px-3 py-2.5 ring-1 ring-inset",
                stuck ? "bg-signal-50 ring-signal-200" : "bg-canvas ring-line")}>
                <div className="line-clamp-2 text-[12px] font-medium leading-snug text-stone-600">{s.name}</div>
                <div className="mt-0.5 flex items-center gap-2">
                  <span className="tabular text-[20px] font-bold leading-tight">{fmt(s.now)}</span>
                  {stuck && <span className="rounded-full bg-signal-500 px-1.5 text-[10px] font-bold uppercase tracking-wide text-white">Bottleneck</span>}
                </div>
                {!compact && s.benchmark && <div className="truncate text-[11px] text-muted" title={s.benchmark}>Good: {s.benchmark}</div>}
              </div>
              {i < stages.length - 1 && <ChevronRight size={16} className="shrink-0 text-stone-300" />}
            </div>
          );
        })}
      </div>
      {a.model.why && <p className="mt-2 text-[12.5px] text-muted"><b className="font-semibold text-signal-800">Working on {a.model.bottleneck.toLowerCase()} first:</b> {a.model.why}</p>}
    </div>
  );
}

const PACE: Record<Pace["status"], { label: string; cls: string }> = {
  behind: { label: "Behind", cls: "bg-red-50 text-red-700 ring-red-100" },
  on_pace: { label: "On pace", cls: "bg-emerald-50 text-emerald-700 ring-emerald-100" },
  ahead: { label: "Ahead", cls: "bg-emerald-50 text-emerald-700 ring-emerald-100" },
  hit: { label: "Target hit", cls: "bg-emerald-50 text-emerald-700 ring-emerald-100" },
};

/** Progress against where it should be by now, and the rate it needs from here. */
export function PaceLine({ p }: { p: Pace }) {
  const pct = Math.min(100, (p.progress / Math.max(p.target, 0.01)) * 100);
  const expected = Math.min(100, (p.expected_by_now / Math.max(p.target, 0.01)) * 100);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className={cx("rounded-full px-2 py-0.5 font-semibold ring-1 ring-inset", PACE[p.status].cls)}>{PACE[p.status].label}</span>
        {p.status === "behind" && p.per_day_needed != null && (
          <span className="text-muted">needs {fmt(p.per_day_needed)}/day{p.per_day_so_far != null ? `, doing ${fmt(p.per_day_so_far)}` : ""}</span>
        )}
      </div>
      <div className="relative mt-2 h-2 rounded-full bg-stone-100">
        <div className={cx("h-full rounded-full", p.status === "behind" ? "bg-signal-500" : "bg-emerald-500")} style={{ width: `${pct}%` }} />
        <div className="absolute -top-1 h-4 w-0.5 rounded bg-stone-500" style={{ left: `${expected}%` }} title={`Expected by now: ${fmt(p.expected_by_now)}`} />
      </div>
    </div>
  );
}

/** A short update, like a good employee's: what was measured, what that tells us, what's changing. */
export function UpdateCard({ u, who, at, className }: { u: GoalUpdate; who?: string; at?: string; className?: string }) {
  const rows: [React.ReactNode, string, string][] = [
    [<Ruler key="m" size={13} />, "Measured", u.measured],
    [<Lightbulb key="l" size={13} />, "Learned", u.learned],
    [<TrendingUp key="c" size={13} />, "Changing", u.changing],
  ];
  return (
    <div className={cx("rounded-xl border border-line bg-white p-3.5", className)}>
      {(who || at) && <div className="mb-2 text-[11.5px] font-semibold text-muted">{who ? `Update from ${who}` : "Update"}{at ? ` · ${timeAgo(at)}` : ""}</div>}
      <ul className="space-y-1.5">
        {rows.filter(([, , t]) => t).map(([icon, label, t]) => (
          <li key={label} className="flex gap-2 text-[13px] leading-snug">
            <span className={cx("mt-0.5 inline-flex w-[84px] shrink-0 items-center gap-1 text-[11.5px] font-semibold",
              label === "Changing" ? "text-brand-700" : "text-stone-500")}>{icon}{label}</span>
            <span className={label === "Changing" ? "font-medium" : ""}>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const STATUS: Record<string, string> = {
  planned: "bg-stone-100 text-stone-600", testing: "bg-brand-50 text-brand-700", working: "bg-emerald-50 text-emerald-700",
  dropped: "bg-stone-100 text-stone-400 line-through",
};

/** The ways it's pursuing the goal, creative ones marked, with what's working. */
export function Approaches({ a, milestone }: { a: GoalApproach; milestone?: number }) {
  const list = a.approaches.filter((x) => milestone == null || x.milestone === milestone);
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {list.map((x) => (
        <li key={x.id} className={cx("rounded-xl px-3 py-2.5 ring-1 ring-inset", x.creative ? "bg-brand-50/40 ring-brand-100" : "bg-canvas ring-line")}>
          <div className="flex items-center gap-1.5">
            {x.creative && <Sparkles size={13} className="shrink-0 text-brand-600" />}
            <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{x.name}</span>
            {x.status !== "planned" && <span className={cx("rounded-full px-1.5 text-[10.5px] font-semibold capitalize", STATUS[x.status])}>{x.status}</span>}
          </div>
          <div className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-muted">{x.what}</div>
        </li>
      ))}
    </ul>
  );
}

/** The running experiment and what's been learned so far. */
export function Learning({ a }: { a: GoalApproach }) {
  const running = a.experiments.find((x) => x.status === "running") || a.experiments.find((x) => x.status === "planned");
  const done = a.experiments.filter((x) => x.status === "kept" || x.status === "dropped").slice(-3).reverse();
  if (!running && !done.length && !a.learnings.length) return null;
  return (
    <div className="space-y-3">
      {running && (
        <div className="rounded-xl bg-canvas px-3 py-2.5 ring-1 ring-inset ring-line">
          <div className="flex items-center gap-1.5 text-[11.5px] font-semibold text-muted"><Beaker size={13} /> {running.status === "running" ? "Testing now" : "First test"}</div>
          <div className="mt-0.5 text-[13px] font-medium">{running.hypothesis}</div>
          <div className="text-[12px] text-muted">{running.change}{running.judge_after ? ` · judged after ${running.judge_after}` : ""}</div>
        </div>
      )}
      {done.map((x) => (
        <div key={x.id} className="flex gap-2 text-[12.5px]">
          {x.status === "kept" ? <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-600" /> : <XCircle size={14} className="mt-0.5 shrink-0 text-stone-400" />}
          <span><span className="font-medium">{x.hypothesis}</span>{x.result ? <span className="text-muted"> · {x.result}</span> : null}</span>
        </div>
      ))}
      {a.learnings.length > 0 && (
        <ul className="space-y-1">
          {a.learnings.slice(-4).reverse().map((l) => (
            <li key={l.text} className="flex gap-2 text-[12.5px]"><Lightbulb size={13} className="mt-0.5 shrink-0 text-signal-600" />
              <span><span className="font-medium">{l.text}</span>{l.evidence ? <span className="text-muted"> ({l.evidence})</span> : null}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** On the goal page: how it gets hit, the pace, the latest update, approaches and learnings. */
export function HowItsGoing({ c, update }: { c: Campaign; update?: { u: GoalUpdate; at: string } | null }) {
  const a = c.approach;
  if (!a) return null;
  const pace = c.target?.pace;
  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="space-y-4 rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)]">
        <div className="flex items-center gap-2 text-[14px] font-semibold"><Gauge size={16} className="text-brand-600" /> How this goal gets hit</div>
        <Funnel a={a} />
        {pace && <PaceLine p={pace} />}
        <div>
          <div className="mb-2 text-[12px] font-semibold text-muted">Approaches</div>
          <Approaches a={a} />
        </div>
      </div>
      <div className="space-y-4">
        {update ? <UpdateCard u={update.u} who="Autopilot" at={update.at} className="shadow-[var(--shadow-card)]" /> : (
          <div className="rounded-xl border border-dashed border-line bg-white p-3.5 text-[12.5px] text-muted">
            Autopilot posts a short update here when there&apos;s news: what it measured, what it learned, and what it&apos;s changing.
          </div>
        )}
        <div className="rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)]">
          <div className="mb-2.5 text-[12px] font-semibold text-muted">Experiments and learnings</div>
          <Learning a={a} />
          {!a.experiments.length && !a.learnings.length && <p className="text-[12.5px] text-muted">Nothing yet.</p>}
        </div>
      </div>
    </section>
  );
}

/** In the start flow: what Autopilot will do, before anyone turns it on. */
/** How the goal gets hit, made on first look (once per goal). */
function useApproach(goal: Campaign): { a: GoalApproach | null; failed: boolean } {
  const [a, setA] = useState<GoalApproach | null>(goal.approach || null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (a) return;
    let stop = false;
    api<GoalApproach>(`/api/campaigns/${goal.id}/approach`, { method: "POST" })
      .then((x) => { if (!stop) setA(x); })
      .catch(() => { if (!stop) setFailed(true); });
    return () => { stop = true; };
  }, [goal.id, a]);
  return { a, failed };
}

function Part({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="flex gap-3.5">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-[12px] font-bold text-white">{n}</span>
      <div className="min-w-0 flex-1">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">{title}</h3>
        <div className="mt-2">{children}</div>
      </div>
    </section>
  );
}

/** The plan shown before turning a goal on, as a short story: what you get, the hard part, how. */
export function PlanStory({ goal }: { goal: Campaign }) {
  const { a, failed } = useApproach(goal);
  const [more, setMore] = useState(false);
  const firstStep = a ? Math.min(...a.approaches.map((x) => x.milestone)) : 1;
  const now = a ? a.approaches.filter((x) => x.milestone === firstStep) : [];
  const later = a ? a.approaches.filter((x) => x.milestone !== firstStep) : [];
  const top = now.slice(0, 3);
  const rest = now.slice(3);
  const hidden = rest.length + later.length;
  return (
    <div className="space-y-7 py-1">
      {goal.first_deliverable && (
        <Part n={1} title="In week 1 you get">
          <p className="text-[16px] font-medium leading-relaxed text-ink">{goal.first_deliverable}</p>
        </Part>
      )}

      {!a && !failed && (
        <div className="flex items-center gap-2 pl-10 text-[13px] text-muted">
          <Loader2 size={14} className="animate-spin" /> Working out how to hit this goal…
        </div>
      )}

      {a && (
        <Part n={goal.first_deliverable ? 2 : 1} title="The hard part">
          <div className="flex flex-wrap items-center gap-1.5">
            {a.model.stages.map((s, i) => (
              <span key={s.name} className="inline-flex items-center gap-1.5">
                <span className={cx("rounded-full px-2.5 py-1 text-[12.5px] font-medium",
                  s.name === a.model.bottleneck ? "bg-signal-100 text-signal-800 ring-1 ring-inset ring-signal-300" : "bg-canvas text-stone-600 ring-1 ring-inset ring-line")}>
                  {s.name}
                </span>
                {i < a.model.stages.length - 1 && <ChevronRight size={14} className="text-stone-300" />}
              </span>
            ))}
          </div>
          {a.model.why && (
            <p className="mt-2.5 text-[15px] leading-relaxed text-ink">
              <b className="font-semibold">{a.model.bottleneck}</b> is where this usually gets stuck. {a.model.why}
            </p>
          )}
        </Part>
      )}

      {a && top.length > 0 && (
        <Part n={goal.first_deliverable ? 3 : 2} title="How it will do it">
          <ol className="space-y-3">
            {top.map((x, i) => (
              <li key={x.id} className="flex gap-3">
                <span className="tabular mt-0.5 w-4 shrink-0 text-[14px] font-semibold text-stone-400">{i + 1}.</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-[15px] font-semibold">
                    {x.name}
                    {x.creative && <span className="inline-flex items-center gap-0.5 rounded-full bg-brand-50 px-1.5 py-px text-[10.5px] font-semibold text-brand-700"><Sparkles size={10} /> creative</span>}
                  </div>
                  <p className="text-[14px] leading-relaxed text-stone-600">{x.what}</p>
                </div>
              </li>
            ))}
          </ol>
          {hidden > 0 && (
            <div className="mt-3">
              <button onClick={() => setMore(!more)} className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand-700 hover:underline">
                {more ? "Show less" : `${hidden} more ${hidden === 1 ? "idea" : "ideas"} it can try`}
                <ChevronDown size={14} className={cx("transition", more && "rotate-180")} />
              </button>
              {more && (
                <ul className="mt-2.5 space-y-2 border-l-2 border-line pl-4">
                  {[...rest, ...later].map((x) => (
                    <li key={x.id} className="text-[13.5px] leading-relaxed">
                      <span className="font-semibold">{x.name}</span>
                      {x.milestone !== firstStep && <span className="text-muted"> (only if you go further)</span>}
                      <span className="text-stone-600">: {x.what}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Part>
      )}

      <p className="flex items-start gap-2 rounded-xl bg-canvas px-4 py-3 text-[13px] text-stone-600">
        <ShieldCheck size={16} className="mt-px shrink-0 text-emerald-600" />
        <span>You approve anything that goes out. It checks what&apos;s working every session and adjusts, and sends you a short update when there&apos;s news.</span>
      </p>
    </div>
  );
}

export function WhatItWillDo({ goal, compact }: { goal: Campaign; compact?: boolean }) {
  const { a, failed } = useApproach(goal);
  if (failed) return null;
  if (!a) {
    return <div className="flex items-center gap-2 rounded-xl bg-canvas px-3 py-3 text-[12.5px] text-muted"><Loader2 size={14} className="animate-spin" /> Working out how to hit this goal…</div>;
  }
  const creative = a.approaches.filter((x) => x.creative).length;
  const milestones = [...new Set(a.approaches.map((x) => x.milestone))].sort();
  if (compact) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {a.approaches.slice(0, 5).map((x) => (
          <span key={x.id} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium ring-1 ring-inset",
            x.creative ? "bg-brand-50 text-brand-800 ring-brand-100" : "bg-white text-stone-700 ring-line")}>
            {x.creative && <Sparkles size={11} />}{x.name}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 text-[12px] font-semibold text-muted">How it gets hit</div>
        <Funnel a={a} compact />
      </div>
      <div>
        <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-muted">
          What it will do{creative ? <span className="inline-flex items-center gap-1 text-brand-700"><Sparkles size={12} /> {creative} creative</span> : null}
        </div>
        {milestones.length > 1 ? (
          <div className="space-y-3">
            {milestones.map((m) => (
              <div key={m}>
                <div className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold">
                  <ArrowRight size={12} className="text-brand-600" /> Step {m}
                  <span className="font-normal text-muted">{m === milestones[0] ? "· starts now" : "· only if you go further"}</span>
                </div>
                <Approaches a={a} milestone={m} />
              </div>
            ))}
          </div>
        ) : <Approaches a={a} />}
      </div>
      {a.experiments[0] && (
        <div className="flex gap-2 rounded-xl bg-canvas px-3 py-2.5 text-[12.5px] ring-1 ring-inset ring-line">
          <Beaker size={14} className="mt-0.5 shrink-0 text-stone-500" />
          <span><b className="font-semibold">First test:</b> {a.experiments[0].hypothesis} <span className="text-muted">({a.experiments[0].change})</span></span>
        </div>
      )}
      <p className="text-[12px] text-muted">It re-plans every session: works the bottleneck, checks the pace, keeps what works, and posts a short update when there&apos;s news.</p>
    </div>
  );
}
