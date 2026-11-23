"use client";

import { ArrowRight, Check, ChevronDown, CircleAlert, Loader2, Minus, Play, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CompanyProfileCard } from "@/components/CompanyProfile";
import { GoalPanel } from "@/components/GoalPanel";
import { OrgChart } from "@/components/OrgChart";
import { StartGoal } from "@/components/StartGoal";
import { AgentAvatar } from "@/components/team";
import { Badge, Button, Card, cx, ErrorNote, Field, Input, Textarea } from "@/components/ui";
import { api, Campaign, CompanyProfile, OrgInfo, SetupInfo, SetupStep, usd, useApi } from "@/lib/api";

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
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            {working ? `Getting to know ${name}…` : status === "done" ? "Meet your AI team" : `Setting up ${name} didn't finish`}
          </h1>
          <p className="text-sm text-muted">
            {working
              ? "This usually takes 1 to 3 minutes. You can leave this page: it keeps going and the results will be here."
              : status === "done"
                ? `Built for ${name} from your website and public information. Nothing runs, and nothing is spent, until you start a goal.`
                : "You can try again, or start with a basic team and set it up yourself."}
          </p>
        </div>
        {status === "done" && (
          <Link href="/team?welcome=1" className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-line bg-white px-4 text-sm font-semibold hover:bg-gray-50">
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
          <Learned profile={info.org.profile || info.setup.plan.profile} name={name} />
          <SuggestedTeam info={info} />
        </>
      )}
    </div>
  );
}

function Learned({ profile, name }: { profile: CompanyProfile; name: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-line bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 px-4 py-3 text-left">
        <Sparkles size={16} className="mt-0.5 shrink-0 text-brand-600" />
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-bold uppercase tracking-wide text-muted">What we learned about {name}</span>
          <span className="block text-[13.5px] leading-snug">{profile.summary}</span>
        </span>
        <ChevronDown size={16} className={cx("mt-1 shrink-0 text-muted transition", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-line p-2"><CompanyProfileCard profile={profile} name={name} /></div>}
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
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org");
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const plan = info.setup!.plan!;
  const createdIds = info.setup!.created?.goals;
  const mine = useMemo(() => {
    const created = new Set(createdIds || []);
    return (goals || []).filter((g) => created.has(g.id));
  }, [goals, createdIds]);
  const picksNames = new Set(plan.departments.flatMap((d) => d.goals.filter((g) => g.start_here).map((g) => g.name)));
  // Older setups have no picks: suggest the first goal of the top two functions.
  if (picksNames.size === 0) plan.departments.slice(0, 2).forEach((d) => d.goals[0] && picksNames.add(d.goals[0].name));
  const picks = mine.filter((g) => picksNames.has(g.name) && g.status === "draft" && g.can_manage !== false);
  const picksBudget = picks.reduce((t, g) => t + g.budget.total, 0);
  const oldBudgets = mine.filter((g) => g.status === "draft" && !g.budget_basis?.starter);

  async function starterBudgets() {
    setErr(null);
    try {
      await api("/api/org/setup/starter-budgets", { method: "POST" });
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  const refresh = () => { reload(); reloadOrg(); };

  return (
    <div className="space-y-6">
      {err && <ErrorNote>{err}</ErrorNote>}
      {oldBudgets.length > 0 && info.can_run && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
          <span className="min-w-0 flex-1">
            Start small: give these goals a one-week budget first ({usd(oldBudgets.reduce((t, g) => t + g.budget.total, 0))} now), and add more once you see results.
          </span>
          <Button size="sm" variant="primary" onClick={starterBudgets}>Use one-week budgets</Button>
        </div>
      )}

      {picks.length > 0 && (
        <section>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold">Start here</h2>
              <p className="text-sm text-muted">The {picks.length === 1 ? "goal" : `${picks.length} goals`} most likely to show results fastest. Each runs for a week on a small budget.</p>
            </div>
            {picks.length > 1 && (
              <Button variant="primary" onClick={() => setStarting(picks)}><Play size={15} /> Start {picks.length === 2 ? "both" : `these ${picks.length}`} · {usd(picksBudget)} for the week</Button>
            )}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {picks.map((g) => (
              <div key={g.id} className="flex flex-col rounded-xl border border-line bg-white p-4 shadow-sm">
                <div className="mb-2 flex items-center gap-2">
                  {g.agent && <AgentAvatar name={g.agent.name} size={26} />}
                  <span className="text-xs font-semibold text-muted">{g.agent?.name}</span>
                </div>
                <div className="text-[15px] font-bold leading-snug">{g.name}</div>
                <div className="mt-2 flex-1 rounded-lg bg-brand-50 px-3 py-2">
                  <div className="text-[10.5px] font-bold uppercase tracking-wide text-brand-700">{g.first_deliverable ? "In your first week you get" : "The goal"}</div>
                  <div className="mt-0.5 text-[13px] leading-snug">{g.first_deliverable || g.goal_description}</div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="primary" onClick={() => setStarting([g])}><Play size={13} /> Start · {usd(g.budget.total)}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setPanel(g)}>How it works</Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-lg font-bold">Your team</h2>
        <p className="mb-3 text-sm text-muted">
          AI employees work in departments and report to the department&apos;s head, who approves their work. No heads yet? Approvals come to you.
          Click any goal to see what it does; change the team whenever you like.
        </p>
        {org && <OrgChart org={org} goals={mine} onGoalClick={setPanel} onChanged={refresh} />}
      </section>

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); refresh(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); refresh(); }} />}
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

