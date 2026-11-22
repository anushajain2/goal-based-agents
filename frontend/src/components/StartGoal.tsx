"use client";

import { ArrowLeft, ArrowRight, Check, ExternalLink, Globe, Loader2, Plug, Play, RefreshCw, Server, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, Campaign, Readiness, ToolNeed, usd } from "@/lib/api";
import { BudgetBreakdown } from "./Budget";
import { Assurance, PlanSteps, usePermissions } from "./GoalPlan";
import { AgentAvatar } from "./team";
import { Button, cx, ErrorNote } from "./ui";

type Need = ToolNeed & { goals: string[] };

/**
 * Starting a goal, in two short steps:
 *   1. connect the tools its plan uses (an app connection, or signing in to the site once),
 *   2. read exactly what it will do on its own and what it will ask about, and change it.
 */
export function StartGoal({ goals, onClose, onStarted }: { goals: Campaign[]; onClose: () => void; onStarted: () => void }) {
  const [step, setStep] = useState<1 | 2>(1);
  const [ready, setReady] = useState<Record<string, Readiness>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const needs: Need[] = [];
  for (const g of goals) {
    for (const t of ready[g.id]?.tools || []) {
      const found = needs.find((n) => n.key === t.key);
      if (found) {
        found.required ||= t.required;
        found.goals.push(g.name);
      } else needs.push({ ...t, goals: [g.name] });
    }
  }
  needs.sort((a, b) => Number(b.required) - Number(a.required));
  const missing = needs.filter((n) => n.required && n.status === "missing");
  const servers = Object.values(ready)[0]?.mcp_servers || [];
  const composio = Object.values(ready)[0]?.composio_enabled;

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

  const title = goals.length === 1 ? goals[0].name : `${goals.length} goals`;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-canvas shadow-xl sm:rounded-2xl">
        <div className="flex items-start gap-3 border-b border-line bg-white px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Before it starts · step {step} of 2</div>
            <h2 className="truncate text-lg font-bold">{step === 1 ? "Connect what it needs" : "Check what it will do"}</h2>
            <p className="truncate text-sm text-muted">{title}</p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-gray-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {loading && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Checking what it needs…</p>}
          {error && <ErrorNote>{error}</ErrorNote>}

          {!loading && step === 1 && (
            <>
              <p className="text-sm text-gray-700">
                These are the tools {goals.length === 1 ? "this goal's" : "these goals'"} plan uses. Connecting one only lets the AI employee use it;
                anything it sends, posts or changes still waits for approval.
              </p>
              {needs.length === 0 ? (
                <div className="rounded-lg border border-line bg-white px-4 py-3 text-sm">It only needs the web for now. Nothing to connect.</div>
              ) : (
                <ul className="space-y-2">{needs.map((n) => <ToolRow key={n.key} n={n} composio={!!composio} multi={goals.length > 1} onChanged={load} />)}</ul>
              )}
              <div className="rounded-lg border border-dashed border-line bg-white px-4 py-3 text-sm">
                <div className="flex items-center gap-2 font-semibold"><Server size={15} /> Your own tools (MCP servers)</div>
                {servers.length ? (
                  <p className="mt-1 text-gray-700">{servers.map((s) => `${s.name} (${s.tools} tools${s.error ? ", not reachable" : ""})`).join(", ")}. Its AI employees can use these too, with the same approvals.</p>
                ) : (
                  <p className="mt-1 text-muted">Have an internal system or a tool with an MCP server? Connect it once and every AI employee can use it, with the same approvals.</p>
                )}
                <Link href="/settings#mcp" target="_blank" className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline">
                  {servers.length ? "Manage" : "Add an MCP server"} <ExternalLink size={11} />
                </Link>
              </div>
              {missing.length > 0 && (
                <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  {missing.map((m) => m.label).join(", ")} {missing.length === 1 ? "isn't" : "aren't"} connected yet. You can start anyway: it will ask for{" "}
                  {missing.length === 1 ? "it" : "them"} when it gets to {missing.length === 1 ? "that step" : "those steps"}, and can&apos;t do them until then.
                </p>
              )}
            </>
          )}

          {!loading && step === 2 && goals.map((g) => <GoalReview key={g.id} goal={g} single={goals.length === 1} />)}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-white px-5 py-3">
          {step === 2 ? <Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft size={15} /> Back</Button> : <Button variant="ghost" onClick={onClose}>Not now</Button>}
          {step === 1 ? (
            <Button variant="primary" disabled={loading} onClick={() => setStep(2)}>
              {missing.length ? "Continue without them" : "Continue"} <ArrowRight size={15} />
            </Button>
          ) : (
            <Button variant="primary" disabled={busy} onClick={start}>
              <Play size={15} /> {goals.length === 1 ? "Start" : `Start ${goals.length} goals`}: it asks before anything goes out
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolRow({ n, composio, multi, onChanged }: { n: Need; composio: boolean; multi: boolean; onChanged: () => void }) {
  const [opened, setOpened] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const done = n.status !== "missing";

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
  async function signedIn() {
    await api("/api/sites/signed-in", { method: "POST", json: { site: n.site } });
    onChanged();
  }

  return (
    <li className="rounded-lg border border-line bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-lg", done ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-500")}>
          {done ? <Check size={16} /> : <Plug size={15} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {n.label}
            <span className={cx("rounded-full px-2 py-0.5 text-[11px] font-semibold", n.required ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600")}>{n.required ? "Needed" : "Helpful"}</span>
          </div>
          <div className="text-xs text-muted">
            {done ? (n.status === "connected" ? "Connected" : "Signed in once in Agent Chrome") : n.steps.length ? `Used in step${n.steps.length > 1 ? "s" : ""} ${n.steps.join(", ")}` : "One of the channels you picked"}
            {multi ? ` · ${n.goals.join(", ")}` : ""}
          </div>
        </div>
      </div>
      {!done && (
        <div className="mt-2.5 flex flex-wrap gap-2 pl-11">
          {composio && n.app && <Button size="sm" variant="primary" onClick={connectApp}><Plug size={13} /> Connect {n.label}</Button>}
          {n.site && <Button size="sm" onClick={openSite}><Globe size={13} /> Sign in on {n.site}</Button>}
          {opened && (
            n.site && !(composio && n.app)
              ? <Button size="sm" variant="ghost" onClick={signedIn}><Check size={13} /> I&apos;ve signed in</Button>
              : <Button size="sm" variant="ghost" onClick={onChanged}><RefreshCw size={13} /> Check again</Button>
          )}
        </div>
      )}
      {!done && n.site && (
        <p className="mt-1.5 pl-11 text-[11.5px] text-muted">
          {composio && n.app ? "Connect uses the app's own sign-in page. " : ""}Signing in on the site opens it in Agent Chrome, Autopilot&apos;s own Chrome window;
          you sign in once and the AI employee never sees your password.
        </p>
      )}
      {err && <p className="mt-1.5 pl-11 text-xs text-red-600">{err}</p>}
    </li>
  );
}

function GoalReview({ goal, single }: { goal: Campaign; single: boolean }) {
  const { perms, note, error, busy, change } = usePermissions(goal.id);
  const [book, setBook] = useState(goal.playbook || null);
  useEffect(() => {
    if (!book) api<Campaign>(`/api/campaigns/${goal.id}`).then((g) => setBook(g.playbook || null)).catch(() => null);
  }, [goal.id, book]);
  const agent = goal.agent?.name || "It";
  return (
    <div className={cx("space-y-3", !single && "rounded-xl border border-line bg-white p-4")}>
      {!single && (
        <div className="flex items-center gap-2">
          {goal.agent && <AgentAvatar name={goal.agent.name} size={26} />}
          <div className="min-w-0"><div className="truncate text-sm font-bold">{goal.name}</div><div className="text-xs text-muted">{goal.agent?.name}</div></div>
        </div>
      )}
      {perms && <Assurance perms={perms} agent={agent} compact={!single} />}
      {book && perms && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Step by step · change anything</div>
          <PlanSteps steps={book.steps} perms={perms} editable={perms.can_edit} onChange={change} busy={busy} />
        </div>
      )}
      {note && <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">{note}</p>}
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="rounded-lg border border-line bg-white px-3 py-2.5">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Budget: {usd(goal.budget.total)}, a hard limit</div>
        {goal.budget_basis ? <BudgetBreakdown basis={goal.budget_basis} total={goal.budget.total} compact /> : <p className="text-xs text-muted">When it runs out, work pauses.</p>}
      </div>
    </div>
  );
}
