"use client";

import { ArrowRight, Compass, Database, Eye, GitBranch, Globe, Loader2, RefreshCw, Target, Users, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api, DepartmentInfo, IntegrationInfo, LeadReviewInfo, OrgInfo, timeAgo, usd, useApi } from "@/lib/api";
import { Badge, Button, cx, ErrorNote, Select, Toggle } from "./ui";

const HEALTH: Record<string, { label: string; tone: "green" | "amber" | "red" }> = {
  on_track: { label: "On track", tone: "green" },
  mixed: { label: "Mixed", tone: "amber" },
  off_track: { label: "Off track", tone: "red" },
};

const every = (days: number) => (days === 1 ? "every day" : days === 7 ? "every week" : `every ${days} days`);

/** The AI team lead on the org chart: between the team's people and its AI employees. */
export function LeadCard({ d, org, onChanged }: { d: DepartmentInfo; org: OrgInfo; onChanged?: () => void }) {
  const [open, setOpen] = useState(false);
  const lead = d.lead;
  const last = lead.last;
  const busy = last && (last.status === "queued" || last.status === "running");
  return (
    <>
      <button onClick={() => setOpen(true)}
        className={cx("block w-full rounded-xl border px-3 py-2.5 text-left hover:border-teal-400",
          lead.enabled ? "border-teal-200 bg-teal-50/50" : "border-dashed border-line bg-white")}>
        <span className="flex items-center gap-2.5">
          <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-full", lead.enabled ? "bg-teal-600 text-white" : "bg-gray-100 text-gray-400")}>
            <Compass size={16} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13.5px] font-semibold">{lead.name}</span>
            <span className="block truncate text-[11.5px] text-muted">{lead.enabled ? "AI team lead · always reviewing" : "AI team lead · off"}</span>
          </span>
        </span>
        {lead.enabled && (
          <span className="mt-1.5 flex items-center gap-1.5 text-[11.5px]">
            {busy ? (
              <><Loader2 size={11} className="animate-spin text-teal-700" /> <span className="text-teal-800">Reviewing the team…</span></>
            ) : last && last.status === "done" ? (
              <>
                {last.health && <Badge tone={HEALTH[last.health].tone} className="!px-1.5 !py-0 !text-[10.5px]">{HEALTH[last.health].label}</Badge>}
                <span className="text-muted">{timeAgo(last.created_at)}{last.proposals.length ? ` · ${last.proposals.length} suggestion${last.proposals.length === 1 ? "" : "s"}` : " · no changes"}</span>
              </>
            ) : (
              <span className="text-muted">Starts reviewing once goals are live</span>
            )}
          </span>
        )}
      </button>
      {open && <LeadPanel d={d} org={org} onClose={() => setOpen(false)} onChanged={onChanged} />}
    </>
  );
}

function LeadPanel({ d, org, onClose, onChanged }: { d: DepartmentInfo; org: OrgInfo; onClose: () => void; onChanged?: () => void }) {
  const lead = d.lead;
  const canManage = org.me.is_admin || org.me.department_ids.includes(d.id);
  const [reviews, setReviews] = useState<LeadReviewInfo[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cap, setCap] = useState(String(lead.monthly_cap_usd));
  const latest = reviews?.[0] || lead.last;
  const busy = latest && (latest.status === "queued" || latest.status === "running");

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const r = await api<LeadReviewInfo[]>(`/api/departments/${d.id}/lead/reviews`);
        if (!stop) setReviews(r);
      } catch { /* the card still shows the last review */ }
    };
    load();
    const t = setInterval(load, busy ? 2000 : 15000);
    return () => { stop = true; clearInterval(t); };
  }, [d.id, busy]);

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      onChanged?.();
      setReviews(await api<LeadReviewInfo[]>(`/api/departments/${d.id}/lead/reviews`));
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  const patch = (json: Record<string, unknown>) => run(() => api(`/api/departments/${d.id}/lead`, { method: "PATCH", json }));

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto bg-white shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="flex items-center gap-3 border-b border-line px-5 py-3">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-teal-600 text-white"><Compass size={18} /></span>
          <div className="min-w-0 flex-1">
            <div className="font-bold">{lead.name}</div>
            <div className="text-xs text-muted">AI team lead for {d.name}</div>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-gray-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="space-y-5 px-5 py-4">
          <p className="text-[13.5px] leading-relaxed text-gray-700">
            Keeps reviewing the {d.name} team, {every(lead.review_days)} and whenever you ask: how {org.org.name} is doing, the market,
            your numbers, and how each AI employee performs. Then it suggests what to change: updated targets, new goals,
            a new AI employee to take live, or pausing what isn&apos;t working. <b>Nothing changes until you approve it</b> in Needs you.
          </p>
          <LooksAt />

          {canManage && lead.enabled && (
            <Button size="sm" variant="primary" disabled={!!busy} onClick={() => run(() => api(`/api/departments/${d.id}/lead/review`, { method: "POST" }))}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} {busy ? "Reviewing…" : "Review the team now"}
            </Button>
          )}
          {err && <ErrorNote>{err}</ErrorNote>}

          {latest && latest.status === "done" && (
            <section>
              <div className="mb-1.5 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wide text-muted">
                Latest review · {timeAgo(latest.created_at)}
                {latest.health && <Badge tone={HEALTH[latest.health].tone}>{HEALTH[latest.health].label}</Badge>}
              </div>
              <p className="text-[13.5px] leading-relaxed">{latest.summary}</p>
              {(latest.research?.looked_at?.length || 0) > 0 && (
                <details className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-[12.5px]">
                  <summary className="cursor-pointer font-semibold text-muted">What it looked at ({latest.research!.looked_at!.length})</summary>
                  <ul className="mt-1.5 space-y-0.5 text-gray-700">{latest.research!.looked_at!.map((x, i) => <li key={i}>· {x}</li>)}</ul>
                  {(latest.research?.sources?.length || 0) > 0 && (
                    <ul className="mt-1.5 space-y-0.5">
                      {latest.research!.sources!.map((src) => (
                        <li key={src.url} className="truncate"><a href={src.url} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">{src.title}</a></li>
                      ))}
                    </ul>
                  )}
                </details>
              )}
              {latest.proposals.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {latest.proposals.map((p) => (
                    <li key={p.request_id} className="rounded-lg border border-line p-3">
                      <div className="text-[13.5px] font-semibold">{p.title}</div>
                      <p className="mt-0.5 text-[12.5px] text-muted">{p.reasoning}</p>
                      <Link href={`/approvals?id=${p.request_id}`} className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline">
                        Decide in Needs you <ArrowRight size={12} />
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[12.5px] text-muted">No changes suggested: the team is fine as it is.</p>
              )}
            </section>
          )}
          {latest && latest.status === "failed" && <ErrorNote>{latest.error || "The last review didn't finish."}</ErrorNote>}

          <section className="space-y-3 rounded-xl bg-gray-50 p-3">
            <div className="flex items-center justify-between gap-3 text-[13px]">
              <span className="font-semibold">AI team lead on</span>
              <Toggle on={lead.enabled} disabled={!canManage} onChange={(v) => patch({ enabled: v })} label="AI team lead on" />
            </div>
            {lead.enabled && (
              <>
                <label className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="font-semibold">Reviews</span>
                  <Select className="h-8 w-40 py-1 text-xs" disabled={!canManage} value={lead.review_days}
                    onChange={(e) => patch({ review_days: Number(e.target.value) })}>
                    {[1, 3, 7, 14, 30].map((n) => <option key={n} value={n}>{every(n)}</option>)}
                  </Select>
                </label>
                <label className="flex items-center justify-between gap-3 text-[13px]">
                  <span><span className="font-semibold">Monthly limit</span><span className="block text-[11.5px] text-muted">{usd(lead.spent_this_month_usd)} used this month · a review costs a few cents</span></span>
                  <span className="flex items-center gap-1">$
                    <input className="h-8 w-16 rounded-md border border-line px-2 text-xs" disabled={!canManage} value={cap}
                      onChange={(e) => setCap(e.target.value)} onBlur={() => Number(cap) >= 0 && Number(cap) !== lead.monthly_cap_usd && patch({ monthly_cap_usd: Number(cap) })} />
                  </span>
                </label>
              </>
            )}
          </section>

          {reviews && reviews.length > 1 && (
            <section>
              <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-muted">Earlier reviews</div>
              <ul className="space-y-1.5 text-[12.5px]">
                {reviews.slice(1, 6).map((r) => (
                  <li key={r.id} className="flex items-center gap-2">
                    <span className="w-20 shrink-0 text-muted">{timeAgo(r.created_at)}</span>
                    {r.health && <Badge tone={HEALTH[r.health].tone}>{HEALTH[r.health].label}</Badge>}
                    <span className="truncate text-muted">{r.status === "done" ? `${r.proposals.length} suggestion${r.proposals.length === 1 ? "" : "s"}` : r.status}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/** What the lead can look at: always the team's work and the web; the database and GitHub once connected. */
function LooksAt() {
  const { data } = useApi<IntegrationInfo[]>("/api/integrations", { live: false });
  const has = (k: string) => (data || []).some((i) => i.kind === k);
  const items: [React.ReactNode, string, boolean][] = [
    [<Target key="t" size={12} />, "Goals & results", true],
    [<Users key="u" size={12} />, "Each AI employee's work", true],
    [<Globe key="g" size={12} />, "Web, market & competitors", true],
    [<Database key="d" size={12} />, "Your database", has("postgres")],
    [<GitBranch key="b" size={12} />, "GitHub issues", has("github")],
  ];
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-muted"><Eye size={12} /> Looks at</div>
      <ul className="flex flex-wrap gap-1.5">
        {items.map(([icon, label, on]) => (
          <li key={label} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold",
            on ? "bg-teal-50 text-teal-800" : "bg-gray-50 text-gray-400")} title={on ? undefined : "Connect it in Settings → Code & data"}>
            {icon} {label}{on ? "" : " (not connected)"}
          </li>
        ))}
      </ul>
    </div>
  );
}
