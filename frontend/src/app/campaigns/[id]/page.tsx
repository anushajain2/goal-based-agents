"use client";

import { ArrowLeft, Inbox, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { ActivityFeed } from "@/components/ActivityFeed";
import { ApprovalCard } from "@/components/ApprovalCard";
import { ListEditor, Mode, PolicyMatrix } from "@/components/Guardrails";
import { MetricChart } from "@/components/MetricChart";
import { Badge, Button, Card, CardHeader, CampaignStatus, Empty, ErrorNote, Field, Input, Tabs, Textarea } from "@/components/ui";
import { ActionType, ActivityItem, api, Campaign, Exclusion, Grant, num, timeAgo, usd, useApi, UserRequest } from "@/lib/api";

type Tab = "activity" | "approvals" | "strategy" | "guardrails" | "settings";

export default function Page() {
  return (
    <Suspense>
      <CampaignPage />
    </Suspense>
  );
}

function CampaignPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "activity");
  const { data: c, error, reload } = useApi<Campaign>(`/api/campaigns/${id}`, { campaignId: id });
  const { data: activity } = useApi<ActivityItem[]>(`/api/campaigns/${id}/activity?limit=300`, { campaignId: id });
  const { data: requests, reload: reloadRequests } = useApi<UserRequest[]>(`/api/requests?status=pending&campaign_id=${id}`, { campaignId: id });
  const [busy, setBusy] = useState(false);

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

  const series = (c.metrics || []).filter((m) => m.metric.toLowerCase() === c.primary_metric.toLowerCase());
  const pct = c.budget.total ? Math.min(100, ((c.budget.spent + c.budget.reserved) / c.budget.total) * 100) : 0;
  const run = c.current_run;

  return (
    <div className="space-y-4">
      <Link href="/" className="flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={15} /> Campaigns
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold">{c.name}</h1>
            <CampaignStatus status={c.status} />
          </div>
          <p className="mt-0.5 max-w-3xl text-sm text-muted">{c.goal_description}</p>
          <p className="mt-1 text-xs text-muted">
            {run && c.status === "active" && ["queued", "running"].includes(run.status) && <span className="font-semibold text-brand-600">● Working on cycle {run.cycle_number} · </span>}
            {run?.status === "waiting" && <span className="font-semibold text-amber-700">● Waiting for you · </span>}
            {c.cycles_completed} cycles completed
            {c.status === "active" && c.next_cycle_at && ` · next check-in ${timeAgo(c.next_cycle_at)}`}
          </p>
        </div>
        <div className="flex gap-2">
          {c.status === "draft" && (
            <Button variant="success" disabled={busy} onClick={() => lifecycle("launch")}>
              <Play size={15} /> Launch
            </Button>
          )}
          {c.status === "active" && (
            <>
              <Button disabled={busy || !!(run && ["queued", "running", "waiting"].includes(run.status))} onClick={() => lifecycle("run-now")}>
                <RefreshCw size={15} /> Run a cycle now
              </Button>
              <Button disabled={busy} onClick={() => lifecycle("pause")}>
                <Pause size={15} /> Pause
              </Button>
            </>
          )}
          {c.status === "paused" && (
            <Button variant="primary" disabled={busy} onClick={() => lifecycle("resume")}>
              <Play size={15} /> Resume
            </Button>
          )}
        </div>
      </div>

      {c.status === "out_of_budget" && (
        <ErrorNote>The budget is used up, so the agent has stopped. Raise the budget in the Settings tab to continue.</ErrorNote>
      )}
      {run?.status === "failed" && run.error && <ErrorNote>Last cycle stopped: {run.error}</ErrorNote>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label={`Results (${c.primary_metric})`} value={c.results.results === null ? "—" : `${c.results.results >= 0 ? "+" : ""}${num(c.results.results)}`} sub={c.results.current !== null ? `Now ${num(c.results.current)}${c.target_value ? ` · target ${num(c.target_value)}` : ""}` : "No readings yet"} />
        <Kpi label="Cost per result" value={usd(c.cost_per_result)} sub="Total spent ÷ results" />
        <Kpi label="Amount spent" value={usd(c.budget.spent)} sub={`AI ${usd(c.budget.ai_usage)} · other ${usd(c.budget.other_spend)}`} />
        <Card className="p-4">
          <div className="text-xs font-semibold text-muted">Budget remaining</div>
          <div className="tabular mt-1 text-2xl font-bold">{usd(c.budget.remaining)}</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1 text-xs text-muted">
            of {usd(c.budget.total)}
            {c.budget.daily_cap ? ` · today ${usd(c.budget.today)} / ${usd(c.budget.daily_cap)}` : ""}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title={`${c.primary_metric.charAt(0).toUpperCase()}${c.primary_metric.slice(1)} over time`} subtitle="Recorded by the agent each cycle from the most direct source it can find." />
          <div className="p-3">
            <MetricChart points={series} label={c.primary_metric} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Current strategy" subtitle="Kept up to date by the agent" />
          <div className="max-h-64 overflow-y-auto whitespace-pre-wrap px-4 py-3 text-sm">{c.strategy || <span className="text-muted">The agent writes a strategy in its first cycle.</span>}</div>
        </Card>
      </div>

      <Card>
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "activity", label: "Activity log" },
            { key: "approvals", label: <>Approvals {requests && requests.length > 0 && <Badge tone="red">{requests.length}</Badge>}</> },
            { key: "strategy", label: "Cycles" },
            { key: "guardrails", label: "Guardrails" },
            { key: "settings", label: "Settings" },
          ]}
        />
        {tab === "activity" && <ActivityFeed items={activity || []} />}
        {tab === "approvals" && (
          <div className="space-y-3 p-4">
            {requests && requests.length === 0 && <Empty icon={<Inbox size={32} />} title="Nothing waiting for you" />}
            {(requests || []).map((r) => (
              <ApprovalCard key={r.id} req={r} onDone={() => { reloadRequests(); reload(); }} />
            ))}
          </div>
        )}
        {tab === "strategy" && <Cycles items={activity || []} />}
        {tab === "guardrails" && <GuardrailsTab campaignId={id} />}
        {tab === "settings" && <SettingsTab c={c} onSaved={reload} onDeleted={() => router.push("/")} />}
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

function Cycles({ items }: { items: ActivityItem[] }) {
  const cycles = items.filter((a) => a.kind === "cycle" && a.title.startsWith("Cycle")).reverse();
  if (!cycles.length) return <p className="px-4 py-10 text-center text-sm text-muted">No completed cycles yet.</p>;
  return (
    <ul className="divide-y divide-line">
      {cycles.map((a) => (
        <li key={a.id} className="flex gap-4 px-4 py-3 text-sm">
          <span className="w-28 shrink-0 text-xs text-muted">{new Date(a.created_at).toLocaleString()}</span>
          <span className="flex-1">{a.title}</span>
          <span className="tabular text-xs text-muted">AI {usd(a.cost_usd)}</span>
        </li>
      ))}
    </ul>
  );
}

function GuardrailsTab({ campaignId }: { campaignId: string }) {
  const { data: meta } = useApi<{ action_types: ActionType[] }>("/api/campaigns/meta", { live: false });
  const { data: exclusions, reload: reloadEx } = useApi<Exclusion[]>(`/api/exclusions?campaign_id=${campaignId}`, { campaignId });
  const { data: grants, reload: reloadGrants } = useApi<Grant[]>(`/api/grants?campaign_id=${campaignId}`, { campaignId });
  const [error, setError] = useState<string | null>(null);
  const types = meta?.action_types || [];

  const { modes, locked } = useMemo(() => {
    const modes: Record<string, Mode> = {};
    const locked: Record<string, string> = {};
    for (const t of types) modes[t.key] = t.default === "auto" ? "auto" : "ask";
    for (const g of grants || []) {
      if (g.scope) continue; // scoped grants are listed separately
      modes[g.action_type] = "auto";
      if (!g.campaign_id) locked[g.action_type] = "Don't ask (all campaigns)";
    }
    for (const e of exclusions || []) {
      if (e.kind !== "action_type") continue;
      modes[e.value] = "never";
      if (!e.campaign_id) locked[e.value] = "Never (all campaigns)";
    }
    return { modes, locked };
  }, [types, grants, exclusions]);

  async function setMode(actionType: string, mode: Mode) {
    setError(null);
    try {
      for (const e of (exclusions || []).filter((e) => e.kind === "action_type" && e.value === actionType && e.campaign_id)) {
        await api(`/api/exclusions/${e.id}`, { method: "DELETE" });
      }
      for (const g of (grants || []).filter((g) => g.action_type === actionType && !g.scope && g.campaign_id)) {
        await api(`/api/grants/${g.id}`, { method: "DELETE" });
      }
      if (mode === "never") await api("/api/exclusions", { method: "POST", json: { campaign_id: campaignId, kind: "action_type", value: actionType } });
      if (mode === "auto") {
        let limit: number | null = null;
        if (actionType === "spend_money") {
          const v = prompt("Spend without asking, up to how much per action (USD)?", "5");
          if (!v) return;
          limit = Number(v);
        }
        await api("/api/grants", { method: "POST", json: { campaign_id: campaignId, action_type: actionType, spend_limit_usd: limit } });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      reloadEx();
      reloadGrants();
    }
  }

  const listOf = (kind: string) => (exclusions || []).filter((e) => e.kind === kind).map((e) => ({ id: e.id, value: e.value, locked: !e.campaign_id }));
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
      <p className="text-sm text-muted">Changes apply immediately, including to a cycle that is running right now.</p>
      {error && <ErrorNote>{error}</ErrorNote>}
      <PolicyMatrix types={types} modes={modes} locked={locked} onChange={setMode} />
      {scoped.length > 0 && (
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Also allowed without asking</div>
          <ul className="space-y-1.5">
            {scoped.map((g) => (
              <li key={g.id} className="flex items-center gap-2 rounded-md bg-emerald-50/60 px-3 py-1.5 text-sm">
                <span className="flex-1">
                  {g.action_label} on <b>{g.scope}</b>
                  {g.spend_limit_usd ? ` (up to ${usd(g.spend_limit_usd)})` : ""}
                  {!g.campaign_id && <span className="text-xs text-muted"> · all campaigns</span>}
                </span>
                <Button size="sm" variant="danger" onClick={async () => { await api(`/api/grants/${g.id}`, { method: "DELETE" }); reloadGrants(); }}>
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Never use these apps</div>
          <ListEditor items={listOf("app")} placeholder="e.g. linkedin" onAdd={add("app")} onRemove={remove} empty="No apps blocked." />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Never use these websites</div>
          <ListEditor items={listOf("site")} placeholder="e.g. reddit.com" onAdd={add("site")} onRemove={remove} empty="No sites blocked." />
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[13px] font-semibold">Rules in your own words</div>
        <ListEditor items={listOf("text")} placeholder={`e.g. "Never mention competitors"`} onAdd={add("text")} onRemove={remove} empty="No custom rules." />
        <p className="mt-1.5 text-xs text-muted">Checked by a separate AI reviewer before every outgoing action. This is strong, but not a guarantee.</p>
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
          context: form.context,
          budget_total: Number(form.budget_total),
          daily_cap: form.daily_cap ? Number(form.daily_cap) : null,
          cycle_hours: Number(form.cycle_hours),
        },
      });
      setMsg("Saved. The agent uses the new settings from its next cycle.");
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
        <Field label="Primary metric">
          <Input value={form.primary_metric} onChange={set("primary_metric")} />
        </Field>
        <Field label="Target">
          <Input type="number" value={form.target_value} onChange={set("target_value")} />
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
            if (confirm(`Delete "${c.name}" and its whole history? This cannot be undone.`)) {
              await api(`/api/campaigns/${c.id}`, { method: "DELETE" });
              onDeleted();
            }
          }}
        >
          <Trash2 size={15} /> Delete campaign
        </Button>
      </div>
    </div>
  );
}
