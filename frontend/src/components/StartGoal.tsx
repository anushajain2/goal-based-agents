"use client";

import { ArrowLeft, ArrowRight, Check, ChevronDown, Database, ExternalLink, GitBranch, Globe, Hand, Loader2, Lock, Plug, Play, RefreshCw, Server, X, Zap } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AgentSummary, api, Campaign, DepartmentInfo, Mode, OrgInfo, Readiness, ToolNeed, usd, useApi } from "@/lib/api";
import { BudgetBreakdown } from "./Budget";
import { DatabaseForm, GitHubForm } from "./Connections";
import { Assurance, PlanSteps, StepList, teamName, usePermissions } from "./GoalPlan";
import { AgentAvatar } from "./team";
import { Button, cx, ErrorNote } from "./ui";

type Use = { agent: string; text: string; mode: Mode };
type Need = ToolNeed & { uses: Use[] };

/**
 * Starting AI employees, in two short steps:
 *   1. connect the tools they'll use, seeing for each what they do on their own and what needs an OK,
 *   2. see who approves (and where work is handed on), change it if you like, and start.
 */
export function StartGoal({ goals, onClose, onStarted }: { goals: Campaign[]; onClose: () => void; onStarted: () => void }) {
  const [step, setStep] = useState<1 | 2>(1);
  const [ready, setReady] = useState<Record<string, Readiness>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org", { live: false });

  const load = useCallback(async () => {
    setError(null);
    try {
      const entries = await Promise.all(goals.map(async (g) => {
        if (!g.has_playbook) await api(`/api/campaigns/${g.id}/playbook`, { method: "POST" });
        return [g.id, await api<Readiness>(`/api/campaigns/${g.id}/readiness`)] as const;
      }));
      setReady(Object.fromEntries(entries));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [goals]);
  useEffect(() => {
    load();
  }, [load]);

  // Every tool the plans use, with what each AI employee does with it.
  const needs: Need[] = [];
  for (const g of goals) {
    const r = ready[g.id];
    if (!r) continue;
    const modeOf = (k: string) => r.permissions.find((p) => p.key === k)?.mode ?? "ask";
    for (const t of r.tools) {
      let n = needs.find((x) => x.key === t.key);
      if (!n) needs.push((n = { ...t, uses: [] }));
      n.required ||= t.required;
      if (t.status !== "missing") n.status = t.status;
      for (const st of r.playbook?.steps || []) {
        if (st.tool === t.key && !n.uses.some((u) => u.text === st.text)) {
          n.uses.push({ agent: g.agent?.name || "AI employee", text: st.text, mode: modeOf(st.action_type) });
        }
      }
    }
  }
  needs.sort((a, b) => Number(a.status !== "missing") - Number(b.status !== "missing") || Number(b.required) - Number(a.required));
  const missing = needs.filter((n) => n.required && n.status === "missing");
  const servers = Object.values(ready)[0]?.mcp_servers || [];
  const composio = !!Object.values(ready)[0]?.composio_enabled;
  const total = goals.reduce((t, g) => t + g.budget.total, 0);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      for (const g of goals) await api(`/api/campaigns/${g.id}/launch`, { method: "POST" });
      onStarted();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const agentIds = [...new Set(goals.map((g) => g.agent?.id).filter(Boolean))] as string[];
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-canvas shadow-xl sm:rounded-2xl">
        <div className="flex items-start gap-3 border-b border-line bg-white px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted">
              <StepDot n={1} active={step === 1} done={step === 2} label="Connect tools" />
              <span className="h-px w-6 bg-line" />
              <StepDot n={2} active={step === 2} done={false} label="Who approves" />
            </div>
            <h2 className="mt-1.5 truncate text-lg font-bold">{goals.length === 1 ? goals[0].name : `Start ${goals.length} goals`}</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-gray-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {loading && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Checking what they need…</p>}
          {error && <ErrorNote>{error}</ErrorNote>}

          {!loading && step === 1 && (
            <>
              <p className="flex items-start gap-2 text-sm text-gray-700">
                <Lock size={15} className="mt-0.5 shrink-0 text-emerald-600" />
                Connecting a tool lets them use it. Anything marked <b className="text-amber-700">&nbsp;needs an OK&nbsp;</b> still waits for a person.
              </p>
              {needs.length === 0 && <div className="rounded-xl border border-line bg-white px-4 py-3 text-sm">They only need the web for now. Nothing to connect.</div>}
              {needs.map((n) => <ToolCard key={n.key} n={n} composio={composio} onChanged={load} />)}
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-line bg-white px-4 py-2.5 text-xs text-muted">
                <Server size={14} /> {servers.length ? `Your MCP servers: ${servers.map((s) => s.name).join(", ")}` : "Have your own tools or an MCP server?"}
                <Link href="/settings#mcp" target="_blank" className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline">{servers.length ? "Manage" : "Add one"} <ExternalLink size={11} /></Link>
              </div>
            </>
          )}

          {!loading && step === 2 && org && (
            <>
              <p className="flex items-start gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                <Lock size={15} className="mt-0.5 shrink-0" />
                <span><b>Nothing goes out without a yes.</b> Each AI employee asks the person below before it sends, posts, spends, merges or changes anything.</span>
              </p>
              {agentIds.map((id) => <Routing key={id} agentId={id} org={org} onChanged={reloadOrg} />)}
              <details className="rounded-xl border border-line bg-white">
                <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
                  {goals.length} {goals.length === 1 ? "goal" : "goals"} · {usd(total)} for the first week, a hard limit
                </summary>
                <div className="space-y-2 border-t border-line p-3">{goals.map((g) => <GoalReview key={g.id} goal={g} single={false} />)}</div>
              </details>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-white px-5 py-3">
          {step === 2 ? <Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft size={15} /> Back</Button> : <Button variant="ghost" onClick={onClose}>Not now</Button>}
          {step === 1 ? (
            <Button variant="primary" disabled={loading} onClick={() => setStep(2)}>
              {missing.length ? `Continue, connect ${missing.length === 1 ? "it" : "them"} later` : "Continue"} <ArrowRight size={15} />
            </Button>
          ) : (
            <Button variant="primary" disabled={busy} onClick={start}><Play size={15} /> {goals.length === 1 ? "Start" : `Start all ${goals.length}`}</Button>
          )}
        </div>
      </div>
    </div>
  );
}

function StepDot({ n, active, done, label }: { n: number; active: boolean; done: boolean; label: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5", active ? "text-ink" : "text-muted")}>
      <span className={cx("grid h-5 w-5 place-items-center rounded-full text-[11px]", done ? "bg-emerald-600 text-white" : active ? "bg-brand-500 text-white" : "bg-gray-200")}>
        {done ? <Check size={11} /> : n}
      </span>
      {label}
    </span>
  );
}

function ToolCard({ n, composio, onChanged }: { n: Need; composio: boolean; onChanged: () => void }) {
  const [opened, setOpened] = useState(false);
  const [form, setForm] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const done = n.status !== "missing";
  const auto = n.uses.filter((u) => u.mode === "auto");
  const asks = n.uses.filter((u) => u.mode === "ask");
  const agents = [...new Set(n.uses.map((u) => u.agent))];

  async function connectApp() {
    setErr(null);
    try {
      const r = await api<{ redirect_url: string }>(`/api/connections/${n.app}/connect`, { method: "POST" });
      window.open(r.redirect_url, "_blank", "noopener");
      setOpened(true);
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  async function openSite() {
    setErr(null);
    try {
      await api("/api/browser/open", { method: "POST", json: { url: n.login_url || n.site } });
      setOpened(true);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const icon = n.kind === "github" ? <GitBranch size={15} /> : n.kind === "postgres" ? <Database size={15} /> : <Plug size={15} />;
  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-lg", done ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-500")}>{done ? <Check size={16} /> : icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{n.label}</div>
          <div className="truncate text-xs text-muted">{agents.join(", ") || "One of the channels you picked"}</div>
        </div>
        {done ? (
          <span className="text-xs font-semibold text-emerald-700">{n.status === "connected" ? "Connected" : "Signed in"}</span>
        ) : n.kind !== "app" ? (
          <Button size="sm" variant="primary" onClick={() => setForm(!form)}>Connect</Button>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {composio && n.app && <Button size="sm" variant="primary" onClick={connectApp}>Connect</Button>}
            {n.site && <Button size="sm" onClick={openSite}><Globe size={13} /> Sign in</Button>}
          </div>
        )}
      </div>
      {(auto.length > 0 || asks.length > 0) && (
        <div className="mt-2 grid gap-1 pl-11 text-[12.5px]">
          {auto.length > 0 && <UseLine icon={<Zap size={12} />} tone="text-emerald-700" label="On its own" items={auto} />}
          {asks.length > 0 && <UseLine icon={<Hand size={12} />} tone="text-amber-700" label="Needs an OK" items={asks} />}
        </div>
      )}
      {!done && form && n.kind === "github" && <div className="mt-3 pl-11"><GitHubForm onDone={() => { setForm(false); onChanged(); }} /></div>}
      {!done && form && n.kind === "postgres" && <div className="mt-3 pl-11"><DatabaseForm onDone={() => { setForm(false); onChanged(); }} /></div>}
      {!done && opened && (
        <div className="mt-2 flex flex-wrap items-center gap-2 pl-11 text-xs text-muted">
          {n.site && !(composio && n.app) ? (
            <>Sign in in the Agent Chrome window, then
              <Button size="sm" variant="ghost" onClick={async () => { await api("/api/sites/signed-in", { method: "POST", json: { site: n.site } }); onChanged(); }}><Check size={13} /> I&apos;ve signed in</Button></>
          ) : (
            <Button size="sm" variant="ghost" onClick={onChanged}><RefreshCw size={13} /> Check again</Button>
          )}
        </div>
      )}
      {err && <p className="mt-1.5 pl-11 text-xs text-red-600">{err}</p>}
    </div>
  );
}

function UseLine({ icon, tone, label, items }: { icon: React.ReactNode; tone: string; label: string; items: Use[] }) {
  const shown = items.slice(0, 2);
  return (
    <div className="flex gap-1.5">
      <span className={cx("inline-flex shrink-0 items-center gap-1 font-semibold", tone)}>{icon} {label}:</span>
      <span className="min-w-0 text-gray-700">
        {shown.map((u) => u.text).join(" · ")}{items.length > 2 ? ` · +${items.length - 2} more` : ""}
      </span>
    </div>
  );
}

/** One AI employee: who it asks, and (for product work) where its PRDs go. All changeable here. */
function Routing({ agentId, org, onChanged }: { agentId: string; org: OrgInfo; onChanged: () => void }) {
  const dept = org.departments.find((d) => d.agents.some((a) => a.id === agentId)) as DepartmentInfo | undefined;
  const a = dept?.agents.find((x) => x.id === agentId) as AgentSummary | undefined;
  const [err, setErr] = useState<string | null>(null);
  if (!a || !dept) return null;
  const owner = org.members.find((m) => m.role === "owner");
  const lead = dept.head || owner;
  const name = (p?: { id: string; name: string; email: string } | null) => (!p ? "the owner" : p.id === org.me.id ? "You" : p.name || p.email);
  const canEdit = org.me.is_admin || org.me.department_ids.includes(dept.id);
  const others = org.departments.flatMap((d) => d.agents.map((x) => ({ ...x, dept: d.name }))).filter((x) => x.id !== a.id);
  const showHandoff = dept.kind === "product" || !!a.handoff_to_agent_id;
  const manager = a.reports_to || lead;

  async function patch(json: Record<string, unknown>) {
    setErr(null);
    try {
      await api(`/api/agents/${a!.id}`, { method: "PATCH", json });
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <AgentAvatar name={a.name} size={30} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{a.name}</div>
          <div className="text-xs text-muted">{dept.name}</div>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <Hand size={12} /> Asks
          <select disabled={!canEdit} className="rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-ink" value={a.reports_to?.id || ""}
            onChange={(e) => patch({ reports_to_user_id: e.target.value || null })}>
            <option value="">{name(lead)}{dept.head ? ` (head of ${dept.name})` : ""}</option>
            {org.members.filter((m) => m.id !== lead?.id).map((m) => <option key={m.id} value={m.id}>{name(m)}</option>)}
          </select>
        </label>
      </div>
      {showHandoff && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-line pt-2.5 pl-11 text-xs">
          <span className="font-semibold text-gray-700">PRDs go to</span>
          <select disabled={!canEdit} className="rounded-md border border-line bg-white px-2 py-1 font-semibold" value={a.handoff_to_agent_id || ""}
            onChange={(e) => patch({ handoff_to_agent_id: e.target.value || null })}>
            <option value="">{name(manager)} only (no hand-off)</option>
            {others.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.dept})</option>)}
          </select>
          {a.handoff_to_agent_id && (
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" disabled={!canEdit} className="h-3.5 w-3.5 accent-brand-500" checked={a.handoff_review} onChange={(e) => patch({ handoff_review: e.target.checked })} />
              {name(manager) === "You" ? "You approve first" : `${name(manager)} approves first`}
            </label>
          )}
        </div>
      )}
      {err && <p className="mt-1.5 text-xs text-red-600">{err}</p>}
    </div>
  );
}

function GoalReview({ goal, single }: { goal: Campaign; single: boolean }) {
  const { perms, note, error, busy, change } = usePermissions(goal.id);
  const [book, setBook] = useState(goal.playbook || null);
  const [customize, setCustomize] = useState(false);
  useEffect(() => {
    if (!book) api<Campaign>(`/api/campaigns/${goal.id}`).then((g) => setBook(g.playbook || null)).catch(() => null);
  }, [goal.id, book]);
  const agent = goal.agent?.name || "It";
  const [open, setOpen] = useState(single);
  const modeOf = (k: string) => perms?.action_types.find((p) => p.key === k)?.mode ?? "ask";
  const auto = book ? book.steps.filter((st) => modeOf(st.action_type) === "auto").length : 0;
  const asks = book ? book.steps.filter((st) => modeOf(st.action_type) === "ask").length : 0;
  if (!single && !open) {
    return (
      <button onClick={() => setOpen(true)} className="flex w-full items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 text-left hover:border-gray-400">
        {goal.agent && <AgentAvatar name={goal.agent.name} size={28} />}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold">{goal.name}</span>
          <span className="block text-xs text-muted">
            {goal.agent?.name}{book ? ` · ${auto} automatic, ${asks} ${asks === 1 ? "waits" : "wait"} for your OK` : ""}
          </span>
        </span>
        <span className="shrink-0 text-sm font-semibold">{usd(goal.budget.total)}</span>
        <ChevronDown size={16} className="shrink-0 text-muted" />
      </button>
    );
  }
  return (
    <div className={cx("space-y-3", !single && "rounded-xl border border-line bg-white p-4")}>
      {!single && (
        <button onClick={() => setOpen(false)} className="flex w-full items-center gap-2 text-left">
          {goal.agent && <AgentAvatar name={goal.agent.name} size={26} />}
          <div className="min-w-0 flex-1"><div className="truncate text-sm font-bold">{goal.name}</div><div className="text-xs text-muted">{goal.agent?.name}</div></div>
          <ChevronDown size={16} className="shrink-0 rotate-180 text-muted" />
        </button>
      )}
      {perms && single && <Assurance perms={perms} agent={agent} />}
      {!single && goal.first_deliverable && (
        <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px]"><b className="text-brand-700">First week:</b> {goal.first_deliverable}</p>
      )}
      {book && perms && (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Step by step</span>
            {perms.can_edit && <button onClick={() => setCustomize(!customize)} className="text-sm font-semibold text-brand-600 hover:underline">{customize ? "Done" : "Customize"}</button>}
          </div>
          {customize
            ? <PlanSteps steps={book.steps} perms={perms} editable onChange={change} busy={busy} />
            : <StepList steps={book.steps} modeOf={(k) => perms.action_types.find((p) => p.key === k)?.mode ?? "ask"} team={teamName(perms)} />}
        </div>
      )}
      {note && <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">{note}</p>}
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="rounded-lg border border-line bg-white px-3 py-2.5">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Budget: {usd(goal.budget.total)}{goal.budget_basis?.starter ? " for the first week" : ""}, a hard limit</div>
        {goal.budget_basis?.starter
          ? <p className="text-[12.5px] text-gray-700">About {goal.budget_basis.sessions} work sessions. When it&apos;s used up, work pauses and you decide whether to add more (the whole goal would take about {usd(goal.budget_basis.full_usd || 0)}).</p>
          : goal.budget_basis ? <BudgetBreakdown basis={goal.budget_basis} total={goal.budget.total} compact /> : <p className="text-xs text-muted">When it runs out, work pauses.</p>}
      </div>
    </div>
  );
}
