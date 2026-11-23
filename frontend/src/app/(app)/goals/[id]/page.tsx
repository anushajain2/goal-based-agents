"use client";

import { ArrowLeft, Flag, Hand, Inbox, Pause, Play, RefreshCw, Sparkles, Target, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { GoalStatus, progressOf, ProgressBar } from "@/components/goal";
import { BudgetBreakdown, BudgetCalculator } from "@/components/Budget";
import { GoalPlan, PermissionsEditor, usePermissions } from "@/components/GoalPlan";
import { ListEditor } from "@/components/Guardrails";
import { TargetHistory } from "@/components/Target";
import { StartGoal } from "@/components/StartGoal";
import { MetricChart } from "@/components/MetricChart";
import { AgentAvatar } from "@/components/team";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Tabs, Textarea, Select } from "@/components/ui";
import { CATEGORY_ICON } from "@/components/UseCaseLibrary";
import { ViewToggle, WorkLog } from "@/components/WorkLog";
import { ActivityItem, api, Campaign, Exclusion, Grant, Level, num, Person, Session, timeAgo, usd, useApi, UserRequest, PERIOD_WORD, Period } from "@/lib/api";
import { CATEGORIES } from "@/lib/useCases";

type Tab = "work" | "results" | "guardrails" | "settings";

export default function Page() {
  return (
    <Suspense>
      <GoalPage />
    </Suspense>
  );
}

function GoalPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "work");
  const [view, setView] = useState<"highlights" | "everything">("highlights");
  const { data: c, error, reload } = useApi<Campaign>(`/api/campaigns/${id}`, { campaignId: id });
  const { data: activity } = useApi<ActivityItem[]>(`/api/campaigns/${id}/activity?limit=500`, { campaignId: id });
  const { data: sessions } = useApi<Session[]>(`/api/campaigns/${id}/sessions`, { campaignId: id });
  const { data: requests, reload: reloadRequests } = useApi<UserRequest[]>(`/api/requests?status=pending&campaign_id=${id}`, { campaignId: id });
  const { data: agentInfo } = useApi<{ approvers: Person[] }>(c?.agent ? `/api/agents/${c.agent.id}` : null, { live: false });
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(params.get("start") === "1");

  async function lifecycle(action: "launch" | "pause" | "resume" | "run-now") {
    setBusy(true);
    try {
      await api(`/api/campaigns/${id}/${action}`, { method: "POST" });
      await reload();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!c) return <p className="text-muted">Loading…</p>;

  const p = progressOf(c);
  const series = (c.metrics || []).filter((m) => m.metric.toLowerCase() === c.primary_metric.toLowerCase());
  const run = c.current_run;
  const busyRun = !!(run && ["queued", "running", "waiting"].includes(run.status));
  const catKey = CATEGORIES.find((k) => k.name === c.category)?.key;
  const budgetPct = c.budget.total ? Math.min(100, ((c.budget.spent + c.budget.reserved) / c.budget.total) * 100) : 0;
  const sessionCost = (sessions || []).filter((s) => s.status === "completed");
  const avgSession = sessionCost.length ? sessionCost.reduce((t, s) => t + s.cost_usd, 0) / sessionCost.length : null;

  return (
    <div className="space-y-5">
      <Link href="/goals" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={15} /> Goals
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            {c.category && <span className="inline-flex items-center gap-1">{catKey && CATEGORY_ICON[catKey]} {c.category}{c.use_case ? ` · ${c.use_case}` : ""}</span>}
            {c.client_name && <Badge tone="violet">for {c.client_name}</Badge>}
          </div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-tight">{c.name}</h1>
          {c.agent && (
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
              <Link href={`/team/agents/${c.agent.id}`} className="inline-flex items-center gap-1.5 font-semibold hover:underline">
                <AgentAvatar name={c.agent.name} size={22} /> {c.agent.name}
              </Link>
              {c.department && <span className="text-muted">{c.department.name}</span>}
              {agentInfo && (
                <span className="inline-flex items-center gap-1 text-muted">
                  <Hand size={13} /> Approvals go to {agentInfo.approvers.map((p) => p.name || p.email).join(", ") || "admins"}
                </span>
              )}
            </div>
          )}
          {c.goal_description !== c.name && <p className="mt-1.5 max-w-2xl text-[14.5px] text-zinc-600">{c.goal_description}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
            <GoalStatus c={c} />
            {c.done_when && (
              <span className="inline-flex items-center gap-1 text-muted"><Flag size={13} /> Counts when: <span className="text-ink">{c.done_when}</span></span>
            )}
            {c.status === "active" && c.next_cycle_at && !busyRun && <span className="text-muted">Next work session {timeAgo(c.next_cycle_at)}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {c.can_manage === false && <span className="text-xs text-muted">View only: managed by the {c.department?.name || "department"} team</span>}
          {c.can_manage !== false && c.status === "draft" && (
            <Button variant="primary" disabled={busy} onClick={() => setStarting(true)}><Play size={15} /> Start working</Button>
          )}
          {c.can_manage !== false && c.status === "active" && (
            <>
              <Button disabled={busy || busyRun} onClick={() => lifecycle("run-now")} title="Start a work session now instead of waiting for the next check-in">
                <RefreshCw size={15} /> Work on it now
              </Button>
              <Button disabled={busy} onClick={() => lifecycle("pause")}><Pause size={15} /> Pause</Button>
            </>
          )}
          {c.can_manage !== false && c.status === "paused" && (
            <Button variant="primary" disabled={busy} onClick={() => lifecycle("resume")}><Play size={15} /> Resume</Button>
          )}
        </div>
      </div>

      {(c.key_results?.length || 0) > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-2xl border border-line bg-white px-4 py-3 text-[13px] shadow-[var(--shadow-card)]">
          <span className="text-[11px] font-bold uppercase tracking-wide text-zinc-700">Key results</span>
          {c.key_results.map((kr) => <span key={kr} className="inline-flex items-center gap-1.5"><Target size={13} className="text-zinc-600" /> {kr}</span>)}
        </div>
      )}
      {(c.target?.history?.length || 0) > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <span className="font-semibold text-muted">Past periods</span>
          <TargetHistory target={c.target} />
        </div>
      )}

      {c.origin === "setup" && c.status === "draft" && (
        <div className="flex flex-wrap items-start gap-3 rounded-xl border border-brand-500/30 bg-brand-50/60 px-4 py-3 text-sm">
          <Sparkles size={16} className="mt-0.5 shrink-0 text-brand-600" />
          <div className="min-w-0 flex-1">
            {c.first_deliverable && <div className="mb-1"><b>In your first week you get:</b> {c.first_deliverable}</div>}
            <b>Suggested by setup research.</b> {c.suggested_reason}
            <div className="text-xs text-muted">Check the target, budget and brief in Settings, then start it. Nothing is spent until you do.</div>
          </div>
        </div>
      )}

      {starting && c.status === "draft" && c.can_manage !== false && (
        <StartGoal goals={[c]} onClose={() => setStarting(false)} onStarted={() => { setStarting(false); reload(); }} />
      )}

      <GoalPlan goal={c} defaultOpen={c.status === "draft"} />

      {c.status === "out_of_budget" && <ErrorNote>The budget is used up, so {c.agent?.name || "Autopilot"} has stopped working on this goal. Raise the budget in Settings to continue.</ErrorNote>}

      {/* Scorecard */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {c.target?.target && c.target.status === "active" ? (
          <Card className="p-4">
            <div className="text-xs font-semibold text-muted">Target {c.target.period ? PERIOD_WORD[c.target.period] : ""}</div>
            <div className="tabular mt-1 text-2xl font-bold">
              {num(c.target.progress)}<span className="text-base font-semibold text-muted"> / {num(c.target.target)}</span>
            </div>
            <ProgressBar pct={Math.min(100, ((c.target.progress || 0) / c.target.target) * 100)} className="mt-2" />
            <div className="mt-1 truncate text-xs text-muted">{c.primary_metric}{c.target.days_left != null ? ` · ${Math.ceil(c.target.days_left)}d left` : ""}</div>
          </Card>
        ) : (
          <Card className="p-4">
            <div className="text-xs font-semibold text-muted">Progress</div>
            <div className="tabular mt-1 text-2xl font-bold">
              {p.done === null ? "—" : num(p.done)}
              {p.target ? <span className="text-base font-semibold text-muted"> / {num(p.target)}</span> : null}
            </div>
            <ProgressBar pct={p.pct} className="mt-2" />
            <div className="mt-1 truncate text-xs text-muted">{c.primary_metric}</div>
          </Card>
        )}
        <Kpi label="Cost per result" value={usd(c.cost_per_result)} sub={c.results.results ? `${num(c.results.results)} results so far` : "Shown once results come in"} />
        <Kpi label="Actions taken" value={num(c.actions_taken)} sub={`${c.cycles_completed} work session${c.cycles_completed === 1 ? "" : "s"}${avgSession !== null ? ` · ~${usd(avgSession)} each` : ""}`} />
        <Card className="p-4">
          <div className="text-xs font-semibold text-muted">Spent</div>
          <div className="tabular mt-1 text-2xl font-bold">{usd(c.budget.spent)} <span className="text-base font-semibold text-muted">/ {usd(c.budget.total)}</span></div>
          <ProgressBar pct={budgetPct} tone="gray" className="mt-2" />
          <div className="mt-1 text-xs text-muted">
            AI {usd(c.budget.ai_usage)} · other {usd(c.budget.other_spend)}{c.budget.daily_cap ? ` · today ${usd(c.budget.today)}/${usd(c.budget.daily_cap)}` : ""}
          </div>
          {c.budget_basis?.starter && c.can_manage !== false && c.status !== "completed" && (
            <button disabled={busy} onClick={async () => {
              setBusy(true);
              try {
                await api(`/api/campaigns/${c.id}`, { method: "PATCH", json: { budget_total: c.budget.total + (c.budget_basis?.suggested_usd || 5) } });
                await reload();
              } finally {
                setBusy(false);
              }
            }} className="mt-1.5 block text-xs font-semibold text-brand-600 hover:underline">
              + Add another week ({usd(c.budget_basis.suggested_usd)})
            </button>
          )}
          {c.budget_basis && (
            <details className="mt-1.5 text-xs">
              <summary className="cursor-pointer font-semibold text-brand-600">How was this set?</summary>
              <div className="mt-1.5"><BudgetBreakdown basis={c.budget_basis} total={c.budget.total} pace={c.pace} compact /></div>
            </details>
          )}
        </Card>
      </div>

      <Card>
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "work", label: <>Work log {requests && requests.length > 0 && <Badge tone="amber">{requests.length} needs you</Badge>}</> },
            { key: "results", label: "Results" },
            { key: "guardrails", label: "Guardrails" },
            ...(c.can_manage !== false ? [{ key: "settings" as Tab, label: "Settings" }] : []),
          ]}
        />

        {tab === "work" && (
          <div className="grid grid-cols-1 gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0">
              {requests && requests.length > 0 && (
                <div className="mb-4 space-y-3 lg:hidden">
                  <h3 className="text-[13px] font-bold uppercase tracking-wide text-amber-700">Needs you</h3>
                  {requests.map((r) => <ApprovalCard key={r.id} req={r} onDone={() => { reloadRequests(); reload(); }} />)}
                </div>
              )}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted">Every work session, newest first: the plan, what it did, what it asked you, and what each session cost.</p>
                <ViewToggle value={view} onChange={setView} />
              </div>
              <WorkLog items={activity || []} sessions={sessions || []} view={view} />
            </div>
            <aside className="space-y-4">
              <div className={requests && requests.length > 0 ? "hidden lg:block" : ""}>
                <h3 className="mb-2 text-[13px] font-bold uppercase tracking-wide text-muted">Needs you</h3>
                {requests && requests.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-line px-3 py-4 text-center text-xs text-muted">
                    <Inbox size={18} className="mx-auto mb-1 text-gray-300" />Nothing waiting. It asks the {c.department?.name || "team"} team here before anything that isn&apos;t pre-approved.
                  </div>
                ) : (
                  <div className="space-y-3">{(requests || []).map((r) => <ApprovalCard key={r.id} req={r} onDone={() => { reloadRequests(); reload(); }} />)}</div>
                )}
              </div>
              <div>
                <h3 className="mb-2 text-[13px] font-bold uppercase tracking-wide text-muted">Current strategy</h3>
                <div className="whitespace-pre-wrap rounded-lg bg-gray-50 px-3 py-2.5 text-[13px] leading-relaxed">
                  {c.strategy || <span className="text-muted">Written at the start of the first work session.</span>}
                </div>
              </div>
              <div>
                <h3 className="mb-2 text-[13px] font-bold uppercase tracking-wide text-muted">Trend</h3>
                <div className="rounded-lg border border-line p-2"><MetricChart points={series} label={c.primary_metric} /></div>
              </div>
            </aside>
          </div>
        )}

        {tab === "results" && <ResultsTab c={c} sessions={sessions || []} />}
        {tab === "guardrails" && <GuardrailsTab campaignId={id} canEdit={c.can_manage !== false} />}
        {tab === "settings" && <SettingsTab c={c} onSaved={reload} onDeleted={() => router.push("/goals")} />}
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

function ResultsTab({ c, sessions }: { c: Campaign; sessions: Session[] }) {
  const series = (c.metrics || []).filter((m) => m.metric.toLowerCase() === c.primary_metric.toLowerCase());
  const readings = [...(c.metrics || [])].reverse();
  return (
    <div className="space-y-6 p-4">
      <div>
        <h3 className="mb-2 text-[15px] font-bold">{c.primary_metric}</h3>
        <MetricChart points={series} label={c.primary_metric} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-[15px] font-bold">Readings</h3>
          {readings.length === 0 ? <p className="text-sm text-muted">No readings yet.</p> : (
            <table className="w-full text-left text-[13px]">
              <thead className="text-xs text-muted"><tr><th className="py-1.5">When</th><th>Metric</th><th className="text-right">Value</th><th className="pl-3">Source</th></tr></thead>
              <tbody>
                {readings.slice(0, 50).map((m, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1.5 text-muted">{new Date(m.recorded_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</td>
                    <td>{m.metric}</td>
                    <td className="tabular text-right font-semibold">{num(m.value)}</td>
                    <td className="truncate pl-3 text-muted">{m.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-[15px] font-bold">Cost by work session</h3>
          {sessions.length === 0 ? <p className="text-sm text-muted">No sessions yet.</p> : (
            <table className="w-full text-left text-[13px]">
              <thead className="text-xs text-muted"><tr><th className="py-1.5">Session</th><th>Outcome</th><th className="text-right">Actions</th><th className="text-right">Cost</th></tr></thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id} className="border-t border-line align-top">
                    <td className="py-1.5 pr-2 font-semibold">#{s.number}</td>
                    <td className="py-1.5 pr-2 text-gray-700">{s.summary || s.error || s.status}</td>
                    <td className="tabular py-1.5 text-right">{s.counts.action || 0}</td>
                    <td className="tabular py-1.5 text-right font-semibold">{usd(s.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function GuardrailsTab({ campaignId, canEdit }: { campaignId: string; canEdit: boolean }) {
  const { perms, note, error, busy, change } = usePermissions(campaignId);
  const { data: exclusions, reload: reloadEx } = useApi<Exclusion[]>(`/api/exclusions?campaign_id=${campaignId}`, { campaignId });
  const { data: grants, reload: reloadGrants } = useApi<Grant[]>(`/api/grants?campaign_id=${campaignId}`, { campaignId });
  const levelName = (l: Level) => (l === "department" ? "department-wide" : l === "org" ? "whole organization" : "this goal");
  const listOf = (kind: string) => (exclusions || []).filter((e) => e.kind === kind).map((e) => ({ id: e.id, value: e.level === "goal" ? e.value : `${e.value} (${levelName(e.level)})`, locked: !canEdit || e.level !== "goal" }));
  const add = (kind: string) => async (value: string) => {
    await api("/api/exclusions", { method: "POST", json: { campaign_id: campaignId, kind, value } });
    reloadEx();
  };
  const remove = async (id: string) => {
    await api(`/api/exclusions/${id}`, { method: "DELETE" });
    reloadEx();
  };
  const scoped = (grants || []).filter((g) => g.scope);

  return (
    <div className="space-y-6 p-4">
      <p className="text-sm text-muted">
        Every kind of action this AI employee could take, and who decides. Changes apply straight away, even in the middle of a work session.
        Settings for a whole department or the organization are in Settings → Permissions.
      </p>
      {error && <ErrorNote>{error}</ErrorNote>}
      {note && <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">{note}</p>}
      {perms && <PermissionsEditor perms={{ ...perms, can_edit: perms.can_edit && canEdit }} onChange={change} busy={busy} />}
      {scoped.length > 0 && (
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Also on its own, but only on one app or site</div>
          <ul className="space-y-1.5">
            {scoped.map((g) => (
              <li key={g.id} className="flex items-center gap-2 rounded-md bg-emerald-50/60 px-3 py-1.5 text-sm">
                <span className="flex-1">
                  {g.action_label} on <b>{g.scope}</b>
                  {g.spend_limit_usd ? ` (up to ${usd(g.spend_limit_usd)})` : ""}
                  {g.level !== "goal" && <span className="text-xs text-muted"> · {levelName(g.level)}</span>}
                </span>
                {canEdit && g.level === "goal" && (
                  <Button size="sm" variant="danger" onClick={async () => { await api(`/api/grants/${g.id}`, { method: "DELETE" }); reloadGrants(); }}>
                    Ask again
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Never use these apps</div>
          <ListEditor items={listOf("app")} placeholder="e.g. linkedin" onAdd={add("app")} onRemove={remove} empty="No apps blocked." readOnly={!canEdit} lockedLabel="set elsewhere" />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Never use these websites</div>
          <ListEditor items={listOf("site")} placeholder="e.g. reddit.com" onAdd={add("site")} onRemove={remove} empty="No sites blocked." readOnly={!canEdit} lockedLabel="set elsewhere" />
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[13px] font-semibold">Rules in your own words</div>
        <ListEditor items={listOf("text")} placeholder={`e.g. "Never mention competitors"`} onAdd={add("text")} onRemove={remove} empty="No custom rules." readOnly={!canEdit} lockedLabel="set elsewhere" />
        <p className="mt-1.5 text-xs text-muted">Checked by a separate AI reviewer before every outgoing action. Strong, but not a guarantee; for a guarantee, set a kind of action to Off above.</p>
      </div>
    </div>
  );
}

function SettingsTab({ c, onSaved, onDeleted }: { c: Campaign; onSaved: () => void; onDeleted: () => void }) {
  const [form, setForm] = useState({
    name: c.name,
    goal_description: c.goal_description,
    primary_metric: c.primary_metric,
    target_value: c.target_value?.toString() ?? "",
    target_period: c.target?.period || "month",
    done_when: c.done_when || "",
    client_name: c.client_name || "",
    context: c.context || "",
    budget_total: c.budget_total.toString(),
    daily_cap: c.daily_cap?.toString() ?? "",
    cycle_hours: c.cycle_hours.toString(),
  });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function save() {
    setError(null);
    setMsg(null);
    try {
      await api(`/api/campaigns/${c.id}`, {
        method: "PATCH",
        json: {
          name: form.name,
          goal_description: form.goal_description,
          primary_metric: form.primary_metric,
          target_value: form.target_value ? Number(form.target_value) : null,
          target_period: form.target_period,
          done_when: form.done_when,
          client_name: form.client_name,
          context: form.context,
          budget_total: Number(form.budget_total),
          daily_cap: form.daily_cap ? Number(form.daily_cap) : null,
          cycle_hours: Number(form.cycle_hours),
        },
      });
      setMsg("Saved. Autopilot uses the new settings from its next work session.");
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="max-w-2xl space-y-4 p-4">
      <Field label="Name">
        <Input value={form.name} onChange={set("name")} />
      </Field>
      <Field label="Goal">
        <Textarea value={form.goal_description} onChange={set("goal_description")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="What counts as one">
          <Input value={form.done_when} onChange={set("done_when")} />
        </Field>
        <Field label="Client (for agencies)">
          <Input value={form.client_name} onChange={set("client_name")} placeholder="Leave empty if it's for you" />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Primary metric">
          <Input value={form.primary_metric} onChange={set("primary_metric")} />
        </Field>
        <Field label="Target" hint="An ongoing goal: this is what it aims for in each period.">
          <div className="flex gap-2">
            <Input type="number" value={form.target_value} onChange={set("target_value")} />
            <Select value={form.target_period} onChange={(e) => setForm({ ...form, target_period: e.target.value as Period })}>
              <option value="week">a week</option><option value="month">a month</option><option value="quarter">a quarter</option>
            </Select>
          </div>
        </Field>
        <Field label="Total budget (USD)" hint={`Already spent ${usd(c.budget.spent)}.`}>
          <Input type="number" min="1" value={form.budget_total} onChange={set("budget_total")} />
        </Field>
        <Field label="Daily cap (USD)">
          <Input type="number" min="0" value={form.daily_cap} onChange={set("daily_cap")} placeholder="No cap" />
        </Field>
        <Field label="Check in every (hours)">
          <Input type="number" min="0.5" max="72" step="0.5" value={form.cycle_hours} onChange={set("cycle_hours")} />
        </Field>
      </div>
      <BudgetCalculator cycleHours={form.cycle_hours || "6"} endDate={c.end_date ? c.end_date.slice(0, 10) : ""} onUse={(v) => setForm({ ...form, budget_total: String(v) })} />
      <Field label="Context">
        <Textarea rows={6} value={form.context} onChange={set("context")} />
      </Field>
      {error && <ErrorNote>{error}</ErrorNote>}
      {msg && <p className="text-sm text-emerald-700">{msg}</p>}
      <div className="flex justify-between border-t border-line pt-4">
        <Button variant="primary" onClick={save}>
          Save changes
        </Button>
        <Button
          variant="danger"
          onClick={async () => {
            if (confirm(`Delete the goal "${c.name}" and its whole work log? This cannot be undone.`)) {
              await api(`/api/campaigns/${c.id}`, { method: "DELETE" });
              onDeleted();
            }
          }}
        >
          <Trash2 size={15} /> Delete goal
        </Button>
      </div>
    </div>
  );
}
