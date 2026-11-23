"use client";

import { Ban, ChevronDown, Hand, Loader2, Lock, ShieldCheck, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, Campaign, Mode, Permission, Permissions, PlanStep, Playbook, TOOL_LABELS, usd } from "@/lib/api";
import { cx, ErrorNote } from "./ui";

/** Plain words for each mode, used everywhere so people learn one vocabulary. */
export const MODE_WORDS: Record<Mode, { short: string; long: (team: string) => string }> = {
  auto: { short: "On its own", long: () => "Does this on its own" },
  ask: { short: "Asks first", long: (team) => `Asks ${team} first` },
  never: { short: "Off", long: () => "Never does this" },
};

const MODE_STYLE: Record<Mode, string> = {
  auto: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  ask: "bg-signal-50 text-signal-900 ring-signal-300",
  never: "bg-stone-100 text-stone-500 ring-stone-200",
};

const MODE_ICON: Record<Mode, React.ReactNode> = {
  auto: <Zap size={12} />,
  ask: <Hand size={12} />,
  never: <Ban size={12} />,
};

export function teamName(p: { department: string | null; approvers: string[] }) {
  return p.department ? `the ${p.department} team` : "an admin";
}

export function ModeBadge({ mode, team }: { mode: Mode; team?: string }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold ring-1", MODE_STYLE[mode])}>
      {MODE_ICON[mode]} {mode === "ask" && team ? `Asks ${team.replace(/^the /, "")}` : MODE_WORDS[mode].short}
    </span>
  );
}

/** Pick on its own / asks first / off for one kind of action. */
export function ModePicker({ p, onChange, disabled }: { p: Permission; onChange: (m: Mode) => void; disabled?: boolean }) {
  const options: Mode[] = p.default === "auto" ? ["auto", "never"] : ["ask", "auto", "never"];
  const locked = p.set_at === "org" || p.set_at === "department";
  return (
    <div className="inline-flex shrink-0 overflow-hidden rounded-md border border-line text-[11.5px] font-semibold" title={locked ? `Set for ${p.set_at === "org" ? "the whole organization" : "the department"} in Settings → Permissions` : undefined}>
      {options.map((m) => (
        <button
          key={m}
          type="button"
          disabled={disabled}
          onClick={() => m !== p.mode && onChange(m)}
          className={cx(
            "px-2 py-1 transition disabled:cursor-not-allowed",
            p.mode === m ? (m === "auto" ? "bg-emerald-600 text-white" : m === "ask" ? "bg-signal-500 text-white" : "bg-stone-600 text-white") : "bg-white text-muted hover:bg-stone-50",
          )}
        >
          {MODE_WORDS[m].short}
        </button>
      ))}
    </div>
  );
}

/** Loads a goal's permissions and changes them, with the explanation the server gives back. */
export function usePermissions(goalId: string) {
  const [perms, setPerms] = useState<Permissions | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setPerms(await api<Permissions>(`/api/campaigns/${goalId}/permissions`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [goalId]);
  useEffect(() => {
    load();
  }, [load]);
  async function change(key: string, mode: Mode) {
    setNote(null);
    setError(null);
    let limit: number | null = null;
    if (key === "spend_money" && mode === "auto") {
      const v = prompt("Spend without asking, up to how much per action (USD)?", "5");
      if (!v || !(Number(v) > 0)) return;
      limit = Number(v);
    }
    setBusy(true);
    try {
      const r = await api<{ note: string | null }>(`/api/campaigns/${goalId}/permissions/${key}`, {
        method: "PUT", json: { mode, spend_limit_usd: limit },
      });
      setNote(r.note);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { perms, note, error, busy, change, reload: load };
}

/** The promise people need to read before they trust an AI employee with their accounts. */
export function Assurance({ perms, agent, compact }: { perms: Permissions; agent: string; compact?: boolean }) {
  const team = teamName(perms);
  const exceptions = perms.action_types.filter((p) => p.default === "ask" && p.mode === "auto");
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-600 text-white"><Lock size={15} /></span>
        <div className="min-w-0 text-sm">
          <div className="font-bold text-emerald-900">Nothing goes out without a yes</div>
          <p className="mt-0.5 text-stone-700">
            Before {agent} sends, posts, spends or changes anything, it stops and asks {team}
            {perms.approvers.length ? ` (${perms.approvers.join(", ")})` : ""}. You see exactly what it wants to do, can edit it, and it only goes
            ahead once someone approves.
          </p>
          {!compact && (
            <p className="mt-1.5 text-xs text-stone-600">
              This is enforced by Autopilot itself, not left to the AI: final clicks like Send, Post and Pay are blocked unless an approval covers
              them, and every app action is checked against these settings before it runs.
            </p>
          )}
          {exceptions.length > 0 && (
            <p className="mt-2 rounded-md bg-signal-50 px-2.5 py-1.5 text-xs text-signal-900 ring-1 ring-signal-200">
              <b>Except:</b> you let it {joinWords(exceptions.map((p) => verbFor(p.key) + (p.spend_limit_usd ? ` (up to ${usd(p.spend_limit_usd)} each)` : "")))} without asking.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

const VERBS: Record<string, string> = {
  engage: "likes, follows or comments", publish_post: "posts anything", publish_article: "publishes an article",
  send_message: "sends a message or email", modify_account: "changes an account or profile", delete_content: "deletes anything",
  spend_money: "spends money", other_write: "changes anything else", research: "researches", read_data: "reads app data",
  create_draft: "writes drafts",
};
const verbFor = (k: string) => VERBS[k] || k;
function joinWords(words: string[]) {
  if (words.length <= 1) return words.join("");
  return words.slice(0, -1).join(", ") + " or " + words[words.length - 1];
}

/** The goal's steps, each marked "on its own" or "asks first", with a control to change it. */
export function PlanSteps({ steps, perms, onChange, editable, busy }: {
  steps: PlanStep[]; perms: Permissions; onChange?: (key: string, mode: Mode) => void; editable?: boolean; busy?: boolean;
}) {
  const byKey = Object.fromEntries(perms.action_types.map((p) => [p.key, p]));
  const team = teamName(perms);
  return (
    <ol className="space-y-2">
      {steps.map((st, i) => {
        const p = byKey[st.action_type] || byKey.other_write;
        return (
          <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-line bg-white px-3 py-2.5">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-stone-100 text-xs font-bold text-stone-600">{i + 1}</span>
            <span className="min-w-0 flex-1 text-[13.5px]">
              {st.text}
              {TOOL_LABELS[st.tool] ? <span className="ml-1.5 rounded bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-600">{TOOL_LABELS[st.tool]}</span> : null}
            </span>
            {editable && onChange ? <ModePicker p={p} disabled={busy} onChange={(m) => onChange(p.key, m)} /> : <ModeBadge mode={p.mode} team={team} />}
          </li>
        );
      })}
    </ol>
  );
}

/** Every kind of action, grouped by who decides. */
export function PermissionsEditor({ perms, onChange, busy }: { perms: Permissions; onChange: (key: string, mode: Mode) => void; busy?: boolean }) {
  const team = teamName(perms);
  const groups: { mode: Mode; title: string; hint: string }[] = [
    { mode: "auto", title: "Does on its own", hint: "Nothing here leaves Autopilot or changes your accounts, unless you moved it here." },
    { mode: "ask", title: `Asks ${team} first`, hint: "It shows exactly what it wants to do and waits for a yes." },
    { mode: "never", title: "Never does", hint: "Blocked outright, whatever it thinks." },
  ];
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {groups.map((g) => {
        const items = perms.action_types.filter((p) => p.mode === g.mode);
        return (
          <div key={g.mode} className="rounded-xl border border-line bg-white">
            <div className="border-b border-line px-3 py-2">
              <div className="flex items-center gap-1.5 text-[13px] font-bold">{MODE_ICON[g.mode]} {g.title}</div>
              <div className="text-[11.5px] text-muted">{g.hint}</div>
            </div>
            <ul className="divide-y divide-line">
              {items.length === 0 && <li className="px-3 py-2.5 text-xs text-muted">Nothing.</li>}
              {items.map((p) => (
                <li key={p.key} className="space-y-1.5 px-3 py-2.5">
                  <div className="text-[13px] font-semibold">{p.label}{p.spend_limit_usd ? ` (up to ${usd(p.spend_limit_usd)} each)` : ""}</div>
                  <div className="text-[11.5px] text-muted">{p.description}</div>
                  {p.only_on.length > 0 && p.mode === "ask" && <div className="text-[11.5px] text-emerald-700">Except on {p.only_on.join(", ")}: on its own</div>}
                  {(p.set_at === "org" || p.set_at === "department") && (
                    <div className="text-[11px] text-muted">Set for {p.set_at === "org" ? "the whole organization" : "the department"}</div>
                  )}
                  {perms.can_edit && <ModePicker p={p} disabled={busy} onChange={(m) => onChange(p.key, m)} />}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

/** The whole picture for one goal: the promise, the steps, and every setting behind them. */
export function GoalPlan({ goal, defaultOpen = true }: { goal: Campaign; defaultOpen?: boolean }) {
  const agent = goal.agent?.name || "Your AI employee";
  const [book, setBook] = useState<Playbook | null>(goal.playbook ?? null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [open, setOpen] = useState(defaultOpen);
  const [showAll, setShowAll] = useState(false);
  const { perms, note, error, busy, change } = usePermissions(goal.id);

  useEffect(() => {
    if (goal.playbook) {
      setBook(goal.playbook);
      return;
    }
    api<Playbook>(`/api/campaigns/${goal.id}/playbook`, { method: "POST" }).then(setBook).catch((e) => setPlanError((e as Error).message));
  }, [goal.id, goal.playbook]);

  const modeOf = (k: string) => perms?.action_types.find((p) => p.key === k)?.mode ?? "ask";
  const asking = book ? book.steps.filter((st) => modeOf(st.action_type) === "ask").length : 0;
  return (
    <section className="rounded-2xl border border-line bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <ShieldCheck size={18} className="text-emerald-600" />
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold">How {agent} works on this goal</span>
          <span className="block text-xs text-muted">
            {book ? `${book.steps.length} steps` : "Working out the steps…"}
            {book && perms ? ` · ${book.steps.length - asking} on its own, ${asking} ${asking === 1 ? "waits" : "wait"} for ${teamName(perms)} · you can change any of it` : ""}
          </span>
        </span>
        <ChevronDown size={18} className={cx("text-muted transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-line p-4">
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[12px] font-bold uppercase tracking-wide text-muted">Step by step</h3>
              {perms?.can_edit && goal.can_manage !== false && book && (
                <button onClick={() => setShowAll(!showAll)} className="text-sm font-semibold text-brand-600 hover:underline">
                  {showAll ? "Done" : "Customize"}
                </button>
              )}
            </div>
            {!book && !planError && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> Working out the steps…</p>}
            {planError && <ErrorNote>{planError}</ErrorNote>}
            {book && perms && !showAll && <StepList steps={book.steps} modeOf={(k) => perms.action_types.find((p) => p.key === k)?.mode ?? "ask"} team={teamName(perms)} />}
            {book && perms && showAll && (
              <div className="space-y-3">
                <PlanSteps steps={book.steps} perms={perms} editable onChange={change} busy={busy} />
                <p className="text-xs text-muted">Changing a step changes every step of the same kind (for example, all &quot;send&quot; steps).</p>
              </div>
            )}
          </div>
          {perms && (
            <p className="flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[13px] text-emerald-900">
              <Lock size={14} className="mt-0.5 shrink-0" />
              <span>
                <b>Nothing goes out without a yes.</b> Before {agent} sends, posts, spends or changes anything, it asks {teamName(perms)} and shows
                exactly what it wants to do. This is enforced by Autopilot, not left to the AI.
                {perms.action_types.some((p) => p.default === "ask" && p.mode === "auto") && (
                  <span className="mt-1 block text-signal-800">
                    Except what you set to on its own: {perms.action_types.filter((p) => p.default === "ask" && p.mode === "auto").map((p) => p.label.toLowerCase()).join(", ")}.
                  </span>
                )}
              </span>
            </p>
          )}
          {note && <p className="rounded-md bg-signal-50 px-3 py-2 text-sm text-signal-900">{note}</p>}
          {error && <ErrorNote>{error}</ErrorNote>}
          {perms && showAll && (
            <div className="space-y-3">
              <h3 className="text-[12px] font-bold uppercase tracking-wide text-muted">Every kind of action it could take</h3>
              <PermissionsEditor perms={perms} onChange={change} busy={busy} />
              <details className="rounded-md bg-stone-50 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-semibold text-muted">Rules that always apply ({perms.built_in_rules.length})</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{perms.built_in_rules.map((r) => <li key={r}>{r}</li>)}</ul>
              </details>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/** The plan as a simple timeline: each step either happens on its own or waits for a person's OK. */
export function StepList({ steps, modeOf, team }: { steps: PlanStep[]; modeOf: (actionType: string) => Mode; team?: string }) {
  return (
    <ol className="relative space-y-3 before:absolute before:bottom-3 before:left-[13px] before:top-3 before:border-l-2 before:border-stone-200">
      {steps.map((st, i) => {
        const mode = modeOf(st.action_type);
        return (
          <li key={i} className="relative flex items-start gap-3">
            <span className={cx("z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ring-white",
              mode === "auto" ? "bg-emerald-100 text-emerald-700" : mode === "ask" ? "bg-signal-100 text-signal-700" : "bg-stone-100 text-stone-400")}>
              {MODE_ICON[mode]}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className={cx("text-[13.5px] leading-snug", mode === "never" && "text-stone-400 line-through")}>{st.text}</div>
              <div className={cx("text-[11.5px] font-semibold", mode === "auto" ? "text-emerald-700" : mode === "ask" ? "text-signal-700" : "text-stone-400")}>
                {mode === "auto" ? "Automatic" : mode === "ask" ? `Waits for ${team ? team.replace(/^the /, "") : "your"} OK` : "Turned off"}
                {TOOL_LABELS[st.tool] ? <span className="font-normal text-muted"> · {TOOL_LABELS[st.tool]}</span> : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
