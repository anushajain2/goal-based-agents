"use client";

import { ArrowRight, Check, ChevronDown, CircleAlert, Flag, Loader2, Minus, Play, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CompanyProfileCard } from "@/components/CompanyProfile";
import { ModeBadge } from "@/components/GoalPlan";
import { StartGoal } from "@/components/StartGoal";
import { AgentAvatar } from "@/components/team";
import { Badge, Button, Card, cx, ErrorNote, Field, Input, Textarea } from "@/components/ui";
import { api, Campaign, SetupInfo, SetupStep, usd, useApi } from "@/lib/api";

// Kinds of action that never change anything outside Autopilot, so they run without asking.
const AUTO_KINDS = new Set(["research", "read_data", "create_draft"]);

export default function SetupPage() {
  const router = useRouter();
  const [info, setInfo] = useState<SetupInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInfo(await api<SetupInfo>("/api/org/setup"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const status = info?.setup?.status;
  const working = status === "queued" || status === "running";
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!working) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [working, load]);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!info) return <p className="text-muted">Loading…</p>;

  const name = info.org.name;
  if (!info.setup) {
    return (
      <div className="mx-auto max-w-2xl">
        <Card className="p-6">
          <h1 className="text-xl font-bold">Research {name} and set up your AI team</h1>
          <p className="mt-1 text-sm text-muted">Autopilot reads your website and researches your company, then suggests AI employees and goals that fit.</p>
          <RetryForm info={info} onStarted={load} label="Start research" />
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            {working ? `Getting to know ${name}…` : status === "done" ? `Your AI team for ${name}` : `Setting up ${name} didn't finish`}
          </h1>
          <p className="text-sm text-muted">
            {working
              ? "This usually takes 1 to 3 minutes. You can leave this page: it keeps going and the results will be here."
              : status === "done"
                ? "Here's what we learned, and the AI employees and goals we suggest. Nothing runs until you start a goal."
                : "You can try again, or start with a basic team and set it up yourself."}
          </p>
        </div>
        {status === "done" && (
          <Link href="/team?welcome=1" className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600">
            Go to my team <ArrowRight size={15} />
          </Link>
        )}
      </div>

      <Steps steps={info.setup.steps} cost={info.setup.cost_usd} compact={status === "done"} />

      {working && (info.org.website || info.org.description) && (
        <Card className="p-4 text-sm">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">What you told us</div>
          {info.org.website && <p className="text-brand-700">{info.org.website}</p>}
          {info.org.description && <p className="mt-1 text-gray-700">{info.org.description}</p>}
        </Card>
      )}

      {status === "failed" && (
        <Card className="space-y-4 p-5">
          <ErrorNote>{info.setup.error || "Something went wrong."}</ErrorNote>
          {info.can_run ? (
            <>
              <RetryForm info={info} onStarted={load} label="Try again" />
              {!info.has_team && (
                <button
                  onClick={async () => { await api("/api/org/setup/basic", { method: "POST" }); router.push("/team?welcome=1&basic=1"); }}
                  className="text-sm font-semibold text-muted hover:text-ink"
                >
                  Or start with a basic team (Sales, Marketing, Customer Research) →
                </button>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">Ask an admin of {name} to try again.</p>
          )}
        </Card>
      )}

      {status === "done" && info.setup.plan && (
        <>
          <CompanyProfileCard profile={info.org.profile || info.setup.plan.profile} name={name} />
          <SuggestedTeam info={info} />
        </>
      )}
    </div>
  );
}

function Steps({ steps, cost, compact }: { steps: SetupStep[]; cost: number; compact: boolean }) {
  const [open, setOpen] = useState(!compact);
  useEffect(() => setOpen(!compact), [compact]);
  return (
    <Card className="p-4">
      {compact && (
        <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left text-sm">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-600 text-white"><Check size={14} /></span>
          <span className="flex-1 font-semibold">Research done</span>
          <span className="text-xs text-muted">Research cost {usd(cost)}</span>
          <ChevronDown size={16} className={cx("text-muted transition", open && "rotate-180")} />
        </button>
      )}
      {open && (
        <ol className={cx("space-y-3", compact && "mt-3 border-t border-line pt-3")}>
          {steps.map((s) => (
            <li key={s.key} className="flex items-start gap-3">
              <StepIcon status={s.status} />
              <div className="min-w-0 flex-1">
                <div className={cx("text-[14px] font-semibold", s.status === "pending" && "text-muted")}>{s.label}</div>
                {s.detail && <div className="text-xs text-muted">{s.detail}</div>}
              </div>
            </li>
          ))}
          {!compact && cost > 0 && <li className="pl-9 text-xs text-muted">Research cost so far: {usd(cost)}. Paid by the organization, not from any goal&apos;s budget.</li>}
        </ol>
      )}
    </Card>
  );
}

function StepIcon({ status }: { status: SetupStep["status"] }) {
  const base = "grid h-6 w-6 shrink-0 place-items-center rounded-full";
  if (status === "done") return <span className={cx(base, "bg-emerald-600 text-white")}><Check size={14} /></span>;
  if (status === "running") return <span className={cx(base, "bg-brand-50 text-brand-600")}><Loader2 size={15} className="animate-spin" /></span>;
  if (status === "failed") return <span className={cx(base, "bg-amber-100 text-amber-700")}><CircleAlert size={14} /></span>;
  if (status === "skipped") return <span className={cx(base, "bg-gray-100 text-gray-400")}><Minus size={14} /></span>;
  return <span className={cx(base, "border-2 border-gray-200")} />;
}

function SuggestedTeam({ info }: { info: SetupInfo }) {
  const { data: goals, reload } = useApi<Campaign[]>("/api/campaigns");
  const [busy, setBusy] = useState<string | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const plan = info.setup!.plan!;
  const createdIds = info.setup!.created?.goals;
  const mine = useMemo(() => {
    const created = new Set(createdIds || []);
    return (goals || []).filter((g) => created.has(g.id));
  }, [goals, createdIds]);
  const drafts = mine.filter((g) => g.status === "draft" && g.can_manage !== false);
  const draftBudget = drafts.reduce((t, g) => t + g.budget.total, 0);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">Your AI employees and their first goals</h2>
          <p className="text-sm text-muted">
            A few goals per function, picked for where {info.org.name} is right now. Start the ones you want; remove the rest. Each goal&apos;s
            budget is a hard limit, and nothing is spent until you start it.
          </p>
        </div>
        {drafts.length > 1 && (
          <Button variant="primary" disabled={!!busy} onClick={() => setStarting(drafts)}>
            <Play size={15} /> Start all {drafts.length} ({usd(draftBudget)})
          </Button>
        )}
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); reload(); }} />}

      {plan.departments.map((d) => {
        const deptGoals = mine.filter((g) => g.department?.name.toLowerCase() === d.name.toLowerCase() || d.goals.some((p) => p.name === g.name));
        const agent = deptGoals[0]?.agent;
        return (
          <Card key={d.name}>
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
              <AgentAvatar name={agent?.name || `${d.name} Agent`} size={40} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  {agent ? <Link href={`/team/agents/${agent.id}`} className="text-[15px] font-bold hover:underline">{agent.name}</Link> : <span className="text-[15px] font-bold">{d.name} Agent</span>}
                  <Badge>{d.name}</Badge>
                  {d.agent_title && <span className="text-xs text-muted">{d.agent_title}</span>}
                </div>
                {d.why && <p className="text-[13px] text-gray-700">{d.why}</p>}
              </div>
            </div>
            <ul className="divide-y divide-line">
              {d.goals.map((p) => {
                const g = deptGoals.find((x) => x.name === p.name) || mine.find((x) => x.name === p.name);
                return (
                  <li key={p.name} className="grid gap-3 px-4 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        {g ? <Link href={`/goals/${g.id}`} className="font-semibold hover:text-brand-600 hover:underline">{p.name}</Link> : <span className="font-semibold text-muted line-through">{p.name}</span>}
                        {g && g.status !== "draft" && <Badge tone="green">Started</Badge>}
                      </div>
                      <p className="mt-0.5 text-[13px] text-gray-700">{p.goal_description}</p>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                        {p.done_when && <span className="inline-flex items-center gap-1"><Flag size={11} /> Counts when: {p.done_when}</span>}
                        <span>Target: {p.target_value ? `${p.target_value} ${p.primary_metric}` : p.primary_metric}</span>
                        <span>Budget {usd(p.budget_usd)}{p.budget_basis ? ` (${p.budget_basis.sessions} sessions × ~${usd(p.budget_basis.per_session_usd)}${p.budget_basis.paid_spend_usd ? ` + ${usd(p.budget_basis.paid_spend_usd)} spend` : ""})` : ""}</span>
                      </div>
                      {p.why && <p className="mt-1.5 flex gap-1.5 text-xs text-brand-700"><Sparkles size={12} className="mt-0.5 shrink-0" /> {p.why}</p>}
                      {(p.steps?.length || 0) > 0 && (
                        <details className="mt-2 text-xs">
                          <summary className="cursor-pointer font-semibold text-muted">What it will do ({p.steps!.length} steps)</summary>
                          <ol className="mt-1.5 space-y-1">
                            {p.steps!.map((st, i) => (
                              <li key={i} className="flex flex-wrap items-center gap-2">
                                <span className="text-muted">{i + 1}.</span>
                                <span className="min-w-0 flex-1 text-gray-700">{st.text}</span>
                                <ModeBadge mode={AUTO_KINDS.has(st.action_type) ? "auto" : "ask"} team={d.name} />
                              </li>
                            ))}
                          </ol>
                        </details>
                      )}
                    </div>
                    {g && g.status === "draft" && g.can_manage !== false && (
                      <div className="flex items-start gap-2">
                        <Button size="sm" variant="primary" disabled={!!busy} onClick={() => setStarting([g])}>
                          <Play size={13} /> Start
                        </Button>
                        <Button size="sm" variant="ghost" disabled={!!busy} title="Remove this suggestion" onClick={() => confirm(`Remove "${g.name}"?`) && act(g.id, () => api(`/api/campaigns/${g.id}`, { method: "DELETE" }))}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
        );
      })}
    </div>
  );
}

function RetryForm({ info, onStarted, label }: { info: SetupInfo; onStarted: () => void; label: string }) {
  const [website, setWebsite] = useState(info.org.website);
  const [description, setDescription] = useState(info.org.description);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!info.can_research) {
    return <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">Add <code>ANTHROPIC_API_KEY</code> to the <code>.env</code> file and restart Autopilot to research your company.</p>;
  }
  return (
    <form className="mt-4 space-y-3" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setErr(null);
      try {
        await api("/api/org/setup", { method: "POST", json: { website, description } });
        onStarted();
      } catch (e2) {
        setErr((e2 as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <Field label="Website"><Input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="acme.com" /></Field>
      <Field label="What the company does"><Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      {err && <ErrorNote>{err}</ErrorNote>}
      <Button type="submit" variant="primary" disabled={busy}>{label === "Try again" ? <RefreshCw size={15} /> : <Sparkles size={15} />} {label}</Button>
    </form>
  );
}

