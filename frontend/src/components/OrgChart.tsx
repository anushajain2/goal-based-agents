"use client";

import { Hand, Mail, Plus, UserPlus, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, Campaign, DepartmentInfo, OrgInfo, Person, usd } from "@/lib/api";
import { AgentAvatar, PersonAvatar } from "./team";
import { Button, cx, Input, Select } from "./ui";

/**
 * Who reports to whom: you at the top, a head for each department (a person), and the AI
 * employees in each department under its head. Approvals go to the people in the department.
 */
export function OrgChart({ org, goals, onGoalClick, onChanged }: {
  org: OrgInfo; goals?: Campaign[]; onGoalClick?: (g: Campaign) => void; onChanged?: () => void;
}) {
  const admin = org.me.is_admin;
  const top = org.me.role === "owner" ? org.me : org.members.find((m) => m.role === "owner") || org.me;
  const isMe = top.id === org.me.id;
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  async function addDepartment() {
    if (!name.trim()) return;
    await api("/api/departments", { method: "POST", json: { name } });
    setName("");
    setAdding(false);
    onChanged?.();
  }

  const columns = org.departments.map((d) => (
    <Department key={d.id} d={d} org={org} goals={goals} onGoalClick={onGoalClick} onChanged={onChanged} />
  ));
  const addColumn = admin && (
    adding ? (
      <div className="flex w-[250px] flex-col gap-2 rounded-xl border border-dashed border-line bg-white p-3">
        <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Department, e.g. Partnerships" onKeyDown={(e) => e.key === "Enter" && addDepartment()} />
        <div className="flex gap-2">
          <Button size="sm" variant="primary" onClick={addDepartment}>Add with an AI employee</Button>
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
        </div>
      </div>
    ) : (
      <button onClick={() => setAdding(true)} className="flex h-24 w-[200px] items-center justify-center gap-1.5 rounded-xl border border-dashed border-line text-sm font-semibold text-muted hover:border-gray-400 hover:text-ink">
        <Plus size={15} /> Add department
      </button>
    )
  );

  return (
    <div>
      {/* Wide screens: a tree. */}
      <div className="hidden overflow-x-auto pb-2 md:block">
        <div className="mx-auto w-max min-w-full px-2">
          <div className="flex justify-center">
            <PersonCard person={top} label={isMe ? `You · ${roleWord(top.role)}` : roleWord(top.role)} />
          </div>
          <div className="org-children">
            {org.departments.map((d, i) => <div key={d.id} className="org-child w-[260px] shrink-0">{columns[i]}</div>)}
            {addColumn && <div className="org-child shrink-0">{addColumn}</div>}
          </div>
        </div>
      </div>
      {/* Phones: the same thing as an indented list. */}
      <div className="space-y-3 md:hidden">
        <PersonCard person={top} label={isMe ? `You · ${roleWord(top.role)}` : roleWord(top.role)} />
        <div className="ml-4 space-y-3 border-l-2 border-[#c9ced6] pl-4">
          {columns}
          {addColumn}
        </div>
      </div>
    </div>
  );
}

const roleWord = (r: string) => (r === "owner" ? "Owner" : r === "admin" ? "Admin" : "Member");

function PersonCard({ person, label }: { person: Person; label: string }) {
  return (
    <div className="flex w-max items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-sm">
      <PersonAvatar name={person.name || person.email} size={36} />
      <div>
        <div className="text-sm font-bold">{person.name || person.email}</div>
        <div className="text-xs text-muted">{label}</div>
      </div>
    </div>
  );
}

function Department({ d, org, goals, onGoalClick, onChanged }: {
  d: DepartmentInfo; org: OrgInfo; goals?: Campaign[]; onGoalClick?: (g: Campaign) => void; onChanged?: () => void;
}) {
  const admin = org.me.is_admin;
  const [hiring, setHiring] = useState(false);
  const [agentName, setAgentName] = useState("");
  const approvers = d.people.length ? d.people.map((p) => (p.id === org.me.id ? "you" : p.name || p.email)) : ["admins"];

  async function hire() {
    await api("/api/agents", { method: "POST", json: { department_id: d.id, name: agentName, title: "" } });
    setHiring(false);
    setAgentName("");
    onChanged?.();
  }

  return (
    <div>
      <div className="rounded-xl border border-line bg-white shadow-sm">
        <div className="border-b border-line px-3 py-2 text-[12px] font-bold uppercase tracking-wide text-gray-600">{d.name}</div>
        <HeadSlot d={d} org={org} onChanged={onChanged} />
        <div className="flex items-center gap-1 border-t border-line px-3 py-1.5 text-[11.5px] text-muted">
          <Hand size={11} /> Approvals go to {approvers.join(", ")}
        </div>
      </div>
      <div className="org-stem" />
      <div className="space-y-2">
        {d.agents.map((a) => {
          const mine = (goals || []).filter((g) => g.agent?.id === a.id);
          return (
            <div key={a.id} className="rounded-xl border border-violet-200 bg-violet-50/40">
              <Link href={`/team/agents/${a.id}`} className="flex items-center gap-2.5 px-3 py-2.5 hover:bg-violet-50">
                <AgentAvatar name={a.name} size={32} state={a.working ? "working" : a.needs_you ? "waiting" : "idle"} />
                <span className="min-w-0">
                  <span className="block truncate text-[13.5px] font-semibold">{a.name}</span>
                  <span className="block truncate text-[11.5px] text-muted">AI employee{a.title ? ` · ${a.title}` : ""}</span>
                </span>
              </Link>
              {goals && (
                <ul className="space-y-1 border-t border-violet-100 px-2 py-2">
                  {mine.length === 0 && <li className="px-1 text-[11.5px] text-muted">No goals yet</li>}
                  {mine.map((g) => (
                    <li key={g.id}>
                      <button onClick={() => onGoalClick?.(g)} className="flex w-full items-center gap-2 rounded-md bg-white px-2 py-1.5 text-left text-[12px] ring-1 ring-line hover:ring-brand-500">
                        <span className={cx("h-2 w-2 shrink-0 rounded-full", g.status === "active" ? "bg-emerald-500" : g.pending_requests ? "bg-amber-500" : "bg-gray-300")} />
                        <span className="min-w-0 flex-1 truncate font-medium">{g.name}</span>
                        <span className="shrink-0 text-[11px] text-muted">{g.status === "draft" ? usd(g.budget.total) : g.status === "active" ? "Active" : "Paused"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
        {admin && (hiring ? (
          <div className="flex gap-1.5">
            <Input autoFocus className="h-8 py-1 text-xs" value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder={`${d.name} Agent 2`} onKeyDown={(e) => e.key === "Enter" && hire()} />
            <Button size="sm" variant="primary" onClick={hire}>Hire</Button>
            <button onClick={() => setHiring(false)} className="text-muted" aria-label="Cancel"><X size={14} /></button>
          </div>
        ) : (
          <button onClick={() => setHiring(true)} className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-line py-1.5 text-[12px] font-semibold text-muted hover:border-gray-400 hover:text-ink">
            <Plus size={12} /> Hire another AI employee
          </button>
        ))}
      </div>
    </div>
  );
}

function HeadSlot({ d, org, onChanged }: { d: DepartmentInfo; org: OrgInfo; onChanged?: () => void }) {
  const admin = org.me.is_admin;
  const [editing, setEditing] = useState(false);
  const [pick, setPick] = useState("");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const invited = org.invitations.find((i) => i.head_department_ids?.includes(d.id));

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      setEditing(false);
      setPick("");
      setEmail("");
      onChanged?.();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  if (editing) {
    return (
      <div className="space-y-2 px-3 py-2.5">
        <div className="text-[11.5px] font-semibold text-muted">Head of {d.name}</div>
        <div className="flex gap-1.5">
          <Select className="h-8 py-1 text-xs" value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Someone on the team…</option>
            {org.members.map((m) => <option key={m.id} value={m.id}>{m.id === org.me.id ? "Me" : m.name || m.email}</option>)}
          </Select>
          <Button size="sm" variant="primary" disabled={!pick} onClick={() => run(() => api(`/api/departments/${d.id}`, { method: "PATCH", json: { head_user_id: pick } }))}>Set</Button>
        </div>
        <div className="flex gap-1.5">
          <Input className="h-8 py-1 text-xs" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Or invite by email" />
          <Button size="sm" disabled={!email.includes("@")} onClick={() => run(() => api("/api/invitations", { method: "POST", json: { email, role: "member", head_of: [d.id] } }))}>
            <Mail size={12} /> Invite
          </Button>
        </div>
        {err && <p className="text-xs text-red-600">{err}</p>}
        <div className="flex gap-2">
          {d.head && <button onClick={() => run(() => api(`/api/departments/${d.id}`, { method: "PATCH", json: { head_user_id: null } }))} className="text-xs font-semibold text-muted hover:text-red-600">Remove head</button>}
          <button onClick={() => setEditing(false)} className="text-xs font-semibold text-muted hover:text-ink">Cancel</button>
        </div>
      </div>
    );
  }

  if (d.head) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <PersonAvatar name={d.head.name || d.head.email} size={32} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-semibold">{d.head.id === org.me.id ? "You" : d.head.name || d.head.email}</div>
          <div className="text-[11.5px] text-muted">Head of {d.name}</div>
        </div>
        {admin && <button onClick={() => setEditing(true)} className="text-xs font-semibold text-brand-600 hover:underline">Change</button>}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 px-3 py-2.5">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 border-dashed border-gray-300 text-gray-400"><UserPlus size={14} /></span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-gray-500" title={invited?.email}>{invited ? invited.email : "No head yet"}</div>
        <div className="text-[11.5px] text-muted">{invited ? "Invited to lead" : "Head of"} {d.name}</div>
      </div>
      {admin && <button onClick={() => setEditing(true)} className="text-xs font-semibold text-brand-600 hover:underline">{invited ? "Change" : "Add"}</button>}
    </div>
  );
}
