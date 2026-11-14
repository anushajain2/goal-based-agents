"use client";

import { ArrowLeft, ArrowRight, Check, DollarSign, Eye, Megaphone, MousePointerClick, Rocket, ShoppingBag, Sparkles, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";

import { ListEditor, Mode, PolicyMatrix } from "@/components/Guardrails";
import { Button, Card, cx, ErrorNote, Field, Input, Select, Textarea } from "@/components/ui";
import { ActionType, api, Campaign, useApi } from "@/lib/api";

const GOALS: { key: string; label: string; metric: string; icon: ReactNode; example: string }[] = [
  { key: "sales", label: "Sell more of my product", metric: "sales", icon: <ShoppingBag size={20} />, example: "Sell more copies of my Notion template on Gumroad" },
  { key: "followers", label: "Grow my followers", metric: "followers", icon: <Users size={20} />, example: "Grow my X account @handle with founders and indie hackers" },
  { key: "traffic", label: "Drive website traffic", metric: "website visits", icon: <MousePointerClick size={20} />, example: "Get more visitors to my blog at example.com" },
  { key: "leads", label: "Get leads or sign-ups", metric: "sign-ups", icon: <Megaphone size={20} />, example: "Get beta sign-ups for my app's waitlist" },
  { key: "awareness", label: "Build awareness", metric: "impressions", icon: <Eye size={20} />, example: "Get my brand in front of designers in Europe" },
  { key: "custom", label: "Something else", metric: "", icon: <Sparkles size={20} />, example: "Describe your goal in your own words" },
];

const CHANNELS = ["X / Twitter", "LinkedIn", "Instagram", "Reddit", "Product Hunt", "Hacker News", "YouTube", "TikTok", "Blog", "Email", "Gumroad", "Shopify"];

const STEPS = ["Goal", "Budget & schedule", "Context & channels", "Guardrails", "Review"];

type Exclusion = { id: string; kind: "app" | "site" | "text"; value: string };

export default function NewCampaign() {
  const router = useRouter();
  const { data: meta } = useApi<{ action_types: ActionType[] }>("/api/campaigns/meta", { live: false });
  const { data: builtIn } = useApi<{ rules: string[] }>("/api/guardrails/built-in", { live: false });
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [goal, setGoal] = useState("followers");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [metric, setMetric] = useState("followers");
  const [target, setTarget] = useState("");
  const [budget, setBudget] = useState("50");
  const [dailyCap, setDailyCap] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cycleHours, setCycleHours] = useState("6");
  const [context, setContext] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [modes, setModes] = useState<Record<string, Mode>>({});
  const [spendLimit, setSpendLimit] = useState("");
  const [exclusions, setExclusions] = useState<Exclusion[]>([]);

  const types = meta?.action_types || [];
  useEffect(() => {
    const g = GOALS.find((x) => x.key === goal);
    if (g) setMetric(g.metric);
  }, [goal]);

  const effective = useMemo(
    () => Object.fromEntries(types.map((t) => [t.key, modes[t.key] ?? (t.default === "auto" ? "auto" : "ask")])) as Record<string, Mode>,
    [types, modes],
  );

  function valid(s: number): string | null {
    if (s === 0) {
      if (!description.trim()) return "Describe your goal.";
      if (!metric.trim()) return "Name the number you want to grow.";
    }
    if (s === 1 && !(Number(budget) > 0)) return "Set a budget greater than $0.";
    if (s === 3 && effective.spend_money === "auto" && !(Number(spendLimit) > 0)) return "Set a per-action limit for spending without asking.";
    return null;
  }

  function next() {
    const v = valid(step);
    if (v) return setError(v);
    setError(null);
    setStep((x) => Math.min(STEPS.length - 1, x + 1));
  }

  async function submit(launch: boolean) {
    for (let s = 0; s < STEPS.length; s++) {
      const v = valid(s);
      if (v) {
        setStep(s);
        return setError(v);
      }
    }
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim() || description.trim().slice(0, 60),
      goal_type: goal,
      goal_description: description.trim(),
      primary_metric: metric.trim(),
      target_value: target ? Number(target) : null,
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
    };
    try {
      const c = await api<Campaign>("/api/campaigns", { method: "POST", json: body });
      router.push(`/campaigns/${c.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const addEx = (kind: Exclusion["kind"]) => (value: string) => setExclusions((x) => [...x, { id: crypto.randomUUID(), kind, value }]);
  const removeEx = (id: string) => setExclusions((x) => x.filter((e) => e.id !== id));

  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={() => router.push("/")} className="mb-3 flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={15} /> Campaigns
      </button>
      <h1 className="mb-4 text-2xl font-bold">Create campaign</h1>

      <div className="grid gap-4 md:grid-cols-[200px_1fr]">
        <ol className="flex gap-2 overflow-x-auto md:flex-col md:gap-1">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button
                onClick={() => (i < step || !valid(step) ? setStep(i) : null)}
                className={cx(
                  "flex w-full items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm font-semibold",
                  i === step ? "bg-white text-brand-700 shadow-sm ring-1 ring-line" : "text-muted hover:text-ink",
                )}
              >
                <span className={cx("grid h-5 w-5 place-items-center rounded-full text-[11px]", i < step ? "bg-emerald-600 text-white" : i === step ? "bg-brand-500 text-white" : "bg-gray-200")}>
                  {i < step ? <Check size={12} /> : i + 1}
                </span>
                {s}
              </button>
            </li>
          ))}
        </ol>

        <Card className="p-5">
          {step === 0 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">What do you want to achieve?</h2>
                <p className="text-sm text-muted">The agent will optimize everything it does for this goal.</p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {GOALS.map((g) => (
                  <button
                    key={g.key}
                    type="button"
                    onClick={() => setGoal(g.key)}
                    className={cx(
                      "flex items-center gap-3 rounded-lg border p-3 text-left text-sm font-semibold transition",
                      goal === g.key ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-line hover:border-gray-400",
                    )}
                  >
                    <span className={goal === g.key ? "text-brand-600" : "text-muted"}>{g.icon}</span>
                    {g.label}
                  </button>
                ))}
              </div>
              <Field label="Describe the goal">
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder={GOALS.find((g) => g.key === goal)?.example} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Number to grow (primary metric)" hint="The agent measures and reports this every cycle.">
                  <Input value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="e.g. followers" />
                </Field>
                <Field label="Target (optional)">
                  <Input type="number" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="e.g. 5000" />
                </Field>
              </div>
              <Field label="Campaign name (optional)">
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. X growth, November" />
              </Field>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">Budget & schedule</h2>
                <p className="text-sm text-muted">
                  The budget covers everything the agent spends: mostly its own AI usage, plus any ads or purchases you allow. It is a hard
                  limit. When it runs out, the campaign pauses.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Total budget (USD)">
                  <div className="relative">
                    <DollarSign size={15} className="absolute left-2.5 top-2.5 text-muted" />
                    <Input className="pl-7" type="number" min="1" step="1" value={budget} onChange={(e) => setBudget(e.target.value)} />
                  </div>
                </Field>
                <Field label="Daily cap (optional)" hint="Spending pauses for the day when reached.">
                  <div className="relative">
                    <DollarSign size={15} className="absolute left-2.5 top-2.5 text-muted" />
                    <Input className="pl-7" type="number" min="0" step="0.5" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)} placeholder="No cap" />
                  </div>
                </Field>
                <Field label="End date (optional)">
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                </Field>
                <Field label="Check in and optimize every" hint="The agent may choose sooner or later based on results.">
                  <Select value={cycleHours} onChange={(e) => setCycleHours(e.target.value)}>
                    {["1", "3", "6", "12", "24", "48"].map((h) => (
                      <option key={h} value={h}>
                        {h} hour{h === "1" ? "" : "s"}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">Context & channels</h2>
                <p className="text-sm text-muted">The more the agent knows, the better its content and choices.</p>
              </div>
              <Field label="About your product, account and audience" hint="Links, what makes it special, who it's for, prices, tone of voice, things to avoid.">
                <Textarea rows={7} value={context} onChange={(e) => setContext(e.target.value)} placeholder={"Product: ...\nLink: https://...\nAudience: ...\nVoice: friendly, concise, no hype\nMy X handle: @..."} />
              </Field>
              <div>
                <div className="mb-1.5 text-[13px] font-semibold">Preferred channels (optional)</div>
                <div className="flex flex-wrap gap-2">
                  {CHANNELS.map((ch) => {
                    const on = channels.includes(ch);
                    return (
                      <button
                        key={ch}
                        type="button"
                        onClick={() => setChannels(on ? channels.filter((c) => c !== ch) : [...channels, ch])}
                        className={cx("rounded-full border px-3 py-1 text-sm", on ? "border-brand-500 bg-brand-50 font-semibold text-brand-700" : "border-line hover:border-gray-400")}
                      >
                        {ch}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-1.5 text-xs text-muted">Leave empty to let the agent choose. It uses connected apps where possible, otherwise Agent Chrome.</p>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-lg font-semibold">Guardrails</h2>
                <p className="text-sm text-muted">
                  Choose what the agent may never do, what it must ask about first, and what it can just do. You can change all of this later, and
                  you can also say &quot;don&apos;t ask me next time&quot; on any approval.
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
                <ListEditor items={exclusions.filter((e) => e.kind === "text")} placeholder={`e.g. "Never mention competitors" or "No posts about politics"`} onAdd={addEx("text")} onRemove={removeEx} empty="No custom rules." />
                <p className="mt-1.5 text-xs text-muted">
                  Every outgoing action is checked against these by a separate AI reviewer before it runs. This is a strong check, not a guarantee. For a
                  guarantee, turn a whole category to &quot;Never&quot; above.
                </p>
              </div>
              {builtIn && (
                <details className="rounded-md bg-gray-50 px-3 py-2 text-sm">
                  <summary className="cursor-pointer font-semibold">Always-on rules ({builtIn.rules.length})</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
                    {builtIn.rules.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Review</h2>
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <Item k="Goal" v={description || "—"} />
                <Item k="Primary metric" v={`${metric}${target ? ` → ${target}` : ""}`} />
                <Item k="Budget" v={`$${budget}${dailyCap ? ` · $${dailyCap}/day cap` : ""}${endDate ? ` · ends ${endDate}` : ""}`} />
                <Item k="Check-ins" v={`Every ${cycleHours}h`} />
                <Item k="Channels" v={channels.join(", ") || "Agent's choice"} />
                <Item k="Never" v={types.filter((t) => effective[t.key] === "never").map((t) => t.label).join(", ") || "—"} />
                <Item k="Without asking" v={types.filter((t) => t.default === "ask" && effective[t.key] === "auto").map((t) => t.label).join(", ") || "Nothing: it asks first"} />
                <Item k="Custom rules & blocks" v={exclusions.map((e) => e.value).join("; ") || "—"} />
              </dl>
              <p className="rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-700">
                When you launch, the agent starts its first cycle: it researches, writes a strategy and asks you before doing anything that needs your OK.
              </p>
            </div>
          )}

          {error && <div className="mt-4"><ErrorNote>{error}</ErrorNote></div>}

          <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
              <ArrowLeft size={15} /> Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button variant="primary" onClick={next}>
                Next <ArrowRight size={15} />
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button disabled={busy} onClick={() => submit(false)}>
                  Save as draft
                </Button>
                <Button variant="success" disabled={busy} onClick={() => submit(true)}>
                  <Rocket size={15} /> Launch
                </Button>
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
