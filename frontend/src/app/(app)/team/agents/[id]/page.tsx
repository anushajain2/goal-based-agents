"use client";

import { ArrowLeft, ArrowRight, FileText, Hand, Pencil, Target } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { GoalProgress, GoalStatus } from "@/components/goal";
import { AgentAvatar, PersonAvatar } from "@/components/team";
import { Button, Card, CardHeader, cx, Empty, ErrorNote, Input, Select } from "@/components/ui";
import { ViewToggle, WorkLog } from "@/components/WorkLog";
import { ActivityItem, api, Campaign, Deliverable, num, OrgInfo, Person, usd, useApi } from "@/lib/api";

type AgentInfo = {
  id: string; name: string; title: string; objective: string; reports_to_user_id: string | null;
  handoff_to_agent_id: string | null; handoff_review: boolean;
  department: { id: string; name: string }; approvers: Person[]; can_manage: boolean; can_edit: boolean; goals: number; actions: number;
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
            <span className="flex items-center gap-1 text-muted"><Hand size={14} /> Reports to</span>
            {agent.approvers.map((p) => (
              <span key={p.id} className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 py-0.5 pl-0.5 pr-2.5 text-xs"><PersonAvatar name={p.name || p.email} size={20} title={p.email} /> {p.id === org?.me.id ? "You" : p.name || p.email}</span>
            ))}
            {agent.can_edit && org && (
              <select
                aria-label="Change who it reports to"
                className="rounded-md border border-line bg-white px-2 py-0.5 text-xs text-muted"
                value={agent.reports_to_user_id || ""}
                onChange={async (e) => { await api(`/api/agents/${id}`, { method: "PATCH", json: { reports_to_user_id: e.target.value || null } }); reload(); }}
              >
                <option value="">Change: head of {agent.department.name} (default)</option>
                {org.members.map((m) => <option key={m.id} value={m.id}>{m.id === org.me.id ? "Me" : m.name || m.email}</option>)}
              </select>
            )}
            <span className="text-xs text-muted">· its approvals and questions go here</span>
          </div>
        </div>
        {agent.can_manage && (
          <Link href={`/goals/new?agent=${agent.id}`} className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600"><Target size={16} /> Give {agent.name.split(" ")[0]} a goal</Link>
        )}
      </Card>
      {err && <ErrorNote>{err}</ErrorNote>}

      <Okrs agent={agent} goals={goals || []} onSaved={reload} />
      {org && <HandOffs agent={agent} org={org} onSaved={reload} />}
      <Documents agentId={agent.id} />

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


/** Like an employee's OKRs: one objective, and the key results of its goals. */
function Okrs({ agent, goals, onSaved }: { agent: AgentInfo; goals: Campaign[]; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(agent.objective);
  const live = goals.filter((g) => g.status !== "draft");
  const later = goals.filter((g) => g.status === "draft");
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-[11px] font-bold uppercase tracking-wide text-violet-700">Objective</div>
        {agent.can_edit && !editing && <button onClick={() => { setText(agent.objective); setEditing(true); }} className="text-xs font-semibold text-brand-600 hover:underline">{agent.objective ? "Edit" : "Add an objective"}</button>}
      </div>
      {editing ? (
        <div className="mt-1 flex flex-wrap gap-2">
          <Input className="min-w-60 flex-1" value={text} onChange={(e) => setText(e.target.value)} placeholder="What is it here to achieve?" />
          <Button variant="primary" onClick={async () => { await api(`/api/agents/${agent.id}`, { method: "PATCH", json: { objective: text } }); setEditing(false); onSaved(); }}>Save</Button>
          <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      ) : (
        <p className="mt-1 text-[16px] font-semibold leading-snug">{agent.objective || <span className="font-normal text-muted">No objective yet.</span>}</p>
      )}
      <div className="mt-4 text-[11px] font-bold uppercase tracking-wide text-muted">Key results</div>
      {live.length === 0 && <p className="mt-1 text-sm text-muted">Nothing live yet. {later.length ? `${later.length} goal${later.length > 1 ? "s" : ""} ready to start below.` : ""}</p>}
      <ul className="mt-2 space-y-3">
        {live.map((g) => (
          <li key={g.id}>
            <Link href={`/goals/${g.id}`} className="text-[13px] font-semibold hover:text-brand-600 hover:underline">{g.name}</Link>
            <ul className="mt-1 space-y-1">
              {(g.key_results?.length ? g.key_results : [g.primary_metric]).map((kr, i) => (
                <li key={i} className="flex items-center gap-2 text-[13px]">
                  <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", i === 0 ? "bg-emerald-500" : "bg-gray-300")} />
                  <span className="min-w-0 flex-1">{kr}</span>
                  {i === 0 && <span className="w-40 shrink-0"><GoalProgress c={g} compact /></span>}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  );
}


/** Where its finished work goes: to the person it reports to, and on to another AI employee. */
function HandOffs({ agent, org, onSaved }: { agent: AgentInfo; org: OrgInfo; onSaved: () => void }) {
  const others = org.departments.flatMap((d) => d.agents.map((a) => ({ ...a, dept: d.name }))).filter((a) => a.id !== agent.id);
  const manager = agent.approvers[0];
  const who = manager ? (manager.id === org.me.id ? "you" : manager.name || manager.email) : "the owner";
  const [err, setErr] = useState<string | null>(null);
  async function patch(json: Record<string, unknown>) {
    setErr(null);
    try {
      await api(`/api/agents/${agent.id}`, { method: "PATCH", json });
      onSaved();
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  return (
    <Card className="p-5">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Where its work goes</div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded-full bg-violet-50 px-3 py-1 font-semibold text-violet-800">{agent.name}</span>
        <ArrowRight size={15} className="text-muted" />
        {agent.handoff_review || !agent.handoff_to_agent_id ? (
          <>
            <span className="rounded-full bg-amber-50 px-3 py-1 font-semibold text-amber-800">{who === "you" ? "You review" : `${who} reviews`}</span>
            {agent.handoff_to_agent_id && <ArrowRight size={15} className="text-muted" />}
          </>
        ) : null}
        {agent.handoff_to_agent_id && (
          <span className="rounded-full bg-brand-50 px-3 py-1 font-semibold text-brand-700">{others.find((a) => a.id === agent.handoff_to_agent_id)?.name} builds it</span>
        )}
      </div>
      {agent.can_edit && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1.5">PRDs go on to
            <select className="rounded-md border border-line bg-white px-2 py-1 font-semibold" value={agent.handoff_to_agent_id || ""}
              onChange={(e) => patch({ handoff_to_agent_id: e.target.value || null })}>
              <option value="">nobody (just {who})</option>
              {others.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.dept})</option>)}
            </select>
          </label>
          {agent.handoff_to_agent_id && (
            <label className="flex items-center gap-1.5">
              <input type="checkbox" className="h-3.5 w-3.5 accent-brand-500" checked={agent.handoff_review} onChange={(e) => patch({ handoff_review: e.target.checked })} />
              {who === "you" ? "You approve first" : `${who} approves first`}
            </label>
          )}
        </div>
      )}
      {err && <p className="mt-2 text-xs text-red-600">{err}</p>}
    </Card>
  );
}

const DOC_STATUS: Record<Deliverable["status"], { label: string; tone: string }> = {
  submitted: { label: "Waiting for review", tone: "bg-amber-50 text-amber-800" },
  approved: { label: "Approved", tone: "bg-emerald-50 text-emerald-800" },
  changes_requested: { label: "Changes asked", tone: "bg-gray-100 text-gray-600" },
  handed_off: { label: "Being built", tone: "bg-brand-50 text-brand-700" },
};

/** PRDs, analyses and reports it handed in. */
function Documents({ agentId }: { agentId: string }) {
  const { data } = useApi<Deliverable[]>(`/api/deliverables?agent_id=${agentId}`);
  const [open, setOpen] = useState<string | null>(null);
  if (!data || data.length === 0) return null;
  return (
    <Card>
      <CardHeader title="Documents" subtitle="PRDs, analyses and reports it handed in" />
      <ul className="divide-y divide-line">
        {data.map((d) => (
          <li key={d.id}>
            <button onClick={() => setOpen(open === d.id ? null : d.id)} className="flex w-full flex-wrap items-center gap-2 px-4 py-3 text-left hover:bg-gray-50">
              <FileText size={15} className="text-muted" />
              <span className="text-[11px] font-bold uppercase text-muted">{d.kind === "prd" ? "PRD" : d.kind}</span>
              <span className="min-w-0 flex-1 truncate text-sm font-semibold">{d.title}</span>
              <span className={cx("rounded-full px-2 py-0.5 text-[11px] font-semibold", DOC_STATUS[d.status].tone)}>{DOC_STATUS[d.status].label}</span>
              {d.handed_to_campaign_id && <Link href={`/goals/${d.handed_to_campaign_id}`} onClick={(e) => e.stopPropagation()} className="text-xs font-semibold text-brand-600 hover:underline">See the build</Link>}
            </button>
            {open === d.id && (
              <div className="border-t border-line bg-gray-50 px-4 py-3">
                {d.summary && <p className="mb-2 text-sm font-medium">{d.summary}</p>}
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-gray-800">{d.content}</pre>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
