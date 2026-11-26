"use client";

import { ArrowRight, Bot, Check, Flag, Lightbulb, Loader2, Plug, Search, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, Campaign, CompanyProfile, Milestone, OrgInfo, Opportunity, ScoreRow, usd, Visibility } from "@/lib/api";
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
export function Opportunities({ profile, org, goals, orgName, onStart, onOpen, canStart, titled = true }: {
  profile: CompanyProfile | null | undefined; org: OrgInfo | null | undefined; goals: Campaign[] | null | undefined; orgName: string;
  onStart: (goals: Campaign[]) => void; onOpen: (goal: Campaign) => void; canStart: boolean;
  titled?: boolean;  // false where the page title already says it (onboarding)
}) {
  const found = profile?.opportunities;
  const has = !!found && (found.findings.length > 0 || (found.unlock || []).length > 0 || (found.scorecard || []).length > 0);
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
        {titled ? (
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> What you&apos;re missing out on</h2>
            <p className="text-sm text-muted">What we found about {orgName}, with evidence. Each gap has a goal ready to turn on, and big ones come in steps with their price.</p>
          </div>
        ) : <div />}
        {canStart && unique.length > 1 && (
          <button onClick={() => onStart(unique)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            Start {unique.length} first steps <ArrowRight size={15} />
          </button>
        )}
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      {(found.checks || []).some((c) => c.why) && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
          <span className="text-muted">What we checked, and why:</span>
          {found.checks!.map((c) => (
            <span key={c.key} title={c.why ? `${c.why}${c.expect ? ` · Expected: ${c.expect}` : ""}` : undefined}
              className="cursor-help rounded-full border border-line bg-white px-2.5 py-0.5 font-medium text-stone-700">{c.title}</span>
          ))}
        </div>
      )}

      {found.visibility && (found.visibility.search.length > 0 || found.visibility.ai.length > 0) && <Findable v={found.visibility} name={orgName} />}
      {(found.scorecard || []).length > 0 && <Scorecard rows={found.scorecard!} name={orgName} />}

      <div className="space-y-4">
        {found.findings.map((f, i) => {
          const steps = f.milestones || [];
          const goal = f.goal_id ? byId.get(f.goal_id) : undefined;
          const facts = factsOf(f);
          return (
            <article key={i} className="flex flex-col rounded-2xl border border-line bg-white p-6 shadow-[var(--shadow-card)]">
              <div className="flex items-center gap-2">
                <TeamTag name={teamName(f.team_kind, org)} />
                <span className="text-[11.5px] font-medium text-muted">{CONFIDENCE[f.confidence]}</span>
              </div>
              <h3 className="mt-3 max-w-[60ch] text-[19px] font-semibold leading-snug tracking-[-0.015em]">{f.title}</h3>

              <div className="mt-5 text-[11.5px] font-semibold uppercase tracking-wide text-muted">What we found</div>
              <ul className="mt-2 max-w-[75ch] space-y-2">
                {facts.map((x, k) => (
                  <li key={k} className="flex gap-3 text-[14.5px] leading-relaxed text-stone-800">
                    <span className="mt-[10px] h-1.5 w-1.5 shrink-0 rounded-full bg-stone-400" />
                    <span>{x}</span>
                  </li>
                ))}
              </ul>

              {f.impact && (
                <div className="mt-5 max-w-[75ch] rounded-xl border-l-4 border-signal-500 bg-signal-50 px-4 py-3.5">
                  <div className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-signal-800">
                    <Lightbulb size={14} /> Why this matters
                  </div>
                  <p className="mt-1.5 text-[15px] leading-relaxed text-ink">{f.impact}</p>
                  {f.estimate && (
                    <p className="mt-2 text-[13px] text-signal-800">
                      <b className="font-semibold">{f.estimate}</b>{f.assumption && <span> · {f.assumption}</span>}
                    </p>
                  )}
                </div>
              )}

              <div className="mt-6">
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
                    <span className="text-muted">Needs {/^[aeiou]/i.test(teamName(f.team_kind, org)) ? "an" : "a"} {teamName(f.team_kind, org)} team</span>
                    <Link href="/team" className="font-semibold text-brand-700 hover:underline">Add it</Link>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {(found.unlock || []).length > 0 && (
        <Unlock groups={found.unlock!} org={org} goals={goals || []} canStart={canStart} onStart={onStart} onOpen={onOpen} />
      )}
    </section>
  );
}

/** "Connect to unlock", per team: what connecting a tool lets its AI employee check, on your own data. */
function Unlock({ groups, org, goals, canStart, onStart, onOpen }: {
  groups: NonNullable<NonNullable<CompanyProfile["opportunities"]>["unlock"]>; org: OrgInfo | null | undefined; goals: Campaign[];
  canStart: boolean; onStart: (g: Campaign[]) => void; onOpen: (g: Campaign) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const has = (kind: string) => !!org?.departments.some((d) => d.kind === kind);
  const sorted = [...groups].sort((a, b) => Number(has(b.team_kind)) - Number(has(a.team_kind)));
  async function go(key: string) {
    setBusy(key);
    setErr(null);
    try {
      const { goal_id } = await api<{ goal_id: string }>(`/api/org/unlock/${key}`, { method: "POST" });
      onStart([await api<Campaign>(`/api/campaigns/${goal_id}`)]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
      <div className="border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2 text-[15px] font-semibold"><Plug size={16} className="text-brand-600" /> Connect to unlock</div>
        <div className="text-[12.5px] text-muted">The rest of what you&apos;re missing is in your own tools. Connect one and that team&apos;s AI employee checks it, then fixes what it finds, with your OK.</div>
      </div>
      {err && <div className="px-5 pt-3"><ErrorNote>{err}</ErrorNote></div>}
      <div className="-mb-px -mr-px grid sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((g) => {
          const titles = [...new Set(g.checks.map((c) => c.title))];
          return (
            <div key={g.team_kind} className="border-b border-r border-line p-4">
              <div className="flex items-center justify-between gap-2">
                <TeamTag name={teamName(g.team_kind, org)} />
                {!has(g.team_kind) && <Link href="/team" className="text-[12px] font-semibold text-brand-700 hover:underline">Add team</Link>}
              </div>
              <ul className="mt-3 space-y-3">
                {titles.map((title) => {
                  const options = g.checks.filter((c) => c.title === title);
                  const live = goals.find((x) => options.some((o) => o.goal === x.name));
                  return (
                    <li key={title}>
                      <div className="text-[13.5px] font-semibold leading-snug">{title}</div>
                      <div className="text-[12px] leading-snug text-muted">{options[0].how}</div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {live ? (
                          <button onClick={() => (live.status === "draft" && canStart ? onStart([live]) : onOpen(live))}
                            className={cx("inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[12px] font-semibold",
                              live.status === "draft" ? "bg-brand-600 text-white hover:bg-brand-700" : "text-emerald-700")}>
                            {live.status === "draft" ? <>Turn on <ArrowRight size={12} /></> : <><Check size={13} /> On</>}
                          </button>
                        ) : has(g.team_kind) && canStart ? options.map((o) => (
                          <button key={o.key} onClick={() => go(o.key)} disabled={busy === o.key}
                            className="inline-flex h-7 items-center gap-1 rounded-md border border-line bg-white px-2.5 text-[12px] font-semibold hover:border-stone-300 disabled:opacity-60">
                            {busy === o.key ? <Loader2 size={12} className="animate-spin" /> : <Plug size={12} />} Connect {o.label}
                          </button>
                        )) : <span className="text-[12px] text-muted">{options.map((o) => o.label).join(" or ")}</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
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
              {(m.does || []).length > 0 && (
                <ul className="mt-2 space-y-0.5 text-[12px] text-stone-700">
                  {m.does!.slice(0, 3).map((d) => <li key={d} className="flex gap-1.5"><span className="text-brand-600">·</span><span className="line-clamp-1">{d}</span></li>)}
                </ul>
              )}
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
            <tr className="border-b border-line bg-canvas text-[11px] font-semibold uppercase tracking-[0.05em] text-muted">
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
                              <div className={cx("text-[11.5px] font-medium", s.ai_overview.mentioned ? "text-emerald-700" : "text-red-700")}>
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
          <div className="mb-2 text-[12px] font-semibold uppercase tracking-[0.05em] text-muted">Google Maps results</div>
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
function Scorecard({ rows, name }: { rows: ScoreRow[]; name: string }) {
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
            <tr className="border-b border-line bg-canvas text-[11px] font-semibold uppercase tracking-[0.05em] text-muted">
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
                  {r.note && <div className="text-[11.5px] text-muted">{r.note}</div>}
                </td>
                <td className="px-3 py-2.5">
                  <span className={cx("inline-flex items-start gap-1.5 font-medium", r.you.status === "bad" ? "text-red-700" : r.you.status === "good" ? "text-emerald-700" : "text-ink")}>
                    <span className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", r.you.status === "bad" ? "bg-red-500" : r.you.status === "good" ? "bg-emerald-500" : "bg-stone-300")} />
                    {r.you.display}
                  </span>
                </td>
                {names.map((n) => <td key={n} className="px-3 py-2.5 text-stone-600">{r.others.find((o) => o.name === n)?.display ?? <span className="text-stone-300">-</span>}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
