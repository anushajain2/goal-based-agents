"use client";

import { ArrowLeft, ArrowRight, Check, ChevronDown, Clock, Database, ExternalLink, GitBranch, Hand, Loader2, Lock, Plug, Play, Server, X, Zap } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AgentSummary, api, BrowserInfo, Campaign, DepartmentInfo, Mode, OrgInfo, perWeek, Readiness, ToolNeed, usd, useApi } from "@/lib/api";
import { AutonomyChoice, AutonomySetup, initialChoice, modeFromChoice } from "./AutonomySetup";
import { BudgetBreakdown } from "./Budget";
import { connectHint, useConnect } from "./ConnectTool";
import { DatabaseForm, GitHubForm } from "./Connections";
import { PlanStory, WhatItWillDo } from "./GoalEngine";
import { StepList, stepCounts, teamName } from "./GoalPlan";
import { Button, cx, ErrorNote } from "./ui";

type Use = { agent: string; text: string; mode: Mode };
type Need = ToolNeed & { uses: Use[] };

/**
 * Starting goals, in three short steps:
 *   0. the plan: how each goal gets hit and what it will do (creative approaches too, by milestone),
 *   1. connect the tools they'll use, seeing for each what they do on their own and what needs an OK,
 *   2. choose how much they do without asking (a recommended preset, changeable per kind of action),
 *      see who approves (and where work is handed on), and start.
 */
export function StartGoal({ goals, onClose, onStarted }: { goals: Campaign[]; onClose: () => void; onStarted: () => void }) {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [ready, setReady] = useState<Record<string, Readiness>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org", { live: false });
  const [choice, setChoice] = useState<AutonomyChoice | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const entries = await Promise.all(goals.map(async (g) => {
        if (!g.has_playbook) await api(`/api/campaigns/${g.id}/playbook`, { method: "POST" });
        return [g.id, await api<Readiness>(`/api/campaigns/${g.id}/readiness`)] as const;
      }));
      setReady(Object.fromEntries(entries));
      setChoice((c) => c ?? initialChoice(entries.map(([, r]) => r.autonomy).filter(Boolean)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [goals]);
  useEffect(() => {
    load();
  }, [load]);

  const autonomies = goals.map((g) => ready[g.id]?.autonomy).filter(Boolean);
  const chosen = choice ? modeFromChoice(autonomies, choice) : () => undefined;
  const inPlan = new Set(goals.flatMap((g) => (ready[g.id]?.playbook?.steps || []).map((st) => st.action_type)));
  // What each kind of action will do once started: the autonomy choice, unless a never-rule wins.
  const PERSONAL_TYPES = ["publish_post", "publish_article", "reply", "send_message"];
  const modeFor = (r: Readiness) => (k: string, tool?: string): Mode => {
    const current = r.permissions.find((p) => p.key === k);
    if (current?.mode === "never" || current?.default === "auto") return current.mode;
    const mode = chosen(k) ?? current?.mode ?? "ask";
    if (tool && choice?.personal.includes(tool) && PERSONAL_TYPES.includes(k) && mode !== "never") return "ask";
    return mode;
  };

  // Every tool the plans use, with what each goal does with it.
  const needs: Need[] = [];
  for (const g of goals) {
    const r = ready[g.id];
    if (!r) continue;
    const modeOf = modeFor(r);
    for (const t of r.tools) {
      let n = needs.find((x) => x.key === t.key);
      if (!n) needs.push((n = { ...t, uses: [] }));
      n.required ||= t.required;
      if (t.status !== "missing") n.status = t.status;
      for (const st of r.playbook?.steps || []) {
        if (st.tool === t.key && !n.uses.some((u) => u.text === st.text)) {
          n.uses.push({ agent: g.name, text: st.text, mode: modeOf(st.action_type, st.tool) });
        }
      }
    }
  }
  needs.sort((a, b) => Number(a.status !== "missing") - Number(b.status !== "missing") || Number(b.required) - Number(a.required));
  const missing = needs.filter((n) => n.required && n.status === "missing");
  const servers = Object.values(ready)[0]?.mcp_servers || [];
  const browser = Object.values(ready)[0]?.browser;
  const total = goals.reduce((t, g) => t + g.budget.total, 0);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      for (const g of goals) {
        if (choice && ready[g.id]?.autonomy) {
          // Only the changes that apply to this goal's own rows.
          const keys = new Set(ready[g.id].autonomy.presets[choice.preset].rows.map((r) => r.key));
          const overrides = Object.fromEntries(Object.entries(choice.overrides).filter(([k]) => keys.has(k)));
          const personal = choice.personal.filter((p) => ready[g.id].autonomy.personal_candidates.some((x) => x.key === p));
          await api(`/api/campaigns/${g.id}/autonomy`, { method: "POST", json: { preset: choice.preset, overrides, personal } });
        }
        await api(`/api/campaigns/${g.id}/launch`, { method: "POST" });
      }
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
              <StepDot n={1} active={step === 0} done={step > 0} label="The plan" />
              <span className="h-px w-6 bg-line" />
              <StepDot n={2} active={step === 1} done={step === 2} label="Connect tools" />
              <span className="h-px w-6 bg-line" />
              <StepDot n={3} active={step === 2} done={false} label="Approvals" />
            </div>
            <h2 className="mt-1.5 truncate text-lg font-bold">{goals.length === 1 ? goals[0].name : `Start ${goals.length} goals`}</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-stone-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {loading && step > 0 && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Checking what&apos;s needed…</p>}
          {error && <ErrorNote>{error}</ErrorNote>}

          {step === 0 && (goals.length === 1 ? (
            <PlanStory goal={goals[0]} />
          ) : (
            <ul className="space-y-2">
              {goals.map((g) => (
                <li key={g.id} className="rounded-xl border border-line bg-white px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13.5px] font-semibold">{g.name}</div>
                      {g.first_deliverable && <div className="truncate text-[12px] text-muted">First week: {g.first_deliverable}</div>}
                    </div>
                  </div>
                  <div className="mt-2"><WhatItWillDo goal={g} compact /></div>
                </li>
              ))}
            </ul>
          ))}

          {!loading && step === 1 && (
            <>
              <p className="flex items-start gap-2 text-sm text-stone-700">
                <Lock size={15} className="mt-0.5 shrink-0 text-emerald-600" />
                <span>
                  Connecting a tool lets Oton use it. Anything marked <b className="text-signal-700">needs an OK</b> still waits for a person;
                  you choose how much goes out on its own in the next step.
                </span>
              </p>
              {needs.length === 0 && <div className="rounded-xl border border-line bg-white px-4 py-3 text-sm">It only needs the web for now. Nothing to connect.</div>}
              {needs.map((n) => <ToolCard key={n.key} n={n} browser={browser} onChanged={load} />)}
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-line bg-white px-4 py-2.5 text-xs text-muted">
                <Server size={14} /> {servers.length ? `Your MCP servers: ${servers.map((s) => s.name).join(", ")}` : "Have your own tools or an MCP server?"}
                <Link href="/settings#mcp" target="_blank" className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline">{servers.length ? "Manage" : "Add one"} <ExternalLink size={11} /></Link>
              </div>
            </>
          )}

          {!loading && step === 2 && org && (
            <>
              {choice && autonomies[0] && (
                <AutonomySetup autonomy={autonomies[0]} inPlan={inPlan} choice={choice} onChange={setChoice} multiple={goals.length > 1}
                  team={ready[goals[0].id] ? teamName(ready[goals[0].id]) : "your team"} />
              )}
              <h3 className="px-1 pt-1 text-[12px] font-bold text-muted">Who it asks</h3>
              {agentIds.map((id) => <Routing key={id} agentId={id} org={org} onChanged={reloadOrg} />)}
              <details className="rounded-xl border border-line bg-white">
                <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
                  {goals.length} {goals.length === 1 ? "goal" : "goals"}, {usd(total)} for the first week (a hard limit)
                </summary>
                <div className="space-y-2 border-t border-line p-3">
                  {goals.map((g) => <GoalReview key={g.id} goal={g} modeOf={ready[g.id] ? modeFor(ready[g.id]) : () => "ask"} team={ready[g.id] ? teamName(ready[g.id]) : undefined} />)}
                </div>
              </details>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-white px-5 py-3">
          {step > 0 ? <Button variant="ghost" onClick={() => setStep(step === 2 ? 1 : 0)}><ArrowLeft size={15} /> Back</Button> : <Button variant="ghost" onClick={onClose}>Not now</Button>}
          {step === 0 ? (
            <Button variant="primary" onClick={() => setStep(1)}>Looks good <ArrowRight size={15} /></Button>
          ) : step === 1 ? (
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
      <span className={cx("grid h-5 w-5 place-items-center rounded-full text-[12px]", done ? "bg-emerald-600 text-white" : active ? "bg-brand-500 text-white" : "bg-stone-200")}>
        {done ? <Check size={11} /> : n}
      </span>
      {label}
    </span>
  );
}

function ToolCard({ n, browser, onChanged }: { n: Need; browser?: BrowserInfo | null; onChanged: () => void }) {
  const [form, setForm] = useState(false);
  const done = n.status !== "missing";
  const auto = n.uses.filter((u) => u.mode === "auto");
  const heads = n.uses.filter((u) => u.mode === "heads_up");
  const asks = n.uses.filter((u) => u.mode === "ask");
  const agents = [...new Set(n.uses.map((u) => u.agent))];
  const { button, help, error } = useConnect(n, browser, onChanged, typeof window !== "undefined" ? window.location.pathname : "/goals");
  const hint = connectHint(n, browser);

  const icon = n.kind === "github" ? <GitBranch size={15} /> : n.kind === "postgres" ? <Database size={15} /> : <Plug size={15} />;
  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-lg", done ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500")}>{done ? <Check size={16} /> : icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{n.label}</div>
          <div className="truncate text-xs text-muted">
            {agents.length ? `For ${agents.join(", ")}` : "One of the channels you picked"}{!done && hint ? ` · ${hint}` : ""}
          </div>
        </div>
        {done ? (
          <span className="text-xs font-semibold text-emerald-700">{n.status === "connected" ? "Connected" : "Signed in"}</span>
        ) : n.kind !== "app" ? (
          <Button size="sm" variant="primary" onClick={() => setForm(!form)}>Connect</Button>
        ) : button}
      </div>
      {(auto.length > 0 || heads.length > 0 || asks.length > 0) && (
        <div className="mt-2 grid gap-1 pl-11 text-[12.5px]">
          {auto.length > 0 && <UseLine icon={<Zap size={12} />} tone="text-emerald-700" label="On its own" items={auto} />}
          {heads.length > 0 && <UseLine icon={<Clock size={12} />} tone="text-sky-700" label="After a heads-up" items={heads} />}
          {asks.length > 0 && <UseLine icon={<Hand size={12} />} tone="text-signal-700" label="Needs an OK" items={asks} />}
        </div>
      )}
      {!done && form && n.kind === "github" && <div className="mt-3 pl-11"><GitHubForm onDone={() => { setForm(false); onChanged(); }} /></div>}
      {!done && form && n.kind === "postgres" && <div className="mt-3 pl-11"><DatabaseForm onDone={() => { setForm(false); onChanged(); }} /></div>}
      {!done && help && <div className="mt-2.5 rounded-lg bg-canvas px-3 py-2.5 pl-11 text-[12.5px] leading-relaxed text-stone-700">{help}</div>}
      {error && <p className="mt-1.5 pl-11 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function UseLine({ icon, tone, label, items }: { icon: React.ReactNode; tone: string; label: string; items: Use[] }) {
  const shown = items.slice(0, 2);
  return (
    <div className="flex gap-1.5">
      <span className={cx("inline-flex shrink-0 items-center gap-1 font-semibold", tone)}>{icon} {label}:</span>
      <span className="min-w-0 text-stone-700">
        {shown.map((u) => u.text).join(", ")}{items.length > 2 ? `, and ${items.length - 2} more` : ""}
      </span>
    </div>
  );
}

/** One team's work: who it asks, and (for product work) where its PRDs go. All changeable here. */
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
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{dept.name}</div>
          {a.title && <div className="text-xs text-muted">{a.title}</div>}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <Hand size={12} /> Asks
          <select disabled={!canEdit} className="rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-ink" value={a.reports_to?.id || ""}
            onChange={(e) => patch({ reports_to_user_id: e.target.value || null })}>
            <option value="">{name(lead)} (same as the {dept.name} team)</option>
            {org.members.filter((m) => m.id !== lead?.id).map((m) => <option key={m.id} value={m.id}>{name(m)}</option>)}
          </select>
        </label>
      </div>
      {showHandoff && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-line pt-2.5 text-xs">
          <span className="font-semibold text-stone-700">PRDs go to</span>
          <select disabled={!canEdit} className="rounded-md border border-line bg-white px-2 py-1 font-semibold" value={a.handoff_to_agent_id || ""}
            onChange={(e) => patch({ handoff_to_agent_id: e.target.value || null })}>
            <option value="">{name(manager)} only (no hand-off)</option>
            {others.map((x) => <option key={x.id} value={x.id}>{x.dept}{x.title ? ` (${x.title})` : ""}</option>)}
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

/** One goal in the summary: what it does each step (with the autonomy chosen above) and its budget. */
function GoalReview({ goal, modeOf, team }: { goal: Campaign; modeOf: (k: string, tool?: string) => Mode; team?: string }) {
  const [book, setBook] = useState(goal.playbook || null);
  useEffect(() => {
    if (!book) api<Campaign>(`/api/campaigns/${goal.id}`).then((g) => setBook(g.playbook || null)).catch(() => null);
  }, [goal.id, book]);
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="flex w-full items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 text-left hover:border-stone-400">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold">{goal.name}</span>
          <span className="block text-xs text-muted">
            {[goal.department?.name, book && stepCounts(book.steps, modeOf, team || "an OK")].filter(Boolean).join(", ")}
          </span>
        </span>
        <span className="shrink-0 text-sm font-semibold">{goal.weekly_cap ? `Max ${perWeek(goal.weekly_cap)}` : usd(goal.budget.total)}</span>
        <ChevronDown size={16} className="shrink-0 text-muted" />
      </button>
    );
  }
  return (
    <div className="space-y-3 rounded-xl border border-line bg-white p-4">
      <button onClick={() => setOpen(false)} className="flex w-full items-center gap-2 text-left">
        <div className="min-w-0 flex-1"><div className="truncate text-sm font-bold">{goal.name}</div><div className="text-xs text-muted">{goal.department?.name}</div></div>
        <ChevronDown size={16} className="shrink-0 rotate-180 text-muted" />
      </button>
      {goal.first_deliverable && (
        <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px]"><b className="text-brand-700">First week:</b> {goal.first_deliverable}</p>
      )}
      {book && (
        <div>
          <div className="mb-2.5 text-xs font-semibold text-muted">Step by step</div>
          <StepList steps={book.steps} modeOf={modeOf} team={team} />
        </div>
      )}
      <div className="rounded-lg border border-line bg-white px-3 py-2.5">
        {goal.weekly_cap ? (
          <>
            <div className="mb-1 text-xs font-semibold text-muted">Max budget: {perWeek(goal.weekly_cap)}</div>
            <p className="text-[12.5px] text-stone-700">A long-term goal: Oton keeps working toward it every week and never spends more than {usd(goal.weekly_cap)} in a week. When a week&apos;s limit is used up, it waits for Monday. Stop it any time.</p>
          </>
        ) : <>
        <div className="mb-1 text-xs font-semibold text-muted">Budget: {usd(goal.budget.total)}{goal.budget_basis?.starter ? " for the first week" : ""}, a hard limit</div>
        {goal.budget_basis?.starter
          ? <p className="text-[12.5px] text-stone-700">About {goal.budget_basis.sessions} work sessions. When it&apos;s used up, work pauses and you decide whether to add more (the whole goal would take about {usd(goal.budget_basis.full_usd || 0)}).</p>
          : goal.budget_basis ? <BudgetBreakdown basis={goal.budget_basis} total={goal.budget.total} compact /> : <p className="text-xs text-muted">When it runs out, work pauses.</p>}
        </>}
      </div>
    </div>
  );
}
