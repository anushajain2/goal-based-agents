"use client";

import { ArrowRight, Check, ChevronDown, CircleAlert, Loader2, Minus, RefreshCw, Search, Sparkles } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CompanyProfileCard } from "@/components/CompanyProfile";
import { Opportunities } from "@/components/Opportunities";
import { GoalPanel } from "@/components/GoalPanel";
import { StartGoal } from "@/components/StartGoal";
import { Badge, Button, Card, cx, ErrorNote, Field, Input, Textarea } from "@/components/ui";
import { api, Campaign, CompanyProfile, OrgInfo, SetupInfo, SetupStep, usd, useApi } from "@/lib/api";
import { useLiteMotion } from "@/lib/motion";

const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });

/** What the check looks at, cycled while it runs so there's always something to read. */
const LOOKING_AT = [
  "Who is asking online for what you sell",
  "What ChatGPT says when buyers ask for tools like yours",
  "Where your competitors show up and you don't",
  "Your competitors' reviews, videos and launch posts",
  "Whether a buyer can check your security and proof",
  "How your home page reads in the first 5 seconds",
  "Companies with a fresh reason to buy right now",
];

/** The company check while it runs: the site being scanned, the steps as a live timeline, and what it's looking at. */
function ResearchLive({ info }: { info: SetupInfo }) {
  const lite = useLiteMotion();
  const steps = info.setup!.steps;
  const done = steps.filter((x) => x.status === "done" || x.status === "skipped").length;
  const current = steps.find((x) => x.status === "running") || steps.find((x) => x.status === "pending");
  const pct = Math.round(((done + (current?.status === "running" ? 0.5 : 0)) / Math.max(1, steps.length)) * 100);
  const [tick, setTick] = useState(0);
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 2400);
    const c = setInterval(() => setSecs((n) => n + 1), 1000);
    return () => { clearInterval(t); clearInterval(c); };
  }, []);
  const host = (info.org.website || "").replace(/^https?:\/\//, "").replace(/\/$/, "") || info.org.name;
  const R = 34, C = 2 * Math.PI * R;

  return (
    <div className="mx-auto max-w-6xl">
      <section className="relative overflow-hidden rounded-3xl bg-ink text-white shadow-[var(--shadow-pop)]">
        <div aria-hidden className="absolute inset-0">
          {lite
            ? <div className="h-full w-full bg-[radial-gradient(60%_50%_at_50%_100%,rgba(132,204,22,0.35),transparent)]" />
            : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={0.95} bandHeight={0.18} noiseAmplitude={0.6} />}
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(21,26,14,0.5),rgba(21,26,14,0.8)_55%,rgba(21,26,14,0.15))]" />
        </div>

        <div className="relative grid gap-10 p-6 md:p-10 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div className="rise min-w-0">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-lime-300">
              <span className="signal-dot" /> Checking {info.org.name} live
            </div>
            <h1 className="mt-3 text-[30px] font-bold leading-[1.1] tracking-[-0.02em] md:text-[40px]">
              Finding what {info.org.name}<br />is missing out on
            </h1>
            <p className="mt-3 max-w-[52ch] text-[14.5px] leading-relaxed text-white/65">
              Usually 1 to 3 minutes. You can leave this page; it keeps going and your findings will be waiting.
            </p>

            {/* The site, being scanned */}
            <div className="mt-8 overflow-hidden rounded-2xl bg-white/[0.06] ring-1 ring-inset ring-white/10 backdrop-blur-sm">
              <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-white/20" /><span className="h-2.5 w-2.5 rounded-full bg-white/20" /><span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                <span className="ml-2 min-w-0 flex-1 truncate rounded-md bg-white/10 px-3 py-1 font-mono text-[12px] text-white/70">{host}</span>
              </div>
              <div className="relative h-44 overflow-hidden px-5 py-4">
                <div className="space-y-2.5 opacity-60">
                  <div className="h-3 w-2/5 rounded bg-white/25" />
                  <div className="h-2 w-4/5 rounded bg-white/10" />
                  <div className="h-2 w-3/5 rounded bg-white/10" />
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    {[0, 1, 2].map((k) => <div key={k} className="h-14 rounded-lg bg-white/[0.07]" />)}
                  </div>
                  <div className="h-2 w-2/3 rounded bg-white/10" />
                </div>
                <div className="scanline pointer-events-none absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-lime-300/25 to-transparent">
                  <div className="absolute inset-x-0 bottom-1/2 h-px bg-lime-300/80 shadow-[0_0_12px_2px_rgba(190,242,100,0.6)]" />
                </div>
                <div className="absolute bottom-3 left-4 right-4 flex items-center gap-2 text-[12.5px]">
                  <Search size={13} className="shrink-0 text-lime-300" />
                  <span key={tick} className="rise truncate text-white/85">{LOOKING_AT[tick % LOOKING_AT.length]}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="rise min-w-0" style={{ animationDelay: "150ms" }}>
            <div className="flex items-center gap-4">
              <svg width="84" height="84" viewBox="0 0 84 84" className="shrink-0 -rotate-90">
                <circle cx="42" cy="42" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="6" />
                <circle cx="42" cy="42" r={R} fill="none" stroke="#bef264" strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={C} strokeDashoffset={C * (1 - pct / 100)} style={{ transition: "stroke-dashoffset 900ms ease" }} />
              </svg>
              <div>
                <div className="tabular text-[30px] font-bold leading-none">{pct}%</div>
                <div className="mt-1 text-[12.5px] text-white/55">{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")} elapsed</div>
              </div>
            </div>

            <ol className="relative mt-7 space-y-5 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-white/15">
              {steps.map((x) => {
                const on = x.status === "running";
                const ok = x.status === "done" || x.status === "skipped";
                return (
                  <li key={x.key} className="relative flex items-start gap-3.5">
                    <span className={cx("relative grid h-6 w-6 shrink-0 place-items-center rounded-full",
                      ok ? "bg-lime-300 text-ink" : on ? "bg-ink ring-2 ring-lime-300" : x.status === "failed" ? "bg-amber-300 text-ink" : "bg-ink ring-1 ring-white/25")}>
                      {ok ? <Check size={14} strokeWidth={3} /> : on ? <span className="signal-dot" /> : x.status === "failed" ? <CircleAlert size={13} /> : null}
                    </span>
                    <div className="min-w-0 pt-0.5">
                      <div className={cx("text-[14.5px] font-semibold", ok ? "text-white/80" : on ? "text-white" : "text-white/40")}>
                        {x.label}{on && <span className="ml-1 inline-flex gap-0.5 align-middle">{[0, 1, 2].map((d) => <span key={d} className="h-1 w-1 animate-bounce rounded-full bg-lime-300" style={{ animationDelay: `${d * 150}ms` }} />)}</span>}
                      </div>
                      {x.detail && <div className="mt-0.5 text-[12.5px] text-white/50">{x.detail}</div>}
                    </div>
                  </li>
                );
              })}
            </ol>
            {info.setup!.cost_usd > 0 && <p className="mt-6 text-[12px] text-white/40">Research cost so far {usd(info.setup!.cost_usd)}, paid by the workspace, not a goal&apos;s budget.</p>}
          </div>
        </div>
      </section>

      <div className="mt-8 mb-3 flex items-baseline justify-between">
        <h2 className="text-[16px] font-semibold">Your findings will land here</h2>
        <span className="text-[12.5px] text-muted">Each with the proof, what it costs you, and a fix you can turn on</span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {[0, 1, 2].map((k) => (
          <div key={k} className="rise overflow-hidden rounded-2xl border border-line bg-white p-5 shadow-[var(--shadow-card)]" style={{ animationDelay: `${300 + k * 120}ms` }}>
            <div className="flex items-center gap-2">
              <span className="h-5 w-14 rounded-full bg-red-50" />
              <span className="h-5 w-20 rounded-full bg-stone-100" />
            </div>
            <div className="mt-4 h-4 w-4/5 animate-pulse rounded bg-stone-200" style={{ animationDelay: `${k * 200}ms` }} />
            <div className="mt-2 h-4 w-3/5 animate-pulse rounded bg-stone-200" style={{ animationDelay: `${k * 200}ms` }} />
            <div className="mt-5 space-y-2">
              {[0, 1, 2].map((r) => <div key={r} className="h-2.5 animate-pulse rounded bg-stone-100" style={{ width: `${90 - r * 15}%`, animationDelay: `${k * 200 + r * 100}ms` }} />)}
            </div>
            <div className="mt-5 flex items-center justify-between rounded-xl bg-ink px-3 py-2.5">
              <span className="h-2.5 w-24 animate-pulse rounded bg-white/20" />
              <span className="h-6 w-16 rounded-lg bg-lime-300/70" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
          <h1 className="text-xl font-bold">Research {name} and set up your goals</h1>
          <p className="mt-1 text-sm text-muted">Oton reads your website and researches your company, then suggests goals that fit each team.</p>
          <RetryForm info={info} onStarted={load} label="Start research" />
        </Card>
      </div>
    );
  }

  if (working) return <ResearchLive info={info} />;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            {working ? `Getting to know ${name}…` : status === "done" ? `What ${name} is missing out on` : `Setting up ${name} didn't finish`}
          </h1>
          <p className="text-sm text-muted">
            {working
              ? "This usually takes 1 to 3 minutes. You can leave this page: it keeps going and the results will be here."
              : status === "done"
                ? "Each one has a goal ready. Nothing runs or costs anything until you turn it on."
                : "You can try again, or start with a basic team and set it up yourself."}
          </p>
        </div>
        {status === "done" && (
          <Link href="/home" className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-line bg-white px-4 text-sm font-semibold hover:bg-stone-50">
            Continue <ArrowRight size={15} />
          </Link>
        )}
      </div>

      <Steps steps={info.setup.steps} cost={info.setup.cost_usd} compact={status === "done"} />

      {working && (info.org.website || info.org.description) && (
        <Card className="p-4 text-sm">
          <div className="mb-1 text-xs font-semibold text-muted">What you told us</div>
          {info.org.website && <p className="text-brand-700">{info.org.website}</p>}
          {info.org.description && <p className="mt-1 text-stone-700">{info.org.description}</p>}
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
                  Or start with a basic team (Sales, Marketing, Customer Research)
                </button>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">Ask an admin of {name} to try again.</p>
          )}
        </Card>
      )}

      {status === "done" && (
        <>
          {(info.org.profile || info.setup.plan?.profile)?.summary && <Learned profile={(info.org.profile || info.setup.plan!.profile)!} name={name} />}
          <SuggestedTeam info={info} onAdding={load} />
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
          <span className="block text-[12px] font-bold text-muted">What we learned about {name}</span>
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
  if (status === "failed") return <span className={cx(base, "bg-signal-100 text-signal-700")}><CircleAlert size={14} /></span>;
  if (status === "skipped") return <span className={cx(base, "bg-stone-100 text-stone-400")}><Minus size={14} /></span>;
  return <span className={cx(base, "border-2 border-stone-200")} />;
}


function SuggestedTeam({ info, onAdding }: { info: SetupInfo; onAdding: () => void }) {
  const { data: goals, reload } = useApi<Campaign[]>("/api/campaigns");
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org");
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const createdIds = info.setup!.created?.goals;
  const mine = useMemo(() => {
    const created = new Set(createdIds || []);
    return (goals || []).filter((g) => created.has(g.id) || g.origin === "setup");
  }, [goals, createdIds]);
  const oldBudgets = mine.filter((g) => g.status === "draft" && !g.budget_basis?.starter && !g.budget_basis?.milestone);

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
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-signal-200 bg-signal-50 px-4 py-3 text-sm">
          <span className="min-w-0 flex-1">
            Start small: give these goals a one-week budget first ({usd(oldBudgets.reduce((t, g) => t + g.budget.total, 0))} now), and add more once you see results.
          </span>
          <Button size="sm" variant="primary" onClick={starterBudgets}>Use one-week budgets</Button>
        </div>
      )}

      {/* Onboarding stays on what we found and the fixes for it. The team, the org chart and
          connecting tools live on their own pages (tools are also asked for when a goal is turned on). */}
      <Opportunities profile={info.org.profile} org={org} goals={goals} orgName={info.org.name} canStart={info.can_run}
        onStart={setStarting} onOpen={setPanel} titled={false} />
      {!(info.org.profile?.opportunities?.findings || []).length && (
        <Card className="flex flex-wrap items-center gap-3 p-5">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{mine.length ? `${mine.length} goals are ready for ${info.org.name}` : "Your goals are ready"}</div>
            <div className="text-sm text-muted">We didn&apos;t find specific gaps to show this time. Pick a goal to turn on.</div>
          </div>
          <Link href="/goals" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">
            See goals <ArrowRight size={15} />
          </Link>
        </Card>
      )}

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
    return <p className="mt-3 rounded-md bg-signal-50 px-3 py-2 text-sm text-signal-900">Add <code>ANTHROPIC_API_KEY</code> to the <code>.env</code> file and restart Oton to research your company.</p>;
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

