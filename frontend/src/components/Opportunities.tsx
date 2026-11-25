"use client";

import { ArrowRight, Check, ExternalLink, Plug, Search, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { Campaign, CompanyProfile, OrgInfo, Opportunity } from "@/lib/api";
import { TeamTag } from "./team";
import { cx } from "./ui";

const CONFIDENCE: Record<Opportunity["confidence"], string> = { high: "Clear signal", medium: "Likely", low: "Worth a look" };

function teamName(kind: string, org: OrgInfo | null | undefined) {
  const d = org?.departments.find((x) => x.kind === kind);
  return d?.name || kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

function host(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

/** "What you're missing out on": gaps found from public information, each with the goal that fixes it. */
export function Opportunities({ profile, org, goals, orgName, onStart, onOpen, canStart }: {
  profile: CompanyProfile | null | undefined; org: OrgInfo | null | undefined; goals: Campaign[] | null | undefined; orgName: string;
  onStart: (goals: Campaign[]) => void; onOpen: (goal: Campaign) => void; canStart: boolean;
}) {
  const found = profile?.opportunities;
  const has = !!found && (found.findings.length > 0 || found.deeper.length > 0);
  useEffect(() => {  // arriving from Home's "Turn on fixes" link
    if (has && window.location.hash === "#missing") document.getElementById("missing")?.scrollIntoView({ behavior: "smooth" });
  }, [has]);
  if (!found || !has) return null;
  const byId = new Map((goals || []).map((g) => [g.id, g]));
  const drafts = found.findings.map((f) => (f.goal_id ? byId.get(f.goal_id) : undefined))
    .filter((g): g is Campaign => !!g && g.status === "draft" && g.can_manage !== false);
  const unique = [...new Map(drafts.map((g) => [g.id, g])).values()];

  return (
    <section id="missing" className="scroll-mt-6">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> What you&apos;re missing out on</h2>
          <p className="text-sm text-muted">What we found from public information about {orgName}. Each one has a goal ready to turn on.</p>
        </div>
        {canStart && unique.length > 1 && (
          <button onClick={() => onStart(unique)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            Fix all {unique.length} <ArrowRight size={15} />
          </button>
        )}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {found.findings.map((f, i) => {
          const goal = f.goal_id ? byId.get(f.goal_id) : undefined;
          return (
            <article key={i} className="flex flex-col rounded-2xl border border-line bg-white p-5 shadow-[var(--shadow-card)]">
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
                {goal ? (
                  <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                    <button onClick={() => onOpen(goal)} className="min-w-0 flex-1 truncate text-left text-[13px] text-muted hover:text-ink">
                      Goal: <span className="font-semibold text-ink">{goal.name}</span>
                    </button>
                    {goal.status === "draft" ? (
                      canStart && goal.can_manage !== false && (
                        <button onClick={() => onStart([goal])} className="inline-flex h-8 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[12.5px] font-semibold text-white hover:bg-brand-700">
                          Turn on <ArrowRight size={13} />
                        </button>
                      )
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-emerald-700"><Check size={14} /> Live</span>
                    )}
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
        <div className="mt-3 rounded-2xl border border-dashed border-stone-300 bg-white/60 p-4">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold"><Plug size={15} className="text-brand-600" /> Connect for a deeper check</div>
          <p className="text-[12.5px] text-muted">With your own data, your AI employees can measure these for real.</p>
          <ul className="mt-2.5 flex flex-wrap gap-2">
            {found.deeper.map((d) => (
              <li key={d.tool}>
                <Link href="/connections" className={cx("inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-[12.5px] hover:border-stone-300")}>
                  <b className="font-semibold">{d.label}</b><span className="text-muted">{d.check}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** On Home: the gaps whose goals aren't on yet. */
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
