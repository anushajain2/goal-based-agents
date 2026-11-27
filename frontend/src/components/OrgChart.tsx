"use client";

import { Hand, Mail, Plus, UserPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, Campaign, DepartmentInfo, OrgInfo, Person, usd } from "@/lib/api";
import { TargetLine } from "./Target";
import { LeadCard } from "./TeamLead";
import { PersonAvatar } from "./team";
import { Button, cx, Input, Select } from "./ui";

/**
 * Who works with whom: you at the top; for each team, its people, its Reviewer, and the goals
 * Oton is working on for it. Approvals for a team's goals go to one person.
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
        <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Team, e.g. Partnerships" onKeyDown={(e) => e.key === "Enter" && addDepartment()} />
        <div className="flex gap-2">
          <Button size="sm" variant="primary" onClick={addDepartment}>Add team</Button>
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
        </div>
      </div>
    ) : (
      <button onClick={() => setAdding(true)} className="flex h-24 w-full items-center justify-center gap-1.5 rounded-2xl border border-dashed border-stone-300 text-sm font-semibold text-muted transition hover:border-stone-400 hover:bg-white hover:text-ink">
        <Plus size={15} /> Add team
      </button>
    )
  );

  const cells = [
    ...org.departments.map((d, i) => <div key={d.id} className="org-child w-[250px] shrink-0">{columns[i]}</div>),
    ...(addColumn ? [<div key="add" className="org-child w-[250px] shrink-0">{addColumn}</div>] : []),
  ];
  const rows = Array.from({ length: Math.ceil(cells.length / 4) }, (_, r) => cells.slice(r * 4, r * 4 + 4));
  return (
    <div>
      {/* Wide screens: a tree. */}
      <div className="hidden overflow-x-auto pb-2 md:block">
        <div className="mx-auto w-max min-w-full px-2">
          <div className="flex justify-center">
            <PersonCard person={top} label={isMe ? `You · ${roleWord(top.role)}` : roleWord(top.role)} />
          </div>
          {/* Four departments per row, so bigger teams wrap instead of running off the screen. */}
          {rows.map((row, r) => (
            <div key={r} className={cx("org-children", r < rows.length - 1 && "org-trunk")}>
              {row}
            </div>
          ))}
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
    <div className="flex w-max items-center gap-3 rounded-2xl border border-line bg-white px-4 py-2.5 shadow-[var(--shadow-card)]">
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
  const canAdd = org.me.is_admin || org.me.department_ids.includes(d.id);
  const ids = new Set(d.agents.map((a) => a.id));
  const mine = (goals || []).filter((g) => g.agent && ids.has(g.agent.id));
  const live = mine.filter((g) => g.status !== "draft");
  const later = mine.filter((g) => g.status === "draft");
  const newGoal = d.agents[0] ? `/goals/new?agent=${d.agents[0].id}` : "/goals/new";

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
      <TeamCard d={d} org={org} onChanged={onChanged} />
      <div className="px-2.5 pt-2.5"><LeadCard d={d} org={org} onChanged={onChanged} /></div>
      <div className="space-y-1.5 p-2.5">
        <div className="px-1 pt-1 text-[12px] font-semibold text-stone-400">Goals</div>
        {goals && mine.length === 0 && <p className="px-1 text-[12px] text-muted">No goals yet.</p>}
        {live.length > 0 && <GoalChips goals={live} onGoalClick={onGoalClick} />}
        {later.length > 0 && (
          <div>
            {live.length > 0 && <div className="px-1 pb-0.5 pt-1 text-[12px] font-semibold text-stone-400">Not started</div>}
            <GoalChips goals={later} onGoalClick={onGoalClick} muted />
          </div>
        )}
        {canAdd && (
          <Link href={newGoal} className="flex w-full items-center justify-center gap-1 rounded-xl py-2 text-[12.5px] font-semibold text-muted transition hover:bg-stone-50 hover:text-ink">
            <Plus size={13} /> Add a goal
          </Link>
        )}
      </div>
    </div>
  );
}

/** The people on a team, and which of them approves its goals' work (one person, so nothing is random). */
function TeamCard({ d, org, onChanged }: { d: DepartmentInfo; org: OrgInfo; onChanged?: () => void }) {
  const admin = org.me.is_admin;
  const [adding, setAdding] = useState(false);
  const [pick, setPick] = useState("");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const owner = org.members.find((m) => m.role === "owner");
  const asks = d.head || owner;
  const invited = org.invitations.filter((i) => i.department_ids.includes(d.id));
  const others = org.members.filter((m) => !d.people.some((p) => p.id === m.id));
  const nameOf = (p: Person) => (p.id === org.me.id ? "You" : p.name || p.email);
  const people = d.people.length ? d.people : owner ? [owner] : [];

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      setAdding(false);
      setPick("");
      setEmail("");
      onChanged?.();
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  const addExisting = (id: string) => {
    const m = org.members.find((x) => x.id === id);
    return api(`/api/members/${id}`, { method: "PATCH", json: { department_ids: [...(m?.department_ids || []), d.id] } });
  };

  return (
    <div className="border-b border-line bg-stone-50/70">
      <div className="flex items-center justify-between px-3.5 pt-3">
        <span className="text-[14.5px] font-semibold">{d.name}</span>
        {admin && !adding && <button onClick={() => setAdding(true)} title="Add people to this team" className="grid h-7 w-7 place-items-center rounded-lg text-stone-500 hover:bg-white hover:text-ink"><UserPlus size={14} /></button>}
      </div>
      <div className="px-3.5 pb-2.5 pt-1.5">
        <div className="flex items-center gap-2">
          <span className="flex -space-x-2">
            {people.slice(0, 4).map((p) => <span key={p.id} className="rounded-full ring-2 ring-stone-50"><PersonAvatar name={p.name || p.email} size={24} /></span>)}
          </span>
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-stone-600" title={people.map(nameOf).join(", ")}>
            {people.length === 1 && people[0].id === org.me.id ? "Just you so far" : people.map(nameOf).join(", ")}
          </span>
        </div>
        {invited.length > 0 && <div className="mt-1 truncate text-[11px] text-muted">Invited: {invited.map((i) => i.email).join(", ")}</div>}
        {adding && (
          <div className="mt-2 space-y-1.5">
            {others.length > 0 && (
              <div className="flex gap-1.5">
                <Select className="h-8 py-1 text-xs" value={pick} onChange={(e) => setPick(e.target.value)}>
                  <option value="">Someone in {org.org.name}…</option>
                  {others.map((m) => <option key={m.id} value={m.id}>{m.name || m.email}</option>)}
                </Select>
                <Button size="sm" variant="primary" disabled={!pick} onClick={() => run(() => addExisting(pick))}>Add</Button>
              </div>
            )}
            <div className="flex gap-1.5">
              <Input className="h-8 py-1 text-xs" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Invite by email" />
              <Button size="sm" disabled={!email.includes("@")} onClick={() => run(() => api("/api/invitations", { method: "POST", json: { email, role: "member", department_ids: [d.id] } }))}>
                <Mail size={12} /> Invite
              </Button>
            </div>
            <button onClick={() => setAdding(false)} className="text-xs font-semibold text-muted hover:text-ink">Cancel</button>
          </div>
        )}
        {err && <p className="mt-1 text-xs text-red-600">{err}</p>}
      </div>
      {(people.length > 1 || (asks && asks.id !== org.me.id)) && <div className="flex items-center gap-1.5 px-3.5 pb-2.5 text-[11.5px] text-muted">
        <Hand size={11} className="shrink-0" />
        <span className="shrink-0">Approvals go to</span>
        {admin && people.length > 1 ? (
          <select className="min-w-0 flex-1 truncate rounded border-0 bg-transparent p-0 text-[11.5px] font-semibold text-ink focus:ring-0" value={asks?.id || ""}
            onChange={(e) => run(() => api(`/api/departments/${d.id}`, { method: "PATCH", json: { head_user_id: e.target.value || null } }))}>
            {people.map((p) => <option key={p.id} value={p.id}>{nameOf(p)}</option>)}
          </select>
        ) : (
          <b className="truncate text-ink">{asks ? nameOf(asks) : "the owner"}</b>
        )}
      </div>}
    </div>
  );
}

function GoalChips({ goals, onGoalClick, muted }: { goals: Campaign[]; onGoalClick?: (g: Campaign) => void; muted?: boolean }) {
  return (
    <ul className="space-y-1">
      {goals.map((g) => (
        <li key={g.id}>
          <button onClick={() => onGoalClick?.(g)} className={cx("flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] ring-1 ring-inset transition hover:ring-brand-200", muted ? "bg-white text-stone-500 ring-dashed ring-stone-200" : "bg-white ring-line")}>
            <span className={cx("mt-1 h-2 w-2 shrink-0 rounded-full", g.status === "active" ? (g.pending_requests ? "bg-signal-500" : "bg-emerald-500") : "bg-stone-300")} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-medium">{g.name}</span>
                <span className="shrink-0 text-[11px] text-muted">{g.status === "draft" ? usd(g.budget.total) : g.status === "active" ? (g.pending_requests ? "Needs you" : "Live") : "Paused"}</span>
              </span>
              {g.target?.target && <span className="mt-0.5 block"><TargetLine goal={g} compact /></span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
