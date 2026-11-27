"use client";

import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from "react";

import { RunProgress } from "./RunProgress";
import { Card, ErrorNote } from "./ui";
import { api, Campaign, SetupInfo, usd } from "@/lib/api";

export type SuggestGoalsHandle = { reload: () => void };

/** "Suggest more goals I can set up": goals for each function (sales, marketing, product,
 *  finance…), planned from what Oton already learned about the company. Shows the run live, then
 *  the new suggestions with Turn on. */
export const SuggestGoals = forwardRef<SuggestGoalsHandle, {
  orgName: string; goals: Campaign[] | null | undefined; canRun: boolean;
  onOpen: (g: Campaign) => void; onStart: (g: Campaign[]) => void; onGoalsChanged: () => void;
}>(function SuggestGoals({ orgName, goals, canRun, onOpen, onStart, onGoalsChanged }, ref) {
  const [info, setInfo] = useState<SetupInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setInfo(await api<SetupInfo>("/api/org/setup"));
    } catch {
      /* the Team page shows its own errors */
    }
  }, []);
  useImperativeHandle(ref, () => ({ reload: load }), [load]);
  useEffect(() => { load(); }, [load]);

  const task = info?.task && (info.task.mode === "goals" || info.task.mode === "include") ? info.task : null;
  const working = !!task && (task.status === "queued" || task.status === "running");
  const busyElsewhere = !!info && ((info.setup && ["queued", "running"].includes(info.setup.status)) ||
    (info.task && info.task !== task && ["queued", "running"].includes(info.task.status)));
  useEffect(() => {
    if (!working) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [working, load]);
  useEffect(() => { if (task?.status === "done") onGoalsChanged(); }, [task?.status]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!info || !canRun || !info.can_research) return null;
  const byId = new Map((goals || []).map((g) => [g.id, g]));
  const fresh = (task?.status === "done" ? task.created?.goals || [] : [])
    .map((id) => byId.get(id)).filter((g): g is Campaign => !!g && g.status === "draft");

  async function suggest() {
    setBusy(true);
    setErr(null);
    try {
      await api("/api/org/setup", { method: "POST", json: { mode: "goals" } });
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-4 bg-gradient-to-r from-brand-50/80 to-white p-5">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-brand-600 ring-1 ring-inset ring-brand-100"><Sparkles size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold">Suggest more goals I can set up</div>
          <div className="text-[13px] text-muted">Goal ideas for each part of {orgName}: sales, marketing, product, finance and more, from what Oton learned about you. Nothing starts until you turn it on.</div>
        </div>
        <button onClick={suggest} disabled={busy || working || !!busyElsewhere}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
          {busy || working ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} {working ? "Working it out…" : "Suggest goals"}
        </button>
      </div>
      {err && <div className="px-5 pb-4"><ErrorNote>{err}</ErrorNote></div>}
      {busyElsewhere && !working && <p className="border-t border-line px-5 py-3 text-xs text-muted">Oton is checking your company right now; you can ask for goals when it&apos;s done.</p>}
      {working && task && (
        <div className="border-t border-line p-5">
          <RunProgress steps={task.steps} />
          <p className="mt-3 text-xs text-muted">About a minute. You can leave this page.</p>
        </div>
      )}
      {task?.status === "failed" && (
        <div className="border-t border-line p-5"><ErrorNote>Suggesting goals didn&apos;t finish: {task.error || "something went wrong"}. Try again.</ErrorNote></div>
      )}
      {fresh.length > 0 && (
        <div className="border-t border-line p-5">
          <div className="mb-3 text-[12px] font-semibold text-muted">Suggested just now · {fresh.length} goal{fresh.length === 1 ? "" : "s"}</div>
          <ul className="grid gap-2.5 md:grid-cols-2">
            {fresh.map((g) => (
              <li key={g.id} className="flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3">
                <button onClick={() => onOpen(g)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[14px] font-semibold">{g.name}</span>
                  <span className="block truncate text-[12.5px] text-muted">
                    {g.department?.name ? `${g.department.name} · ` : ""}{g.suggested_reason || g.first_deliverable || `${usd(g.budget.total)} budget`}
                  </span>
                </button>
                <button onClick={() => onStart([g])} className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg bg-brand-600 px-3 text-[12.5px] font-semibold text-white hover:bg-brand-700">
                  Turn on <ArrowRight size={13} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
});
