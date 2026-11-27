"use client";

import { useState } from "react";

import { Card, cx, ErrorNote, PageHeader } from "@/components/ui";
import { useApi } from "@/lib/api";

type TaskCost = {
  task: string; label: string; slot: string; model: string; effort: string; served_by: string | null;
  calls: number; cost_usd: number; avg_usd: number; share: number;
  input_tokens: number; output_tokens: number; cache_read_tokens: number; web_searches: number;
};
type Costs = {
  days: number; total_usd: number; calls: number; tasks: TaskCost[];
  orgs: { org_id: string | null; name: string; calls: number; cost_usd: number }[];
};

const money = (v: number) => (v >= 100 ? `$${v.toFixed(0)}` : v >= 1 ? `$${v.toFixed(2)}` : v >= 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(4)}`);
const tokens = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : `${v}`);

/** For the people who run this Oton: what each kind of model call costs, and which model runs it. */
export default function CostsPage() {
  const [days, setDays] = useState(30);
  const { data, error } = useApi<Costs>(`/api/ops/costs?days=${days}`, { live: false });
  return (
    <div className="space-y-5">
      <PageHeader
        title="AI cost by task"
        subtitle="Every model call, by what it was for, across all organizations. Change a task's model with TASK_MODELS and TASK_EFFORTS."
        actions={
          <div className="inline-flex rounded-xl bg-stone-100 p-1 text-[13px] font-semibold">
            {[7, 30, 90].map((d) => (
              <button key={d} onClick={() => setDays(d)} className={cx("rounded-lg px-3 py-1.5", days === d ? "bg-white shadow-sm" : "text-stone-500 hover:text-ink")}>
                {d} days
              </button>
            ))}
          </div>
        }
      />
      {error && <ErrorNote>{/operator|403/i.test(error) ? "Only the people who run this Oton (OPERATOR_EMAILS) can see this." : error}</ErrorNote>}
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label={`Spent, last ${data.days} days`} value={money(data.total_usd)} />
            <Stat label="Model calls" value={data.calls.toLocaleString()} />
            <Stat label="Average per call" value={data.calls ? money(data.total_usd / data.calls) : "—"} />
          </div>
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11.5px] text-muted">
                  <th className="px-4 py-2.5 font-semibold">Task</th>
                  <th className="px-3 py-2.5 font-semibold">Model now</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Calls</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Cost</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Per call</th>
                  <th className="px-3 py-2.5 font-semibold">Share</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Tokens in / out / cached</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((t) => (
                  <tr key={t.task} className={cx("border-b border-line/70 last:border-0", !t.calls && "text-stone-400")}>
                    <td className="px-4 py-2.5">
                      <div className={cx("font-semibold", t.calls > 0 && "text-ink")}>{t.label}</div>
                      <div className="font-mono text-[11px] text-muted">{t.task}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-mono text-[12px]">{t.model}</div>
                      <div className="text-[11px] text-muted">
                        {t.effort} effort · {t.slot} slot{t.served_by && t.served_by !== t.model ? ` · ran on ${t.served_by}` : ""}
                      </div>
                    </td>
                    <td className="tabular px-3 py-2.5 text-right">{t.calls.toLocaleString()}</td>
                    <td className="tabular px-3 py-2.5 text-right font-semibold">{t.calls ? money(t.cost_usd) : "—"}</td>
                    <td className="tabular px-3 py-2.5 text-right">{t.calls ? money(t.avg_usd) : "—"}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-stone-100">
                          <div className="h-full rounded-full bg-brand-600" style={{ width: `${Math.round(t.share * 100)}%` }} />
                        </div>
                        <span className="tabular w-9 text-right text-[12px]">{Math.round(t.share * 100)}%</span>
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-[12px] text-muted">
                      {t.calls ? `${tokens(t.input_tokens)} / ${tokens(t.output_tokens)} / ${tokens(t.cache_read_tokens)}` : ""}
                      {t.web_searches ? <div>{t.web_searches} web searches</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {data.orgs.length > 0 && (
            <Card className="p-4">
              <div className="mb-2 text-[12px] font-semibold text-muted">Top organizations</div>
              <ul className="divide-y divide-line text-[13px]">
                {data.orgs.map((o) => (
                  <li key={o.org_id || "none"} className="flex items-center justify-between py-2">
                    <span className="font-medium">{o.name}</span>
                    <span className="tabular text-muted">{o.calls.toLocaleString()} calls · <b className="text-ink">{money(o.cost_usd)}</b></span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="text-[12px] font-semibold text-muted">{label}</div>
      <div className="tabular mt-1 text-[24px] font-bold tracking-tight">{value}</div>
    </Card>
  );
}
