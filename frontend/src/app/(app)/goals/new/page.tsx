"use client";

import { ArrowLeft, ArrowRight, Check, DollarSign, Flag, Rocket } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { ListEditor, Mode, PolicyMatrix } from "@/components/Guardrails";
import { EmployeeAvatar } from "@/components/Shell";
import { AgentAvatar } from "@/components/team";
import { Button, Card, cx, ErrorNote, Field, Input, Select, Textarea } from "@/components/ui";
import { CATEGORY_ICON, FitBadge, UseCaseLibrary } from "@/components/UseCaseLibrary";
import { ActionType, api, Campaign, CATEGORY_DEPARTMENT, OrgInfo, useApi } from "@/lib/api";
import { findUseCase, metricFrom, targetFrom, UseCase } from "@/lib/useCases";

const CHANNELS = ["Email", "LinkedIn", "X / Twitter", "Instagram", "Reddit", "Product Hunt", "Hacker News", "Communities", "Newsletters", "Directories", "My website", "Calendar"];
const STEPS = ["Choose a goal", "The goal", "Budget", "Context", "Permissions", "Review"];

type Exclusion = { id: string; kind: "app" | "site" | "text"; value: string };

export default function Page() {
  return (
    <Suspense>
      <NewGoal />
    </Suspense>
  );
}

function NewGoal() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: meta } = useApi<{ action_types: ActionType[] }>("/api/campaigns/meta", { live: false });
  const { data: builtIn } = useApi<{ rules: string[] }>("/api/guardrails/built-in", { live: false });
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false });
  const [agentId, setAgentId] = useState(params.get("agent") || "");
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [uc, setUc] = useState<UseCase | null>(null);
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");
  const [metric, setMetric] = useState("");
  const [target, setTarget] = useState("");
  const [doneWhen, setDoneWhen] = useState("");
  const [client, setClient] = useState("");
  const [budget, setBudget] = useState("25");
  const [dailyCap, setDailyCap] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cycleHours, setCycleHours] = useState("6");
  const [context, setContext] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [modes, setModes] = useState<Record<string, Mode>>({});
  const [spendLimit, setSpendLimit] = useState("");
  const [exclusions, setExclusions] = useState<Exclusion[]>([]);

  function choose(u: UseCase | null) {
    setUc(u);
    if (u) {
      setDescription(u.goal);
      setDoneWhen(u.doneWhen);
      setMetric(metricFrom(u.doneWhen));
      const t = targetFrom(u.goal);
      setTarget(t !== null ? String(t) : "");
      setName("");
    } else {
      setDescription("");
      setDoneWhen("");
      setMetric("");
      setTarget("");
    }
    setError(null);
    setStep(1);
  }

  useEffect(() => {
    const u = findUseCase(params.get("uc"));
    if (u) choose(u);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // AI employees this person may give goals to: their own departments' (admins: everyone's).
  const assignable = useMemo(
    () =>
      (org?.departments || [])
        .filter((d) => org?.me.is_admin || org?.me.department_ids.includes(d.id))
        .flatMap((d) => d.agents.map((a) => ({ ...a, department: d }))),
    [org],
  );
  const assignee = assignable.find((a) => a.id === agentId);

  // Suggest the AI employee whose department usually handles this kind of goal.
  useEffect(() => {
    if (!assignable.length || assignable.some((a) => a.id === agentId)) return;
    const kind = uc ? CATEGORY_DEPARTMENT[uc.categoryKey] : undefined;
    const match = assignable.find((a) => a.department.kind === kind) || assignable[0];
    setAgentId(match.id);
  }, [assignable, uc, agentId]);

  const types = meta?.action_types || [];
  const effective = useMemo(
    () => Object.fromEntries(types.map((t) => [t.key, modes[t.key] ?? (t.default === "auto" ? "auto" : "ask")])) as Record<string, Mode>,
    [types, modes],
  );

  function valid(s: number): string | null {
    if (s === 1) {
      if (!agentId) return org && !assignable.length ? "You're not in a department with an AI employee yet. Ask an admin to add you to one." : "Choose who works on it.";
      if (!description.trim()) return "Describe the goal.";
      if (!metric.trim()) return "Say what gets counted, e.g. \"meetings held\".";
    }
    if (s === 2 && !(Number(budget) > 0)) return "Set a budget greater than $0.";
    if (s === 4 && effective.spend_money === "auto" && !(Number(spendLimit) > 0)) return "Set a per-action limit for spending without asking.";
    return null;
  }

  function next() {
    const v = valid(step);
    if (v) return setError(v);
    setError(null);
    setStep((x) => Math.min(STEPS.length - 1, x + 1));
  }

  async function submit(launch: boolean) {
    for (let s = 1; s < STEPS.length; s++) {
      const v = valid(s);
      if (v) {
        setStep(s);
        return setError(v);
      }
    }
    setBusy(true);
    setError(null);
    const body = {
      name: (name.trim() || description.trim()).slice(0, 200),
      goal_type: uc?.categoryKey || "custom",
      goal_description: description.trim(),
      primary_metric: metric.trim(),
      target_value: target ? Number(target) : null,
      done_when: doneWhen.trim(),
      category: uc?.category || "",
      use_case: uc?.sub || "",
      client_name: client.trim(),
      context,
      channels,
      budget_total: Number(budget),
      daily_cap: dailyCap ? Number(dailyCap) : null,
      end_date: endDate ? new Date(endDate + "T23:59:00").toISOString() : null,
      cycle_hours: Number(cycleHours),
      exclusions: [
        ...types.filter((t) => effective[t.key] === "never").map((t) => ({ kind: "action_type", value: t.key })),
        ...exclusions.map((e) => ({ kind: e.kind, value: e.value })),
      ],
      grants: types
        .filter((t) => t.default === "ask" && effective[t.key] === "auto")
        .map((t) => ({ action_type: t.key, spend_limit_usd: t.key === "spend_money" ? Number(spendLimit) : null })),
      launch,
      agent_id: agentId || null,
    };
    try {
      const c = await api<Campaign>("/api/campaigns", { method: "POST", json: body });
      router.push(`/goals/${c.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const addEx = (kind: Exclusion["kind"]) => (value: string) => setExclusions((x) => [...x, { id: crypto.randomUUID(), kind, value }]);
  const removeEx = (id: string) => setExclusions((x) => x.filter((e) => e.id !== id));

  if (step === 0) {
    return (
      <div>
        <button onClick={() => router.back()} className="mb-3 flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft size={15} /> Back</button>
        <div className="mb-5 flex items-center gap-3">
          <EmployeeAvatar size={40} />
          <div>
            <h1 className="text-2xl font-bold">{assignee ? `What should ${assignee.name} work on?` : "What should your AI employee work on?"}</h1>
            <p className="text-sm text-muted">Pick a goal with a clear finish line, or describe your own. You can adjust everything on the next steps.</p>
          </div>
        </div>
        <UseCaseLibrary onPick={choose} onCustom={() => choose(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={() => setStep(0)} className="mb-3 flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft size={15} /> Choose a different goal</button>
      <h1 className="mb-1 text-2xl font-bold">Set up the goal</h1>
      {uc && (
        <p className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="text-gray-400">{CATEGORY_ICON[uc.categoryKey]}</span> {uc.category} · {uc.sub} <FitBadge fit={uc.fit} />
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-[190px_1fr]">
        <ol className="flex gap-2 overflow-x-auto md:flex-col md:gap-1">
          {STEPS.slice(1).map((s, idx) => {
            const i = idx + 1;
            return (
              <li key={s}>
                <button
                  onClick={() => (i < step || !valid(step) ? setStep(i) : null)}
                  className={cx("flex w-full items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm font-semibold", i === step ? "bg-white text-brand-700 shadow-sm ring-1 ring-line" : "text-muted hover:text-ink")}
                >
                  <span className={cx("grid h-5 w-5 place-items-center rounded-full text-[11px]", i < step ? "bg-emerald-600 text-white" : i === step ? "bg-brand-500 text-white" : "bg-gray-200")}>
                    {i < step ? <Check size={12} /> : i}
                  </span>
                  {s}
                </button>
              </li>
            );
          })}
        </ol>

        <Card className="p-5">
          {step === 1 && (
            <div className="space-y-5">
              <Field label="Who works on it" hint={assignee ? `Approvals go to the ${assignee.department.name} team${assignee.department.people.length ? `: ${assignee.department.people.map((p) => p.name || p.email).join(", ")}` : " (nobody's in it yet, so admins)"}.` : "Each AI employee belongs to a department. Its approvals go to the people in that department."}>
                <div className="grid gap-2 sm:grid-cols-2">
                  {assignable.map((a) => (
                    <button key={a.id} type="button" onClick={() => setAgentId(a.id)}
                      className={cx("flex items-center gap-3 rounded-lg border px-3 py-2 text-left", a.id === agentId ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-line hover:border-gray-400")}>
                      <AgentAvatar name={a.name} size={30} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{a.name}</span>
                        <span className="block truncate text-xs text-muted">{a.department.name}{a.title ? ` · ${a.title}` : ""} · {a.active_goals} active</span>
                      </span>
                    </button>
                  ))}
                  {org && !assignable.length && <p className="text-sm text-amber-700">You&apos;re not in a department yet. Ask an admin to add you to one on the Team page.</p>}
                </div>
              </Field>
              <Field label="The goal" hint="Say it the way you'd brief a new hire: who, what, how many.">
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Book 15 interviews with heads of operations at logistics companies in the UK" />
              </Field>
              <Field label="Counts as done when" hint="Autopilot only counts a result when this is true. Be specific: this is how you'll judge its work.">
                <div className="relative">
                  <Flag size={14} className="absolute left-3 top-3 text-muted" />
                  <Input className="pl-8" value={doneWhen} onChange={(e) => setDoneWhen(e.target.value)} placeholder="e.g. Interview held on calendar with a matching person" />
                </div>
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="What gets counted" hint="The number shown as progress.">
                  <Input value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="e.g. interviews held" />
                </Field>
                <Field label="Target">
                  <Input type="number" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="e.g. 15" />
                </Field>
                <Field label="Short name (optional)">
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. UK ops interviews" />
                </Field>
                <Field label="For a client? (agencies)" hint="Leave empty if it's for your own company.">
                  <Input value={client} onChange={(e) => setClient(e.target.value)} placeholder="Client name" />
                </Field>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">Budget & schedule</h2>
                <p className="text-sm text-muted">
                  The budget covers everything this goal costs: mostly Autopilot&apos;s own AI usage, plus any ads or purchases you allow. It&apos;s a hard
                  limit. When it runs out, work pauses. You&apos;ll see the cost of every work session in the work log.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Total budget (USD)">
                  <div className="relative">
                    <DollarSign size={15} className="absolute left-2.5 top-2.5 text-muted" />
                    <Input className="pl-7" type="number" min="1" step="1" value={budget} onChange={(e) => setBudget(e.target.value)} />
                  </div>
                </Field>
                <Field label="Daily cap (optional)" hint="Work pauses for the day when reached.">
                  <div className="relative">
                    <DollarSign size={15} className="absolute left-2.5 top-2.5 text-muted" />
                    <Input className="pl-7" type="number" min="0" step="0.5" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)} placeholder="No cap" />
                  </div>
                </Field>
                <Field label="Deadline (optional)">
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                </Field>
                <Field label="Check in and work on it about every" hint="Autopilot may go a bit sooner or later (half to double this) depending on results.">
                  <Select value={cycleHours} onChange={(e) => setCycleHours(e.target.value)}>
                    {["1", "3", "6", "12", "24", "48"].map((h) => <option key={h} value={h}>{h} hour{h === "1" ? "" : "s"}</option>)}
                  </Select>
                </Field>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">Brief your employee</h2>
                <p className="text-sm text-muted">The more Autopilot knows, the better its outreach and choices.</p>
              </div>
              <Field label="About the company, offer and audience" hint="Links, ideal customer, what makes you different, prices, tone of voice, people or companies to avoid.">
                <Textarea rows={8} value={context} onChange={(e) => setContext(e.target.value)} placeholder={"Company: ...\nWebsite: https://...\nWho we sell to: ...\nWhat we offer: ...\nTone: friendly, concise, no hype\nCalendar link for meetings: ..."} />
              </Field>
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Channels it should use (optional)</div>
                <div className="flex flex-wrap gap-2">
                  {CHANNELS.map((ch) => {
                    const on = channels.includes(ch);
                    return (
                      <button key={ch} type="button" onClick={() => setChannels(on ? channels.filter((c) => c !== ch) : [...channels, ch])}
                        className={cx("rounded-full border px-3 py-1 text-sm", on ? "border-brand-500 bg-brand-50 font-semibold text-brand-700" : "border-line hover:border-gray-400")}>
                        {ch}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-1.5 text-xs text-muted">Leave empty to let Autopilot choose. It uses connected apps where possible, otherwise your Agent Chrome.</p>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-lg font-semibold">What may it do on its own?</h2>
                <p className="text-sm text-muted">
                  By default Autopilot asks you before anything important. You can also tick &quot;don&apos;t ask me next time&quot; on any approval later.
                </p>
              </div>
              <PolicyMatrix types={types} modes={effective} onChange={(k, m) => setModes({ ...modes, [k]: m })} spendLimit={spendLimit} onSpendLimit={setSpendLimit} />
              <div className="grid gap-5 md:grid-cols-2">
                <div>
                  <div className="mb-1.5 text-[13px] font-semibold">Never use these apps</div>
                  <ListEditor items={exclusions.filter((e) => e.kind === "app")} placeholder="e.g. linkedin" onAdd={addEx("app")} onRemove={removeEx} empty="No apps blocked." />
                </div>
                <div>
                  <div className="mb-1.5 text-[13px] font-semibold">Never use these websites</div>
                  <ListEditor items={exclusions.filter((e) => e.kind === "site")} placeholder="e.g. reddit.com" onAdd={addEx("site")} onRemove={removeEx} empty="No sites blocked." />
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Rules in your own words</div>
                <ListEditor items={exclusions.filter((e) => e.kind === "text")} placeholder={`e.g. "Never contact our existing customers" or "Don't mention pricing"`} onAdd={addEx("text")} onRemove={removeEx} empty="No custom rules." />
                <p className="mt-1.5 text-xs text-muted">Every outgoing action is checked against these by a separate AI reviewer first. Strong, but not a guarantee. For a guarantee, set a whole category to &quot;Never&quot; above.</p>
              </div>
              {builtIn && (
                <details className="rounded-md bg-gray-50 px-3 py-2 text-sm">
                  <summary className="cursor-pointer font-semibold">Rules that always apply ({builtIn.rules.length})</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{builtIn.rules.map((r) => <li key={r}>{r}</li>)}</ul>
                </details>
              )}
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Review</h2>
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <Item k="Who works on it" v={assignee ? `${assignee.name} · ${assignee.department.name}` : "—"} />
                <Item k="Approvals go to" v={assignee ? (assignee.department.people.map((p) => p.name || p.email).join(", ") || "Admins (nobody in the team yet)") : "—"} />
                <Item k="Goal" v={description || "—"} />
                <Item k="Counts as done when" v={doneWhen || "—"} />
                <Item k="Progress measured as" v={`${metric}${target ? ` (target ${target})` : ""}`} />
                <Item k="For" v={client || "Your company"} />
                <Item k="Budget" v={`$${budget}${dailyCap ? ` · $${dailyCap}/day cap` : ""}${endDate ? ` · deadline ${endDate}` : ""}`} />
                <Item k="Works on it" v={`About every ${cycleHours}h`} />
                <Item k="Never" v={types.filter((t) => effective[t.key] === "never").map((t) => t.label).join(", ") || "—"} />
                <Item k="Without asking" v={types.filter((t) => t.default === "ask" && effective[t.key] === "auto").map((t) => t.label).join(", ") || "Nothing: it asks first"} />
              </dl>
              <p className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">
                When you start, {assignee?.name || "your AI employee"} plans its first work session, then gets going. It asks the{" "}
                {assignee?.department.name || "department"} team before anything that needs an OK, and every step shows up in the work log.
              </p>
            </div>
          )}

          {error && <div className="mt-4"><ErrorNote>{error}</ErrorNote></div>}

          <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
            <Button variant="ghost" onClick={() => setStep(step - 1)}><ArrowLeft size={15} /> Back</Button>
            {step < STEPS.length - 1 ? (
              <Button variant="primary" onClick={next}>Next <ArrowRight size={15} /></Button>
            ) : (
              <div className="flex gap-2">
                <Button disabled={busy} onClick={() => submit(false)}>Save for later</Button>
                <Button variant="primary" disabled={busy} onClick={() => submit(true)}><Rocket size={15} /> Start working on it</Button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-muted">{k}</dt>
      <dd className="mt-0.5">{v}</dd>
    </div>
  );
}
