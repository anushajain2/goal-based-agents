"use client";

import { Bot, Check, Hand, PartyPopper, Pencil, Plus, Sparkles, Target, Trash2, UserPlus, Users, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { CompanyProfileCard } from "@/components/CompanyProfile";
import { GoalPanel } from "@/components/GoalPanel";
import { useRouter } from "next/navigation";
import { HireDialog, OrgChart } from "@/components/OrgChart";
import { TeamSize } from "@/components/TeamSize";
import { StartGoal } from "@/components/StartGoal";
import { AgentAvatar, PersonAvatar } from "@/components/team";
import { Badge, Button, Card, cx, ErrorNote, Input, PageHeader } from "@/components/ui";
import { api, Campaign, DepartmentInfo, OrgInfo, usd, useApi } from "@/lib/api";

export default function Page() {
  return (
    <Suspense>
      <TeamPage />
    </Suspense>
  );
}

function TeamPage() {
  const params = useSearchParams();
  const router = useRouter();
  const { data: org, reload, error } = useApi<OrgInfo>("/api/org");
  const { data: goals, reload: reloadGoals } = useApi<Campaign[]>("/api/campaigns");
  const [view, setView] = useState<"chart" | "list">("chart");
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [hiring, setHiring] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newDept, setNewDept] = useState("");
  const [err, setErr] = useState<string | null>(null);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!org) return <p className="text-muted">Loading…</p>;
  const admin = org.me.is_admin;
  const agents = org.departments.reduce((n, d) => n + d.agents.length, 0);

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      {params.get("welcome") && (
        <Card className="flex flex-wrap items-center gap-4 border-emerald-200 bg-emerald-50/60 p-5">
          <PartyPopper className="text-emerald-600" />
          <div className="min-w-0 flex-1">
            <div className="font-bold">{org.org.name} is set up, with {agents} AI employees.</div>
            <div className="text-sm text-stone-700">
              {org.org.profile
                ? "Next: review and start the suggested goals, and invite your team so approvals reach the right people."
                : "Next: invite your team so approvals reach the right people, then give your AI employees their first goals."}
            </div>
          </div>
          <Link href="/settings#people" className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-sm font-semibold hover:bg-stone-50"><UserPlus size={15} /> Invite people</Link>
          {org.org.profile ? (
            <Link href="/setup" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-semibold text-white hover:bg-brand-600"><Sparkles size={15} /> Review suggested goals</Link>
          ) : (
            <Link href="/goals/new" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-semibold text-white hover:bg-brand-600"><Target size={15} /> Give a goal</Link>
          )}
        </Card>
      )}

      <PageHeader
        title="Team"
        subtitle="Your people, AI employees, and an AI team lead per team that keeps suggesting what to do next."
        actions={admin && (
          <>
            <Link href="/settings#people" className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3.5 text-sm font-semibold shadow-[0_1px_2px_rgb(16_24_40/0.05)] hover:bg-stone-50"><UserPlus size={15} /> Invite</Link>
            <Button onClick={() => setAdding(true)}><Plus size={15} /> Team</Button>
            <Button variant="primary" onClick={() => setHiring(true)}><Bot size={15} /> Hire AI employee</Button>
          </>
        )}
      />

      {err && <ErrorNote>{err}</ErrorNote>}

      {params.get("basic") && (
        <Card className="border-signal-200 bg-signal-50/60 p-4 text-sm text-signal-900">
          We started you with the usual team for {org.org.profile?.pack_label ? `a company like yours (${org.org.profile.pack_label})` : "a company like yours"}. To have Autopilot research {org.org.name} and personalise it, add
          <code className="mx-1">ANTHROPIC_API_KEY</code> to the <code>.env</code> file, restart, then use <Link href="/setup" className="font-semibold underline">Research my company</Link>.
        </Card>
      )}

      {adding && (
        <Card className="flex flex-wrap items-center gap-2 p-4">
          <Input autoFocus className="max-w-sm" value={newDept} onChange={(e) => setNewDept(e.target.value)} placeholder="Department name, e.g. Client Delivery" />
          <Button variant="primary" disabled={!newDept.trim()} onClick={() => act(async () => { await api("/api/departments", { method: "POST", json: { name: newDept } }); setNewDept(""); setAdding(false); })}>
            <Check size={15} /> Create (with an AI employee)
          </Button>
          <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
        </Card>
      )}

      <TeamSize profile={org.org.profile} canAdd={org.me.is_admin} onAdding={() => router.push("/setup")} />

      <div className="inline-flex rounded-xl bg-stone-100 p-1 text-[13px] font-semibold">
        {(["chart", "list"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)} className={cx("rounded-lg px-3 py-1.5 transition", view === v ? "bg-white text-ink shadow-sm" : "text-stone-500 hover:text-ink")}>
            {v === "chart" ? "Org chart" : "Details"}
          </button>
        ))}
      </div>

      {view === "chart" ? (
        <div className="rounded-3xl border border-line bg-stone-50/60 bg-[radial-gradient(#e4e4e7_1px,transparent_1px)] p-6 [background-size:18px_18px]">
          <OrgChart org={org} goals={goals || []} onGoalClick={setPanel} onChanged={() => { reload(); reloadGoals(); }} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {org.departments.map((d) => (
            <DepartmentCard key={d.id} d={d} org={org} onChange={(fn) => act(fn)} />
          ))}
        </div>
      )}

      {org.org.profile ? (
        <CompanyProfileCard
          profile={org.org.profile}
          name={org.org.name}
          action={admin && <Link href="/setup" className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline"><Sparkles size={12} /> Research again</Link>}
        />
      ) : admin && (
        <Link href="/setup" className="flex items-center gap-3 rounded-xl border border-dashed border-brand-500/40 bg-brand-50/40 px-4 py-3 text-sm hover:bg-brand-50">
          <Sparkles size={16} className="text-brand-600" />
          <span className="flex-1"><b>Research {org.org.name}</b> and get suggested AI employees and goals that fit where you are.</span>
          <span className="font-semibold text-brand-600">Start →</span>
        </Link>
      )}

      {hiring && <HireDialog org={org} onClose={() => setHiring(false)} onHired={() => { setHiring(false); reload(); }} />}
      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); reloadGoals(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); reloadGoals(); reload(); }} />}
    </div>
  );
}

function DepartmentCard({ d, org, onChange }: { d: DepartmentInfo; org: OrgInfo; onChange: (fn: () => Promise<unknown>) => void }) {
  const admin = org.me.is_admin;
  const mine = org.me.department_ids.includes(d.id);
  const [hiring, setHiring] = useState(false);
  const [agentName, setAgentName] = useState("");
  const [agentTitle, setAgentTitle] = useState("");
  const [editingPeople, setEditingPeople] = useState(false);
  const [people, setPeople] = useState<string[]>(d.people.map((p) => p.id));
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(d.name);
  const spent = d.agents.reduce((t, a) => t + a.spent, 0);
  const waiting = d.agents.reduce((t, a) => t + a.needs_you, 0);

  return (
    <Card className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        {renaming ? (
          <>
            <Input className="h-8 max-w-[220px] py-1" value={name} onChange={(e) => setName(e.target.value)} />
            <Button size="sm" variant="primary" onClick={() => { onChange(() => api(`/api/departments/${d.id}`, { method: "PATCH", json: { name } })); setRenaming(false); }}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}><X size={13} /></Button>
          </>
        ) : (
          <h2 className="text-[16px] font-bold">{d.name}</h2>
        )}
        {mine && <Badge tone="blue">You&apos;re in this team</Badge>}
        {waiting > 0 && <Badge tone="amber"><Hand size={11} /> {waiting} waiting</Badge>}
        <span className="tabular ml-auto text-xs text-muted">{usd(spent)} spent</span>
        {admin && !renaming && (
          <span className="flex gap-1">
            <button title="Rename" onClick={() => setRenaming(true)} className="rounded p-1 text-muted hover:bg-stone-100"><Pencil size={13} /></button>
            <button title="Delete department" onClick={() => confirm(`Delete ${d.name}? Its AI employees must have no goals.`) && onChange(() => api(`/api/departments/${d.id}`, { method: "DELETE" }))} className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"><Trash2 size={13} /></button>
          </span>
        )}
      </div>

      <div className="flex-1 space-y-2 p-3">
        <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted">AI employees</div>
        {d.agents.length === 0 && <p className="px-1 text-sm text-muted">No AI employees yet.</p>}
        {d.agents.map((a) => (
          <Link key={a.id} href={`/team/agents/${a.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-stone-50">
            <AgentAvatar name={a.name} state={a.working ? "working" : a.needs_you ? "waiting" : "idle"} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-semibold">{a.name}</span>
              <span className="block truncate text-xs text-muted">
                {a.working ? <span className="font-semibold text-emerald-700">Working now</span> : a.needs_you ? <span className="font-semibold text-signal-700">Needs a yes</span> : a.active_goals ? "Between work sessions" : "No active goals"}
                {" · "}{a.goals} {a.goals === 1 ? "goal" : "goals"}{a.title ? ` · ${a.title}` : ""}
              </span>
            </span>
            <span className="tabular text-xs text-muted">{usd(a.spent)}</span>
          </Link>
        ))}
        {hiring ? (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            <Input className="h-8 min-w-36 flex-1 py-1" placeholder={`Name, e.g. ${d.name} Agent 2`} value={agentName} onChange={(e) => setAgentName(e.target.value)} />
            <Input className="h-8 min-w-36 flex-1 py-1" placeholder="Focus (optional), e.g. Outbound" value={agentTitle} onChange={(e) => setAgentTitle(e.target.value)} />
            <Button size="sm" variant="primary" onClick={() => { onChange(() => api("/api/agents", { method: "POST", json: { department_id: d.id, name: agentName, title: agentTitle } })); setHiring(false); setAgentName(""); setAgentTitle(""); }}>Hire</Button>
            <Button size="sm" variant="ghost" onClick={() => setHiring(false)}>Cancel</Button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {(admin || mine) && d.agents.length > 0 && (
              <Link href={`/goals/new?agent=${d.agents[0].id}`} className="inline-flex h-7 items-center gap-1 rounded-md border border-line px-2.5 text-xs font-semibold hover:bg-stone-50"><Target size={12} /> Give a goal</Link>
            )}
            {admin && <Button size="sm" variant="ghost" onClick={() => setHiring(true)}><Plus size={12} /> Hire another AI employee</Button>}
          </div>
        )}
      </div>

      <div className="border-t border-line px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted"><Users size={12} /> People · approve this team&apos;s work</span>
          {admin && !editingPeople && <button onClick={() => setEditingPeople(true)} className="text-xs font-semibold text-brand-600 hover:underline">Edit</button>}
        </div>
        {editingPeople ? (
          <div className="space-y-1.5">
            {org.members.map((m) => (
              <label key={m.id} className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-brand-500" checked={people.includes(m.id)} onChange={(e) => setPeople(e.target.checked ? [...people, m.id] : people.filter((x) => x !== m.id))} />
                {m.name || m.email} <span className="text-xs text-muted">{m.name ? m.email : ""}</span>
              </label>
            ))}
            <div className="flex gap-2 pt-1">
              <Button size="sm" variant="primary" onClick={() => { onChange(() => api(`/api/departments/${d.id}/people`, { method: "PUT", json: { user_ids: people } })); setEditingPeople(false); }}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => setEditingPeople(false)}>Cancel</Button>
            </div>
          </div>
        ) : d.people.length ? (
          <div className="flex flex-wrap items-center gap-2">
            {d.people.map((p) => (
              <span key={p.id} className="inline-flex items-center gap-1.5 rounded-full bg-stone-50 py-0.5 pl-0.5 pr-2.5 text-xs">
                <PersonAvatar name={p.name || p.email} size={22} title={p.email} /> {p.name || p.email}
              </span>
            ))}
          </div>
        ) : (
          <p className={cx("text-xs", "text-signal-700")}>Nobody yet, so this team&apos;s approvals go to admins.</p>
        )}
      </div>
    </Card>
  );
}
