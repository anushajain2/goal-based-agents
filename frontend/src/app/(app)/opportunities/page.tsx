"use client";

import { ArrowRight, CheckCircle2, Loader2, Radar, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { GoalPanel } from "@/components/GoalPanel";
import { Opportunities } from "@/components/Opportunities";
import { RunProgress } from "@/components/RunProgress";
import { StartGoal } from "@/components/StartGoal";
import { Card, ErrorNote, PageHeader } from "@/components/ui";
import { api, Campaign, OrgInfo, Opportunity, SetupInfo, useApi } from "@/lib/api";

/** Find opportunities: what we found that the company could do better, with the goal that fixes
 *  each (only the ones not turned on yet), and "Find more" to look again for new ones. */
export default function OpportunitiesPage() {
  const [info, setInfo] = useState<SetupInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: goals, reload: reloadGoals } = useApi<Campaign[]>("/api/campaigns");
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org");
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const [asking, setAsking] = useState(false);

  const load = useCallback(async () => {
    try {
      setInfo(await api<SetupInfo>("/api/org/setup"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const task = info?.task?.mode === "more" ? info.task : null;
  const looking = !!task && (task.status === "queued" || task.status === "running");
  const researching = !!info?.setup && (info.setup.status === "queued" || info.setup.status === "running");
  // Only one research run at a time (e.g. "Suggest more goals" on the Team page).
  const otherRun = !!info?.task && !task && (info.task.status === "queued" || info.task.status === "running");
  useEffect(() => {
    if (!looking && !researching) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [looking, researching, load]);
  useEffect(() => {
    if (!otherRun) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [otherRun, load]);
  // When a search finishes, its new goals show up.
  useEffect(() => { if (task?.status === "done") { reloadGoals(); reloadOrg(); } }, [task?.status, reloadGoals, reloadOrg]);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!info) return <p className="text-muted">Loading…</p>;

  const profile = info.org.profile;
  const found = profile?.opportunities;
  const byId = new Map((goals || []).map((g) => [g.id, g]));
  // A finding is being fixed once any of its goals is on.
  const goalsOf = (f: Opportunity) => [f.goal_id, ...(f.milestones || []).map((m) => m.goal_id)].filter(Boolean) as string[];
  const fixing = (f: Opportunity) => goalsOf(f).some((id) => { const g = byId.get(id); return !!g && g.status !== "draft"; });
  const all = found?.findings || [];
  const open = all.filter((f) => !fixing(f));
  const on = all.length - open.length;
  const canRun = info.can_run;

  async function findMore() {
    setAsking(true);
    setError(null);
    try {
      await api("/api/org/setup", { method: "POST", json: { mode: "more" } });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAsking(false);
    }
  }

  const findButton = canRun && found && (
    <button onClick={findMore} disabled={asking || looking || researching || otherRun}
      title={otherRun ? "Oton is suggesting goals right now; try again in a minute" : undefined}
      className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
      {asking || looking ? <Loader2 size={16} className="animate-spin" /> : <Radar size={16} />} {looking ? "Looking…" : "Find more opportunities"}
    </button>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Find opportunities"
        subtitle={`Where ${info.org.name} could win more customers or do better, measured against competitors, each with a goal ready to turn on.`}
        actions={findButton}
      />

      {researching && (
        <Card className="flex items-center gap-3 p-4 text-sm">
          <Loader2 size={16} className="animate-spin text-brand-600" />
          <span className="flex-1">Oton is checking {info.org.name}. The findings appear here when it&apos;s done.</span>
          <Link href="/setup" className="font-semibold text-brand-700 hover:underline">See progress</Link>
        </Card>
      )}

      {task && looking && (
        <Card className="p-5">
          <div className="mb-3 flex items-center gap-2 text-[15px] font-semibold"><Search size={16} className="text-brand-600" /> Looking for new opportunities</div>
          <RunProgress steps={task.steps} />
          <p className="mt-3 text-xs text-muted">This takes a few minutes. It skips what we found before, so everything it adds is new. You can leave this page.</p>
        </Card>
      )}
      {task && task.status === "done" && (task.created?.goals || []).length === 0 && !looking && task.steps.at(-1)?.detail?.includes("nothing new") && (
        <Card className="p-4 text-sm text-muted">The last search didn&apos;t find anything new. Try again later, after your site or market changes.</Card>
      )}
      {task && task.status === "failed" && <ErrorNote>Finding more didn&apos;t finish: {task.error || "something went wrong"}. Try again.</ErrorNote>}

      {!found && !researching && (
        <Card className="flex flex-wrap items-center gap-3 p-5">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">No check yet</div>
            <div className="text-sm text-muted">Oton researches {info.org.name}, measures it against competitors and shows what you&apos;re missing out on.</div>
          </div>
          {canRun && <Link href="/setup" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700">Check my company <ArrowRight size={15} /></Link>}
        </Card>
      )}

      {found && on > 0 && (
        <Link href="/goals" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm hover:bg-emerald-50">
          <CheckCircle2 size={17} className="text-emerald-600" />
          <span className="flex-1"><b>{on} of {all.length}</b> {on === 1 ? "is" : "are"} being fixed: {on === 1 ? "its goal is" : "their goals are"} on.</span>
          <span className="font-semibold text-emerald-800">See goals →</span>
        </Link>
      )}

      {found && open.length === 0 && all.length > 0 && (
        <Card className="p-5 text-sm">
          <div className="font-semibold">Every opportunity we found is being worked on.</div>
          <div className="mt-0.5 text-muted">Find more to look for new ones.</div>
        </Card>
      )}

      {found && (
        <Opportunities profile={profile} org={org} goals={goals} orgName={info.org.name} canStart={canRun}
          onStart={setStarting} onOpen={setPanel} titled={false} only={(f) => !fixing(f)} recheck={false} />
      )}

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); reloadGoals(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); reloadGoals(); reloadOrg(); }} />}
    </div>
  );
}
