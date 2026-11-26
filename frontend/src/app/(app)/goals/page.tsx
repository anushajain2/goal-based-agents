"use client";

import { Plus, Target } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StartGoal } from "@/components/StartGoal";
import { GoalProgress, GoalStatus, ProgressBar } from "@/components/goal";
import { Badge, Card, cx, Empty, ErrorNote, PageHeader, Select, Toggle } from "@/components/ui";
import { api, Campaign, OrgInfo, timeAgo, usd, useApi } from "@/lib/api";

type Tab = "live" | "suggested" | "drafts";

const inTab = (c: Campaign, tab: Tab) =>
  tab === "live" ? c.status !== "draft" : tab === "suggested" ? c.status === "draft" && c.origin === "setup" : c.status === "draft" && c.origin !== "setup";

export default function GoalsPage() {
  const { data, error, reload } = useApi<Campaign[]>("/api/campaigns");
  const [busy, setBusy] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  const [client, setClient] = useState("");
  const [dept, setDept] = useState("");
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false });

  const clients = useMemo(() => [...new Set((data || []).map((c) => c.client_name).filter(Boolean))].sort(), [data]);
  const counts = { live: 0, suggested: 0, drafts: 0 } as Record<Tab, number>;
  for (const c of data || []) for (const t of ["live", "suggested", "drafts"] as Tab[]) if (inTab(c, t)) counts[t]++;
  // Open on live goals, or on suggestions when nothing is running yet.
  const shown: Tab = tab ?? (counts.live ? "live" : counts.suggested ? "suggested" : "live");
  const rows = (data || []).filter((c) => {
    if (client && c.client_name !== client) return false;
    if (dept && c.department?.id !== dept) return false;
    return inTab(c, shown);
  });
  // Grouped by function (department), in the organization's order.
  const order = (org?.departments || []).map((d) => d.id);
  const groups = [...new Set(rows.map((c) => c.department?.id || ""))]
    .sort((a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999))
    .map((id) => ({ id, name: rows.find((c) => (c.department?.id || "") === id)?.department?.name || "Other", goals: rows.filter((c) => (c.department?.id || "") === id) }));
  const totals = rows.reduce((t, c) => ({ spent: t.spent + c.budget.spent, budget: t.budget + c.budget.total, actions: t.actions + c.actions_taken }), { spent: 0, budget: 0, actions: 0 });

  const [starting, setStarting] = useState<Campaign | null>(null);

  async function toggle(c: Campaign, on: boolean) {
    if (on && c.status === "draft") return setStarting(c); // first start: connect tools, review approvals
    setBusy(c.id);
    try {
      await api(`/api/campaigns/${c.id}/${on ? (c.status === "draft" ? "launch" : "resume") : "pause"}`, { method: "POST" });
      await reload();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Goals"
        subtitle="What each team is working toward, and how it's going this period."
        actions={<Link href="/goals/new" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white shadow-sm hover:bg-brand-600"><Plus size={16} /> New goal</Link>}
      />

      {error && <ErrorNote>Can&apos;t reach the backend ({error}).</ErrorNote>}
      {starting && <StartGoal goals={[starting]} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); reload(); }} />}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 px-5 py-3">
          <div className="inline-flex rounded-xl bg-stone-100 p-1 text-[13px] font-semibold">
            {(["live", "suggested", "drafts"] as Tab[]).filter((t) => t !== "drafts" || counts.drafts).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={cx("rounded-lg px-3 py-1.5 transition", shown === t ? "bg-white text-ink shadow-sm" : "text-stone-500 hover:text-ink")}>
                {{ live: "Live", suggested: "Suggested", drafts: "Not started" }[t]}
                <span className="tabular ml-1.5 text-stone-400">{counts[t]}</span>
              </button>
            ))}
          </div>
          {(org?.departments.length || 0) > 1 && (
            <div className="w-48">
              <Select className="h-8 py-1 text-xs" value={dept} onChange={(e) => setDept(e.target.value)}>
                <option value="">All departments</option>
                {org!.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            </div>
          )}
          {clients.length > 0 && (
            <div className="w-48">
              <Select className="h-8 py-1 text-xs" value={client} onChange={(e) => setClient(e.target.value)}>
                <option value="">All clients</option>
                {clients.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </div>
          )}
          <span className="ml-auto text-xs text-muted">
            Spent <b className="tabular text-ink">{usd(totals.spent)}</b> of {usd(totals.budget)}
          </span>
        </div>

        {data && rows.length === 0 ? (
          <Empty icon={<Target size={36} />} title={shown === "live" ? "Nothing live yet" : "Nothing here"}>
            {shown === "live" && counts.suggested
              ? <button onClick={() => setTab("suggested")} className="font-semibold text-brand-600">See the {counts.suggested} suggested goals →</button>
              : <Link href="/goals/new" className="font-semibold text-brand-600">Give Oton a goal →</Link>}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-[13px]">
              <thead className="text-[11.5px] font-semibold uppercase tracking-[0.05em] text-stone-400">
                <tr>
                  <th className="w-16 px-5 py-3 font-semibold">On</th>
                  <th className="px-2 py-3 font-semibold">Goal</th>
                  <th className="w-56 px-2 py-3 font-semibold">This period</th>
                  <th className="w-44 px-2 py-3 font-semibold">Spent</th>
                  <th className="px-5 py-3 font-semibold">Latest</th>
                </tr>
              </thead>
              {groups.map((grp) => (
              <tbody key={grp.id}>
                <tr className="border-t border-line">
                  <td colSpan={5} className="bg-stone-50/80 px-5 py-2 text-[12.5px] font-semibold text-stone-700">
                    {grp.name} <span className="font-medium text-stone-400">· {grp.goals.length}</span>
                  </td>
                </tr>
                {grp.goals.map((c) => {
                  const on = c.status === "active";
                  const pct = c.budget.total ? (c.budget.spent / c.budget.total) * 100 : 0;
                  return (
                    <tr key={c.id} className="border-t border-line/70 align-top transition hover:bg-stone-50/70">
                      <td className="px-5 py-3.5">
                        <Toggle on={on} disabled={c.can_manage === false || ["completed", "out_of_budget"].includes(c.status) || busy === c.id} onChange={(v) => toggle(c, v)} label={`Turn ${c.name} ${on ? "off" : "on"}`} />
                      </td>
                      <td className="max-w-sm px-2 py-3.5">
                        <Link href={`/goals/${c.id}`} className="text-[13.5px] font-semibold text-ink hover:text-brand-600">{c.name}</Link>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted">
                          {!on && <GoalStatus c={c} />}
                          {c.origin === "setup" && c.status === "draft" && <Badge tone="blue">Suggested</Badge>}
                          {c.pending_requests > 0 && <Badge tone="amber">Needs you</Badge>}
                          {c.client_name && <Badge tone="violet">{c.client_name}</Badge>}
                        </div>
                      </td>
                      <td className="px-2 py-3.5"><GoalProgress c={c} /></td>
                      <td className="px-2 py-3.5">
                        <div className="tabular text-[13px] font-medium">{usd(c.budget.spent)} <span className="font-normal text-muted">of {usd(c.budget.total)}</span></div>
                        <ProgressBar pct={pct} tone="gray" className="mt-1.5" />
                      </td>
                      <td className="max-w-[280px] px-5 py-3.5">
                        {c.last_activity ? (
                          <>
                            <div className="line-clamp-2 text-[12.5px] text-stone-700">{c.last_activity.title}</div>
                            <div className="mt-0.5 text-[11.5px] text-muted">{timeAgo(c.last_activity.at)}</div>
                          </>
                        ) : <span className="text-muted">Not started</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              ))}
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
