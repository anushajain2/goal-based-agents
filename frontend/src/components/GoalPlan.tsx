"use client";

import { Ban, ChevronDown, Clock, Hand, Loader2, Lock, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, Campaign, Mode, Permission, Permissions, PlanStep, Playbook, TOOL_LABELS, usd } from "@/lib/api";
import { cx, ErrorNote } from "./ui";

/** Plain words for each mode, used everywhere so people learn one vocabulary. */
export const MODE_WORDS: Record<Mode, { short: string; long: (team: string) => string }> = {
  auto: { short: "On its own", long: () => "Does this on its own" },
  heads_up: { short: "Heads-up", long: (team) => `Gives ${team} a heads-up, then goes ahead unless stopped` },
  ask: { short: "Asks first", long: (team) => `Asks ${team} first` },
  never: { short: "Off", long: () => "Never does this" },
};

export const MODE_STYLE: Record<Mode, string> = {
  auto: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  heads_up: "bg-sky-50 text-sky-800 ring-sky-200",
  ask: "bg-signal-50 text-signal-900 ring-signal-300",
  never: "bg-stone-100 text-stone-500 ring-stone-200",
};

export const MODE_ICON: Record<Mode, React.ReactNode> = {
  auto: <Zap size={12} />,
  heads_up: <Clock size={12} />,
  ask: <Hand size={12} />,
  never: <Ban size={12} />,
};

const MODE_ON: Record<Mode, string> = {
  auto: "bg-emerald-600 text-white", heads_up: "bg-sky-600 text-white", ask: "bg-signal-500 text-white", never: "bg-stone-600 text-white",
};

/** The modes a kind of action can have: things that change nothing outside can only be turned off. */
export function modesFor(p: { key: string; default: "auto" | "ask" }): Mode[] {
  if (p.default === "auto") return ["auto", "never"];
  if (p.key === "spend_money") return ["ask", "auto", "never"];
  return ["ask", "heads_up", "auto", "never"];
}

/** What a step of the plan does: its kind of action's mode, except where it always asks on
 * that step's tool (a personal profile, say). */
export function stepModeOf(perms: Permissions | null) {
  return (actionType: string, tool?: string): Mode => {
    const p = perms?.action_types.find((x) => x.key === actionType);
    if (!p) return "ask";
    if ((p.mode === "auto" || p.mode === "heads_up") && tool && p.asks_on.includes(tool)) return "ask";
    return p.mode;
  };
}

/** One line for a goal's plan: "3 on its own, 2 after a heads-up, 1 waits for the team". */
export function stepCounts(steps: PlanStep[], modeOf: (actionType: string, tool?: string) => Mode, team: string) {
  const n = (m: Mode) => steps.filter((st) => modeOf(st.action_type, st.tool) === m).length;
  const asks = n("ask");
  return [`${n("auto")} on its own`, n("heads_up") ? `${n("heads_up")} after a heads-up` : "", `${asks} ${asks === 1 ? "waits" : "wait"} for ${team}`]
    .filter(Boolean).join(", ");
}

/** Anything people let go out without a yes (on its own or after a heads-up). */
export const goesOut = (p: Permission) => p.default === "ask" && (p.mode === "auto" || p.mode === "heads_up");

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
  const options = modesFor(p);
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
            p.mode === m ? MODE_ON[m] : "bg-white text-muted hover:bg-stone-50",
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
  async function change(key: string, mode: Mode, dailyCap?: number | null) {
    setNote(null);
    setError(null);
    const current = perms?.action_types.find((p) => p.key === key);
    // Moving between "on its own" and "heads-up" keeps the daily limit.
    const cap = dailyCap !== undefined ? dailyCap : current?.daily_cap ?? null;
    let limit: number | null = null;
    if (key === "spend_money" && mode === "auto") {
      const v = prompt("Spend without asking, up to how much per action (USD)?", "5");
      if (!v || !(Number(v) > 0)) return;
      limit = Number(v);
    }
    setBusy(true);
    try {
      const r = await api<{ note: string | null }>(`/api/campaigns/${goalId}/permissions/${key}`, {
        method: "PUT", json: { mode, spend_limit_usd: limit, daily_cap: mode === "auto" || mode === "heads_up" ? cap : null },
      });
      setNote(r.note);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function flag(key: string, why?: string) {
    setError(null);
    try {
      await api(`/api/campaigns/${goalId}/autonomy/flag`, { method: "POST", json: { action_type: key, note: why || null } });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return { perms, note, error, busy, change, flag, reload: load };
}

/** Settings this goal has earned: never applied by itself, one click to accept. */
export function EarnedSuggestions({ perms, onChange, busy }: { perms: Permissions; onChange: (key: string, mode: Mode) => void; busy?: boolean }) {
  const [hidden, setHidden] = useState<string[]>([]);
  const items = perms.action_types.filter((p) => p.suggestion && !hidden.includes(p.key));
  if (!perms.can_edit || items.length === 0) return null;
  return (
    <div className="space-y-2">
      {items.map((p) => (
        <div key={p.key} className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-brand-50 px-3 py-2.5 text-[13px] text-brand-900 ring-1 ring-inset ring-brand-200">
          <Sparkles size={15} className="shrink-0 text-brand-600" />
          <span className="min-w-0 flex-1"><b>{p.label}:</b> {p.suggestion!.reason}</span>
          <span className="flex gap-1.5">
            <button disabled={busy} onClick={() => onChange(p.key, p.suggestion!.mode)}
              className="rounded-md bg-brand-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
              Switch to {MODE_WORDS[p.suggestion!.mode].short.toLowerCase()}
            </button>
            <button onClick={() => setHidden([...hidden, p.key])} className="rounded-md px-2 py-1 text-xs font-semibold text-brand-800 hover:bg-brand-100">Not now</button>
          </span>
        </div>
      ))}
    </div>
  );
}

/** The promise people need to read before they trust Oton with their accounts. */
export function Assurance({ perms, agent, compact }: { perms: Permissions; agent: string; compact?: boolean }) {
  const team = teamName(perms);
  const exceptions = perms.action_types.filter(goesOut);
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-600 text-white"><Lock size={15} /></span>
        <div className="min-w-0 text-sm">
          <div className="font-bold text-emerald-900">{exceptions.length ? "You decide what goes out without a yes" : "Nothing goes out without a yes"}</div>
          <p className="mt-0.5 text-stone-700">
            Before {agent} sends, posts, spends or changes anything, it stops and asks {team}
            {perms.approvers.length ? ` (${perms.approvers.join(", ")})` : ""}. You see exactly what it wants to do, can edit it, and it only goes
            ahead once someone approves.
          </p>
          {!compact && (
            <p className="mt-1.5 text-xs text-stone-600">
              This is enforced by Oton itself, not left to the AI: final clicks like Send, Post and Pay are blocked unless an approval covers
              them, and every app action is checked against these settings before it runs.
            </p>
          )}
          {exceptions.length > 0 && (
            <p className="mt-2 rounded-md bg-signal-50 px-2.5 py-1.5 text-xs text-signal-900 ring-1 ring-signal-200">
              <b>Except:</b> {exceptionWords(exceptions)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

const VERBS: Record<string, string> = {
  engage: "like and follow", reply: "reply and comment", publish_post: "post", publish_article: "publish articles",
  send_message: "send messages and emails", modify_account: "change accounts or profiles", delete_content: "delete things",
  spend_money: "spend money", other_write: "change anything else", research: "research", read_data: "read app data",
  create_draft: "write drafts", propose_code: "open pull requests", merge_content: "merge small content changes", merge_code: "merge code",
};
const verbFor = (k: string) => VERBS[k] || k;
const capWords = (p: Permission) => [p.daily_cap ? `up to ${p.daily_cap} a day` : "", p.spend_limit_usd ? `up to ${usd(p.spend_limit_usd)} each` : ""].filter(Boolean).join(", ");

/** "you let it post (after a heads-up, up to 5 a day) and like and follow (on its own)." */
export function exceptionWords(items: Permission[]) {
  const parts = (m: Mode) => items.filter((p) => p.mode === m).map((p) => verbFor(p.key) + (capWords(p) ? ` (${capWords(p)})` : ""));
  const auto = parts("auto");
  const heads = parts("heads_up");
  return [
    auto.length ? `it may ${joinWords(auto)} on its own.` : "",
    heads.length ? `${auto.length ? "It" : "it"} may ${joinWords(heads)} after a heads-up you can stop.` : "",
  ].filter(Boolean).join(" ");
}
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
function CapInput({ p, onChange, disabled }: { p: Permission; onChange: (cap: number | null) => void; disabled?: boolean }) {
  const [v, setV] = useState(p.daily_cap ? String(p.daily_cap) : "");
  const save = () => {
    const n = v.trim() ? Math.round(Number(v)) : null;
    if (n === p.daily_cap || (n !== null && !(n >= 1 && n <= 1000))) return setV(p.daily_cap ? String(p.daily_cap) : "");
    onChange(n);
  };
  return (
    <label className="flex items-center gap-1.5 text-[11.5px] text-muted">
      At most
      <input inputMode="numeric" aria-label={`Daily limit for ${p.label}`} disabled={disabled} value={v} placeholder="no limit"
        onChange={(e) => setV(e.target.value.replace(/[^0-9]/g, ""))} onBlur={save} onKeyDown={(e) => e.key === "Enter" && save()}
        className="h-6 w-16 rounded border border-line px-1.5 text-[11.5px] text-ink" />
      a day, then it asks
    </label>
  );
}

export function PermissionsEditor({ perms, onChange, busy }: { perms: Permissions; onChange: (key: string, mode: Mode, dailyCap?: number | null) => void; busy?: boolean }) {
  const team = teamName(perms);
  const groups: { mode: Mode; title: string; hint: string }[] = [
    { mode: "auto", title: "Does on its own", hint: "Nothing here leaves Oton or changes your accounts, unless you moved it here." },
    { mode: "heads_up", title: "Heads-up, then goes ahead", hint: `${team[0].toUpperCase() + team.slice(1)} sees it first and can edit or stop it.` },
    { mode: "ask", title: `Asks ${team} first`, hint: "It shows exactly what it wants to do and waits for a yes." },
    { mode: "never", title: "Never does", hint: "Blocked outright, whatever it thinks." },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
                  <div className="text-[13px] font-semibold">{p.label}{capWords(p) ? ` (${capWords(p)})` : ""}</div>
                  <div className="text-[11.5px] text-muted">{p.description}</div>
                  {p.only_on.length > 0 && p.mode === "ask" && <div className="text-[11.5px] text-emerald-700">Except on {p.only_on.join(", ")}: without asking</div>}
                  {p.asks_on.length > 0 && p.mode !== "ask" && p.mode !== "never" && <div className="text-[11.5px] text-signal-800">Always asks on {p.asks_on.join(", ")}</div>}
                  {p.source === "downgrade" && p.mode === "ask" && <div className="text-[11px] text-signal-800">Asks again because some were stopped or flagged</div>}
                  {(p.mode === "auto" || p.mode === "heads_up") && p.default === "ask" && perms.can_edit && (
                    <CapInput p={p} disabled={busy} onChange={(cap) => onChange(p.key, p.mode, cap)} />
                  )}
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
  const agent = "Oton";
  const [book, setBook] = useState<Playbook | null>(goal.playbook ?? null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [open, setOpen] = useState(defaultOpen);
  const [showAll, setShowAll] = useState(false);
  const { perms, note, error, busy, change, reload } = usePermissions(goal.id);
  // Starting a goal applies its autonomy settings: show them.
  useEffect(() => {
    reload();
  }, [goal.status, reload]);

  useEffect(() => {
    if (goal.playbook) {
      setBook(goal.playbook);
      return;
    }
    api<Playbook>(`/api/campaigns/${goal.id}/playbook`, { method: "POST" }).then(setBook).catch((e) => setPlanError((e as Error).message));
  }, [goal.id, goal.playbook]);

  const modeOf = stepModeOf(perms);
  const out = perms ? perms.action_types.filter(goesOut) : [];
  return (
    <section className="rounded-2xl border border-line bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <ShieldCheck size={18} className="text-emerald-600" />
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold">How {agent} works on this goal</span>
          <span className="block text-xs text-muted">
            {book ? `${book.steps.length} steps` : "Working out the steps…"}
            {book && perms ? ` · ${stepCounts(book.steps, modeOf, teamName(perms))} · you can change any of it` : ""}
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
            {book && perms && !showAll && <StepList steps={book.steps} modeOf={modeOf} team={teamName(perms)} />}
            {book && perms && showAll && (
              <div className="space-y-3">
                <PlanSteps steps={book.steps} perms={perms} editable onChange={change} busy={busy} />
                <p className="text-xs text-muted">Changing a step changes every step of the same kind (for example, all &quot;send&quot; steps).</p>
              </div>
            )}
          </div>
          {perms && <EarnedSuggestions perms={perms} onChange={change} busy={busy} />}
          {perms && (
            <p className="flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[13px] text-emerald-900">
              <Lock size={14} className="mt-0.5 shrink-0" />
              <span>
                {out.length ? <b>You decide what goes out without a yes.</b> : <b>Nothing goes out without a yes.</b>} Anything else {agent} wants to send,
                post, spend or change waits for {teamName(perms)}, with exactly what it wants to do. This is enforced by Oton, not left to the AI.
                {out.length > 0 && <span className="mt-1 block text-signal-800">Except: {exceptionWords(out)}</span>}
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
export function StepList({ steps, modeOf, team }: { steps: PlanStep[]; modeOf: (actionType: string, tool?: string) => Mode; team?: string }) {
  return (
    <ol className="relative space-y-3 before:absolute before:bottom-3 before:left-[13px] before:top-3 before:border-l-2 before:border-stone-200">
      {steps.map((st, i) => {
        const mode = modeOf(st.action_type, st.tool);
        return (
          <li key={i} className="relative flex items-start gap-3">
            <span className={cx("z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ring-white",
              mode === "auto" ? "bg-emerald-100 text-emerald-700" : mode === "heads_up" ? "bg-sky-100 text-sky-700" : mode === "ask" ? "bg-signal-100 text-signal-700" : "bg-stone-100 text-stone-400")}>
              {MODE_ICON[mode]}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className={cx("text-[13.5px] leading-snug", mode === "never" && "text-stone-400 line-through")}>{st.text}</div>
              <div className={cx("text-[11.5px] font-semibold", mode === "auto" ? "text-emerald-700" : mode === "heads_up" ? "text-sky-700" : mode === "ask" ? "text-signal-700" : "text-stone-400")}>
                {mode === "auto" ? "Automatic" : mode === "heads_up" ? `Heads-up to ${team ? team.replace(/^the /, "") : "you"}, then goes ahead` : mode === "ask" ? `Waits for ${team ? team.replace(/^the /, "") : "your"} OK` : "Turned off"}
                {TOOL_LABELS[st.tool] ? <span className="font-normal text-muted"> · {TOOL_LABELS[st.tool]}</span> : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
