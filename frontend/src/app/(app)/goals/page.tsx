"use client";

import { Plus, Target } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StartGoal } from "@/components/StartGoal";
import { AgentAvatar } from "@/components/team";
import { GoalProgress, GoalStatus, ProgressBar } from "@/components/goal";
import { Card, cx, Empty, ErrorNote, Select, Toggle } from "@/components/ui";
import { api, Campaign, num, OrgInfo, timeAgo, usd, useApi } from "@/lib/api";

type Tab = "live" | "suggested" | "drafts";

const TAB_HELP: Record<Tab, string> = {
  live: "Goals your AI employees are working on, or have worked on.",
  suggested: "Suggested by setup research for where your company is now. Nothing runs until you start one.",
  drafts: "Goals you set up but haven't started yet.",
};

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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Goals</h1>
          <p className="text-sm text-muted">What your AI employees are working toward, with progress, spend and what they did last.</p>
        </div>
        <Link href="/goals/new" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3.5 text-sm font-semibold text-white hover:bg-brand-600">
          <Plus size={16} /> New goal
        </Link>
      </div>

      {error && <ErrorNote>Can&apos;t reach the backend ({error}).</ErrorNote>}
      {starting && <StartGoal goals={[starting]} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); reload(); }} />}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
          <div className="inline-flex overflow-hidden rounded-md border border-line text-xs font-semibold">
            {(["live", "suggested", "drafts"] as Tab[]).filter((t) => t !== "drafts" || counts.drafts).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={cx("px-3 py-1.5", shown === t ? "bg-ink text-white" : "bg-white text-muted hover:text-ink")}>
                {{ live: "Live", suggested: "Suggested", drafts: "Not started" }[t]}
                <span className={cx("ml-1.5", shown === t ? "text-white/70" : "text-gray-400")}>{counts[t]}</span>
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
          <span className="text-xs text-muted">{TAB_HELP[shown]}</span>
          <span className="ml-auto text-xs text-muted">
            {rows.length} goals · spent <b className="tabular text-ink">{usd(totals.spent)}</b> of {usd(totals.budget)} · {num(totals.actions)} actions
          </span>
        </div>

        {data && rows.length === 0 ? (
          <Empty icon={<Target size={36} />} title={shown === "live" ? "Nothing live yet" : "Nothing here"}>
            {shown === "live" && counts.suggested
              ? <button onClick={() => setTab("suggested")} className="font-semibold text-brand-600">See the {counts.suggested} suggested goals →</button>
              : <Link href="/goals/new" className="font-semibold text-brand-600">Give an AI employee a goal →</Link>}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1240px] text-left text-[13px]">
              <thead className="border-b border-line bg-gray-50/60 text-xs font-semibold text-muted">
                <tr>
                  <th className="w-14 px-4 py-2.5">On</th>
                  <th className="px-2 py-2.5">Goal</th>
                  <th className="px-2 py-2.5">AI employee</th>
                  <th className="px-2 py-2.5">Status</th>
                  <th className="w-44 px-2 py-2.5">Progress</th>
                  <th className="px-2 py-2.5 text-right">Cost per result</th>
                  <th className="w-40 px-2 py-2.5">Spent / budget</th>
                  <th className="px-2 py-2.5 text-right">Actions</th>
                  <th className="px-4 py-2.5">Last activity</th>
                </tr>
              </thead>
              {groups.map((grp) => (
              <tbody key={grp.id}>
                <tr className="border-b border-line bg-gray-50/80">
                  <td colSpan={9} className="px-4 py-1.5 text-[11.5px] font-bold uppercase tracking-wide text-gray-600">
                    {grp.name} <span className="font-semibold text-gray-400">· {grp.goals.length}</span>
                  </td>
                </tr>
                {grp.goals.map((c) => {
                  const on = c.status === "active";
                  const pct = c.budget.total ? (c.budget.spent / c.budget.total) * 100 : 0;
                  return (
                    <tr key={c.id} className="border-b border-line/70 align-top last:border-0 hover:bg-brand-50/30">
                      <td className="px-4 py-3">
                        <Toggle on={on} disabled={c.can_manage === false || ["completed", "out_of_budget"].includes(c.status) || busy === c.id} onChange={(v) => toggle(c, v)} label={`Turn ${c.name} ${on ? "off" : "on"}`} />
                      </td>
                      <td className="max-w-xs px-2 py-3">
                        <Link href={`/goals/${c.id}`} className="font-semibold text-ink hover:text-brand-600 hover:underline">{c.name}</Link>
                        <div className="mt-0.5 flex flex-wrap gap-1.5 text-xs text-muted">
                          {c.origin === "setup" && c.status === "draft" && <span className="rounded bg-brand-50 px-1.5 font-medium text-brand-700" title={c.suggested_reason}>Suggested</span>}
                          {c.client_name && <span className="rounded bg-violet-50 px-1.5 font-medium text-violet-700">{c.client_name}</span>}
                          {c.category && <span>{c.category}</span>}
                        </div>
                      </td>
                      <td className="px-2 py-3">
                        {c.agent ? (
                          <Link href={`/team/agents/${c.agent.id}`} className="flex items-center gap-2 hover:underline">
                            <AgentAvatar name={c.agent.name} size={24} />
                            <span className="min-w-0">
                              <span className="block truncate font-medium">{c.agent.name}</span>
                              {c.department && <span className="block truncate text-[11px] text-muted">{c.department.name}</span>}
                            </span>
                          </Link>
                        ) : <span className="text-muted">—</span>}
                      </td>
                      <td className="px-2 py-3"><GoalStatus c={c} /></td>
                      <td className="px-2 py-3"><GoalProgress c={c} /></td>
                      <td className="tabular px-2 py-3 text-right">{usd(c.cost_per_result)}</td>
                      <td className="px-2 py-3">
                        <div className="tabular text-[13px]">{usd(c.budget.spent)} <span className="text-muted">/ {usd(c.budget.total)}</span></div>
                        <ProgressBar pct={pct} tone="gray" className="mt-1" />
                        <div className="mt-0.5 text-[11px] text-muted">AI {usd(c.budget.ai_usage)}{c.daily_cap ? ` · ${usd(c.daily_cap)}/day cap` : ""}</div>
                      </td>
                      <td className="tabular px-2 py-3 text-right">{num(c.actions_taken)}</td>
                      <td className="max-w-[260px] px-4 py-3">
                        {c.last_activity ? (
                          <>
                            <div className="line-clamp-2 text-[12.5px]">{c.last_activity.title}</div>
                            <div className="text-[11px] text-muted">{timeAgo(c.last_activity.at)}</div>
                          </>
                        ) : <span className="text-muted">—</span>}
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
