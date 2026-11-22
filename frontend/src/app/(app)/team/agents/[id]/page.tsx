"use client";

import { ArrowLeft, Hand, Pencil, Target } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { GoalProgress, GoalStatus } from "@/components/goal";
import { AgentAvatar, PersonAvatar } from "@/components/team";
import { Button, Card, CardHeader, Empty, ErrorNote, Input, Select } from "@/components/ui";
import { ViewToggle, WorkLog } from "@/components/WorkLog";
import { ActivityItem, api, Campaign, num, OrgInfo, Person, usd, useApi } from "@/lib/api";

type AgentInfo = {
  id: string; name: string; title: string; department: { id: string; name: string };
  approvers: Person[]; can_manage: boolean; goals: number; actions: number;
};

export default function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const { data: agent, error, reload } = useApi<AgentInfo>(`/api/agents/${id}`);
  const { data: org } = useApi<OrgInfo>("/api/org");
  const { data: goals } = useApi<Campaign[]>(`/api/campaigns?agent_id=${id}`);
  const { data: log } = useApi<ActivityItem[]>(`/api/activity?agent_id=${id}&limit=150`);
  const [view, setView] = useState<"highlights" | "everything">("highlights");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", title: "", department_id: "" });
  const [err, setErr] = useState<string | null>(null);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!agent) return <p className="text-muted">Loading…</p>;
  const spent = (goals || []).reduce((t, g) => t + g.budget.spent, 0);
  const working = (goals || []).some((g) => g.status === "active" && g.current_run && ["queued", "running"].includes(g.current_run.status));
  const waiting = (goals || []).reduce((t, g) => t + g.pending_requests, 0);

  async function save() {
    setErr(null);
    try {
      await api(`/api/agents/${id}`, { method: "PATCH", json: form });
      setEditing(false);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <Link href="/team" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft size={15} /> Team</Link>

      <Card className="flex flex-wrap items-center gap-4 p-5">
        <AgentAvatar name={agent.name} size={56} state={working ? "working" : waiting ? "waiting" : "idle"} />
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex flex-wrap gap-2">
              <Input className="max-w-[220px]" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" />
              <Input className="max-w-[220px]" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Focus, e.g. Outbound" />
              <div className="w-48">
                <Select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                  {(org?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </div>
              <Button variant="primary" onClick={save}>Save</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-bold">{agent.name}</h1>
                {org?.me.is_admin && (
                  <button onClick={() => { setForm({ name: agent.name, title: agent.title, department_id: agent.department.id }); setEditing(true); }} className="rounded p-1 text-muted hover:bg-gray-100" title="Edit"><Pencil size={14} /></button>
                )}
              </div>
              <p className="text-sm text-muted">AI employee · {agent.department.name}{agent.title ? ` · ${agent.title}` : ""}</p>
            </>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="flex items-center gap-1 text-muted"><Hand size={14} /> Asks for approval from:</span>
            {agent.approvers.map((p) => (
              <span key={p.id} className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 py-0.5 pl-0.5 pr-2.5 text-xs"><PersonAvatar name={p.name || p.email} size={20} title={p.email} /> {p.name || p.email}</span>
            ))}
          </div>
        </div>
        {agent.can_manage && (
          <Link href={`/goals/new?agent=${agent.id}`} className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600"><Target size={16} /> Give {agent.name.split(" ")[0]} a goal</Link>
        )}
      </Card>
      {err && <ErrorNote>{err}</ErrorNote>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Status" value={working ? "Working" : waiting ? "Needs a yes" : "Idle"} />
        <Stat label="Goals" value={`${agent.goals}`} />
        <Stat label="Actions taken" value={num(agent.actions)} />
        <Stat label="Spent" value={usd(spent)} />
      </div>

      <Card>
        <CardHeader title="Goals" subtitle={`What ${agent.name} is working toward`} />
        {goals && goals.length === 0 ? (
          <Empty icon={<Target size={30} />} title="No goals yet">
            {agent.can_manage ? <Link href={`/goals/new?agent=${agent.id}`} className="font-semibold text-brand-600">Give it its first goal →</Link> : "Someone in this department can give it one."}
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {(goals || []).map((g) => (
              <li key={g.id}>
                <Link href={`/goals/${g.id}`} className="grid grid-cols-1 items-center gap-3 px-4 py-3 hover:bg-gray-50 sm:grid-cols-[1fr_180px_140px_auto]">
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">{g.name}</span>
                    {g.client_name && <span className="text-xs text-muted">for {g.client_name}</span>}
                  </span>
                  <GoalProgress c={g} compact />
                  <span className="tabular text-xs text-muted">{usd(g.budget.spent)} / {usd(g.budget.total)}</span>
                  <GoalStatus c={g} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="Work log" subtitle={`Everything ${agent.name} has done, across its goals`} action={<ViewToggle value={view} onChange={setView} />} />
        <div className="p-3"><WorkLog items={log || []} showGoal view={view} /></div>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="tabular mt-1 text-xl font-bold">{value}</div>
    </Card>
  );
}
