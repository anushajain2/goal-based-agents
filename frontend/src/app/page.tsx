"use client";

import { Plus, Rocket } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CampaignStatus, Card, Empty, ErrorNote, Toggle } from "@/components/ui";
import { api, Campaign, num, timeAgo, usd, useApi } from "@/lib/api";

export default function CampaignsPage() {
  const { data, error, reload } = useApi<Campaign[]>("/api/campaigns");
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(c: Campaign, on: boolean) {
    setBusy(c.id);
    try {
      const action = on ? (c.status === "draft" ? "launch" : "resume") : "pause";
      await api(`/api/campaigns/${c.id}/${action}`, { method: "POST" });
      await reload();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const totals = (data || []).reduce(
    (t, c) => ({ spent: t.spent + c.budget.spent, budget: t.budget + c.budget.total, pending: t.pending + c.pending_requests }),
    { spent: 0, budget: 0, pending: 0 },
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Campaigns</h1>
          <p className="text-sm text-muted">Set a goal and a budget. The agent works toward it and checks with you on what matters.</p>
        </div>
        <Link
          href="/campaigns/new"
          className="inline-flex h-9 items-center gap-1.5 rounded-md bg-emerald-600 px-3.5 text-sm font-semibold text-white hover:bg-emerald-700"
        >
          <Plus size={16} /> Create
        </Link>
      </div>

      {error && <ErrorNote>Can&apos;t reach the backend ({error}). Is it running on port 8000?</ErrorNote>}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-6 border-b border-line bg-gray-50/60 px-4 py-2.5 text-xs text-muted">
          <span>
            <b className="text-ink tabular">{data?.length ?? 0}</b> campaigns
          </span>
          <span>
            Spent <b className="text-ink tabular">{usd(totals.spent)}</b> of {usd(totals.budget)}
          </span>
          {totals.pending > 0 && (
            <Link href="/approvals" className="font-semibold text-red-600">
              {totals.pending} waiting for your approval
            </Link>
          )}
        </div>
        {data && data.length === 0 ? (
          <Empty icon={<Rocket size={36} />} title="No campaigns yet">
            Create one: pick a goal like &quot;grow my followers on X&quot;, set a budget, and choose what the agent may do on its own.
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-left text-[13px]">
              <thead className="border-b border-line text-xs font-semibold text-muted">
                <tr>
                  <th className="w-14 px-4 py-2.5">On/Off</th>
                  <th className="px-2 py-2.5">Campaign</th>
                  <th className="px-2 py-2.5">Status</th>
                  <th className="px-2 py-2.5 text-right">Results</th>
                  <th className="px-2 py-2.5 text-right">Cost per result</th>
                  <th className="px-2 py-2.5 text-right">Amount spent</th>
                  <th className="px-2 py-2.5 text-right">Budget</th>
                  <th className="px-2 py-2.5 text-right">Approvals</th>
                  <th className="px-4 py-2.5 text-right">Next check-in</th>
                </tr>
              </thead>
              <tbody>
                {(data || []).map((c) => {
                  const on = c.status === "active";
                  const canToggle = c.status !== "completed" && c.status !== "out_of_budget";
                  const r = c.results.results;
                  return (
                    <tr key={c.id} className="border-b border-line/70 last:border-0 hover:bg-brand-50/40">
                      <td className="px-4 py-3">
                        <Toggle on={on} disabled={!canToggle || busy === c.id} onChange={(v) => toggle(c, v)} label={`Turn ${c.name} ${on ? "off" : "on"}`} />
                      </td>
                      <td className="px-2 py-3">
                        <Link href={`/campaigns/${c.id}`} className="font-semibold text-brand-600 hover:underline">
                          {c.name}
                        </Link>
                        <div className="max-w-xs truncate text-xs text-muted">{c.goal_description}</div>
                      </td>
                      <td className="px-2 py-3">
                        <CampaignStatus status={c.status} />
                        {c.current_run && ["running", "queued"].includes(c.current_run.status) && on && (
                          <div className="text-xs text-brand-600">Working · cycle {c.current_run.cycle_number}</div>
                        )}
                        {c.current_run?.status === "waiting" && <div className="text-xs text-amber-700">Waiting on you</div>}
                      </td>
                      <td className="px-2 py-3 text-right tabular">
                        <div className="font-semibold">{r === null ? "—" : `${r >= 0 ? "+" : ""}${num(r)}`}</div>
                        <div className="text-xs text-muted">{c.primary_metric}</div>
                      </td>
                      <td className="px-2 py-3 text-right tabular">{usd(c.cost_per_result)}</td>
                      <td className="px-2 py-3 text-right tabular">
                        <div>{usd(c.budget.spent)}</div>
                        <div className="text-xs text-muted">AI {usd(c.budget.ai_usage)}</div>
                      </td>
                      <td className="px-2 py-3 text-right tabular">
                        <div>{usd(c.budget.total)}</div>
                        <div className="text-xs text-muted">{c.daily_cap ? `${usd(c.daily_cap)}/day` : "Lifetime"}</div>
                      </td>
                      <td className="px-2 py-3 text-right">
                        {c.pending_requests > 0 ? (
                          <Link href={`/campaigns/${c.id}?tab=approvals`} className="font-semibold text-red-600">
                            {c.pending_requests} pending
                          </Link>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-muted">{on ? timeAgo(c.next_cycle_at) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
