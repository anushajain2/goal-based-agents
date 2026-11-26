"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Card, cx, Input, Select, PageHeader } from "@/components/ui";
import { ViewToggle, WorkLog } from "@/components/WorkLog";
import { ActivityItem, Campaign, usd, useApi } from "@/lib/api";

const TYPES: { key: string; label: string; kinds: string }[] = [
  { key: "all", label: "Everything", kinds: "" },
  { key: "actions", label: "Actions", kinds: "action" },
  { key: "asked", label: "Asked you", kinds: "request,decision" },
  { key: "blocked", label: "Blocked", kinds: "blocked" },
  { key: "plans", label: "Plans & strategy", kinds: "plan,strategy,note" },
  { key: "results", label: "Measurements", kinds: "metric" },
  { key: "problems", label: "Problems", kinds: "error,budget" },
];

export default function WorkPage() {
  const { data: goals } = useApi<Campaign[]>("/api/campaigns");
  const [goal, setGoal] = useState("");
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [view, setView] = useState<"highlights" | "everything">("highlights");
  const kinds = TYPES.find((t) => t.key === type)?.kinds || "";
  const path = `/api/activity?limit=400${goal ? `&campaign_id=${goal}` : ""}${kinds ? `&kinds=${kinds}` : ""}${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`;
  const { data } = useApi<ActivityItem[]>(path);

  const byDay = useMemo(() => {
    const out: { day: string; items: ActivityItem[]; cost: number }[] = [];
    for (const a of data || []) {
      const day = new Date(a.created_at).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
      const last = out[out.length - 1];
      if (last?.day === day) {
        last.items.push(a);
        last.cost += a.cost_usd || 0;
      } else out.push({ day, items: [a], cost: a.cost_usd || 0 });
    }
    return out;
  }, [data]);

  return (
    <div className="space-y-4">
      <PageHeader title="Work log" subtitle="Everything Oton did, decided and asked." />

      <Card className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="w-full sm:w-64">
          <Select className="h-9 py-1.5" value={goal} onChange={(e) => setGoal(e.target.value)}>
            <option value="">All goals</option>
            {(goals || []).map((g) => <option key={g.id} value={g.id}>{g.client_name ? `${g.client_name}: ` : ""}{g.name}</option>)}
          </Select>
        </div>
        <div className="relative min-w-48 flex-1">
          <Search size={15} className="absolute left-3 top-2.5 text-muted" />
          <Input className="h-9 pl-9" placeholder="Search the log" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <ViewToggle value={view} onChange={setView} />
        <div className="flex w-full flex-wrap gap-1.5">
          {TYPES.map((t) => (
            <button key={t.key} onClick={() => setType(t.key)} className={cx("rounded-full border px-3 py-1 text-xs font-semibold", type === t.key ? "border-ink bg-ink text-white" : "border-line text-muted hover:text-ink")}>
              {t.label}
            </button>
          ))}
        </div>
      </Card>

      {byDay.length === 0 && <Card><p className="px-4 py-12 text-center text-sm text-muted">Nothing matches. Activity shows up here as Oton works.</p></Card>}
      {byDay.map((d) => (
        <Card key={d.day}>
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h2 className="text-[13px] font-bold">{d.day}</h2>
            {d.cost > 0 && <span className="tabular text-xs text-muted">AI cost logged: {usd(d.cost)}</span>}
          </div>
          <div className="p-2">
            <WorkLog items={d.items} showGoal={!goal} view={type === "all" ? view : "everything"} />
          </div>
        </Card>
      ))}
    </div>
  );
}
