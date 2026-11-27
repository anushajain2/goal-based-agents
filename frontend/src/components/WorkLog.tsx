"use client";

import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronDown,
  Compass,
  Flag,
  Globe,
  Hand,
  Keyboard,
  Laptop,
  Lightbulb,
  ListChecks,
  MessageCircle,
  MousePointer2,
  PlayCircle,
  Search,
  Settings2,
  ShieldX,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Wallet,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { Fragment, ReactNode, useMemo, useState } from "react";

import { ActivityItem, api, API_URL, Session, timeAgo, usd } from "@/lib/api";
import { UpdateCard } from "./GoalEngine";
import { Badge, cx } from "./ui";

/** Entries shown in "Highlights": what the employee did, decided, asked or learned. */
const HIGHLIGHT_KINDS = new Set(["report", "action", "blocked", "decision", "request", "plan", "strategy", "metric", "note", "budget", "error"]);

type Meta = { icon: ReactNode; tone: string; label: string; minor?: boolean };

function metaFor(a: ActivityItem): Meta {
  const s = 15;
  switch (a.kind) {
    case "action":
      return a.status === "failed"
        ? { icon: <XCircle size={s} />, tone: "bg-red-50 text-red-600", label: "Failed" }
        : { icon: <CheckCircle2 size={s} />, tone: "bg-emerald-50 text-emerald-600", label: "Did" };
    case "blocked":
      return { icon: <ShieldX size={s} />, tone: "bg-red-50 text-red-600", label: "Blocked" };
    case "decision":
      return a.status === "approved"
        ? { icon: <ThumbsUp size={s} />, tone: "bg-emerald-50 text-emerald-600", label: "You approved" }
        : { icon: <ThumbsDown size={s} />, tone: "bg-stone-100 text-stone-500", label: "You declined" };
    case "request":
      return { icon: <Hand size={s} />, tone: "bg-signal-50 text-signal-600", label: "Asked you" };
    case "plan":
      return { icon: <ListChecks size={s} />, tone: "bg-stone-50 text-stone-600", label: "Plan" };
    case "strategy":
      return { icon: <Compass size={s} />, tone: "bg-stone-50 text-stone-600", label: "Strategy" };
    case "metric":
      return { icon: <TrendingUp size={s} />, tone: "bg-stone-50 text-stone-600", label: "Measured" };
    case "note":
      return { icon: <Lightbulb size={s} />, tone: "bg-signal-50 text-signal-600", label: "For you" };
    case "budget":
      return { icon: <Wallet size={s} />, tone: "bg-red-50 text-red-600", label: "Budget" };
    case "error":
      return { icon: <AlertTriangle size={s} />, tone: "bg-red-50 text-red-600", label: "Problem" };
    case "computer":
      return { icon: <Laptop size={s} />, tone: "bg-stone-100 text-stone-600", label: "Waiting for your computer" };
    case "cycle":
      return a.title.startsWith("Session")
        ? { icon: <Flag size={s} />, tone: "bg-stone-100 text-stone-600", label: "Session done" }
        : { icon: <PlayCircle size={s} />, tone: "bg-stone-100 text-stone-600", label: "Session started", minor: true };
    case "update":
      return { icon: <MessageCircle size={13} />, tone: "text-stone-400", label: "Thinking", minor: true };
    case "step": {
      const t = a.title;
      const icon = t.startsWith("Searched") || t.startsWith("Looked up") ? <Search size={13} />
        : t.startsWith("Opened") || t.startsWith("Read ") ? <Globe size={13} />
        : t.startsWith("Clicked") ? <MousePointer2 size={13} />
        : t.startsWith("Typed") ? <Keyboard size={13} />
        : t.startsWith("Took a screenshot") ? <Camera size={13} />
        : <span className="block h-1.5 w-1.5 rounded-full bg-current" />;
      return { icon, tone: a.status === "failed" ? "text-red-500" : "text-stone-400", label: "Step", minor: true };
    }
    default:
      return { icon: <Settings2 size={13} />, tone: "text-stone-400", label: "", minor: true };
  }
}

function Details({ a }: { a: ActivityItem }) {
  const d = (a.details || {}) as Record<string, unknown>;
  const blocks: ReactNode[] = [];
  if (Array.isArray(d.plan) && d.plan.length)
    blocks.push(
      <ol key="plan" className="list-decimal space-y-1 pl-5 text-[13px]">
        {(d.plan as string[]).map((p, i) => <li key={i}>{p}</li>)}
      </ol>,
    );
  const quote = (label: string, v: unknown) =>
    typeof v === "string" && v ? (
      <div key={label}>
        <div className="mb-1 text-[12px] font-semibold text-muted">{label}</div>
        <blockquote className="whitespace-pre-wrap rounded-md border-l-2 border-brand-500 bg-stone-50 px-3 py-2 text-[13px]">{v}</blockquote>
      </div>
    ) : null;
  blocks.push(quote("Why", d.reason), quote("Content", d.content), quote("Strategy", d.strategy), quote("Your note", d.note), quote("Message", d.message), quote("Error", d.error));
  const ed = d.edited_fields as Record<string, string> | undefined;
  if (ed && Object.keys(ed).length) blocks.push(quote("Your edited version", Object.values(ed).join("\n\n")));
  if (d.arguments && typeof d.arguments === "object")
    blocks.push(
      <div key="args">
        <div className="mb-1 text-[12px] font-semibold text-muted">What it sent{d.action ? ` (${d.action})` : ""}</div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 rounded-md bg-stone-50 px-3 py-2 text-[12.5px]">
          {Object.entries(d.arguments as Record<string, unknown>).map(([k, v]) => (
            <Fragment key={k}><dt className="font-medium text-muted">{k}</dt><dd className="whitespace-pre-wrap break-words">{typeof v === "string" ? v : JSON.stringify(v)}</dd></Fragment>
          ))}
        </dl>
      </div>,
    );
  if (typeof d.result === "string" && d.result) blocks.push(quote("Result", d.result.slice(0, 1500)));
  if (typeof d.url === "string" && d.url)
    blocks.push(<a key="url" href={d.url} target="_blank" rel="noreferrer" className="block truncate text-[13px] text-brand-600 hover:underline">{d.url}</a>);
  if (typeof d.screenshot === "string" && d.screenshot)
    // eslint-disable-next-line @next/next/no-img-element
    blocks.push(<img key="shot" src={`${API_URL}/api/screenshots/${d.screenshot}`} alt="Screenshot" className="max-h-64 rounded-md border border-line" />);
  const shown = blocks.filter(Boolean);
  if (!shown.length) return <p className="text-xs text-muted">Nothing more to show for this entry.</p>;
  return <div className="space-y-3">{shown}</div>;
}

// Kinds of action that can go out without a yes (see backend services/autonomy).
const FLAGGABLE = new Set(["engage", "reply", "publish_post", "publish_article", "send_message", "merge_content", "modify_account", "other_write"]);

/** "This shouldn't have gone out": that kind of action asks first again on this goal. */
function FlagButton({ a }: { a: ActivityItem }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | string>("idle");
  if (state === "done") return <span className="text-[12px] font-semibold text-signal-800">Flagged. It asks first from now on</span>;
  return (
    <span onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1">
      <button
        type="button"
        disabled={state === "busy"}
        onClick={async () => {
          const why = window.prompt("What was wrong with it? (optional) It will ask first before doing this again on this goal.", "");
          if (why === null) return;
          setState("busy");
          try {
            await api(`/api/campaigns/${a.campaign_id}/autonomy/flag`, { method: "POST", json: { action_type: a.action_type, note: why.trim() || null } });
            setState("done");
          } catch (err) {
            setState((err as Error).message);
          }
        }}
        className="inline-flex items-center gap-1 rounded px-1 text-[12px] font-semibold text-stone-500 hover:bg-stone-100 hover:text-signal-800"
      >
        <Flag size={11} /> Shouldn&apos;t have gone out
      </button>
      {state !== "idle" && state !== "busy" && <span className="text-[12px] text-red-600">{state}</span>}
    </span>
  );
}

export function LogEntry({ a, showGoal }: { a: ActivityItem; showGoal?: boolean }) {
  const [open, setOpen] = useState(false);
  if (a.kind === "report") {
    const d = a.details as { measured?: string; learned?: string; changing?: string };
    return (
      <li className="py-1.5">
        {showGoal && a.campaign_name && (
          <Link href={`/goals/${a.campaign_id}`} className="mb-1 block text-[12px] font-semibold text-brand-600 hover:underline">{a.campaign_name}</Link>
        )}
        <UpdateCard u={{ measured: d.measured || "", learned: d.learned || "", changing: d.changing || "" }} at={a.created_at} />
      </li>
    );
  }
  const m = metaFor(a);
  const expandable = a.kind !== "update" && a.kind !== "cycle" && Object.keys(a.details || {}).some((k) => k !== "request_id");

  if (m.minor) {
    return (
      <li className="group">
        <button
          disabled={!expandable}
          onClick={() => setOpen(!open)}
          className="flex w-full items-start gap-3 py-1 pl-[7px] pr-2 text-left disabled:cursor-default"
        >
          <span className={cx("mt-[3px] grid w-[18px] shrink-0 place-items-center", m.tone)}>{m.icon}</span>
          <span className={cx("min-w-0 flex-1 text-[12.5px] leading-5 text-stone-600", a.kind === "update" && "italic text-stone-500")}>
            {a.title}
            {showGoal && a.campaign_name && <span className="ml-1.5 not-italic text-stone-400">· {a.campaign_name}</span>}
          </span>
          {a.cost_usd !== null && a.cost_usd > 0 && <span className="tabular shrink-0 text-[12px] text-stone-400">{usd(a.cost_usd)}</span>}
          <span className="w-14 shrink-0 text-right text-[12px] text-stone-400" title={new Date(a.created_at).toLocaleString()}>
            {new Date(a.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
          </span>
        </button>
        {open && <div className="mb-2 ml-9 mr-2"><Details a={a} /></div>}
      </li>
    );
  }

  return (
    <li>
      <button onClick={() => expandable && setOpen(!open)} className={cx("flex w-full items-start gap-3 rounded-lg px-1 py-2 text-left", expandable && "hover:bg-stone-50")}>
        <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-full", m.tone)}>{m.icon}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 text-[12px] font-semibold text-muted">
            {m.label}
            {showGoal && a.campaign_name && (
              <Link href={`/goals/${a.campaign_id}`} onClick={(e) => e.stopPropagation()} className="normal-case tracking-normal text-brand-600 hover:underline">
                {a.campaign_name}
              </Link>
            )}
          </span>
          <span className="mt-0.5 block text-[14px] leading-snug text-ink">{a.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span title={new Date(a.created_at).toLocaleString()}>{timeAgo(a.created_at)}</span>
            {a.channel && <Badge>{a.channel}</Badge>}
            {a.status === "waiting" && <Badge tone="amber">waiting for you</Badge>}
            {a.details?.approved_by_user === true && <Badge tone="green">you approved</Badge>}
            {a.details?.edited_by_user === true && <Badge tone="blue">you edited</Badge>}
            {a.kind === "action" && a.status !== "failed" && a.action_type && FLAGGABLE.has(a.action_type) && a.details?.approved_by_user === false && (
              <>
                <Badge tone="gray">on its own</Badge>
                <FlagButton a={a} />
              </>
            )}
          </span>
        </span>
        {a.cost_usd !== null && a.cost_usd > 0 && <span className="tabular mt-1 shrink-0 text-xs text-muted">{usd(a.cost_usd)}</span>}
        {expandable && <ChevronDown size={15} className={cx("mt-1.5 shrink-0 text-stone-400 transition", open && "rotate-180")} />}
      </button>
      {open && <div className="mb-3 ml-12 mr-2"><Details a={a} /></div>}
    </li>
  );
}

const SESSION_STATUS: Record<string, { label: string; tone: "green" | "amber" | "gray" | "red" | "blue"; live?: boolean }> = {
  queued: { label: "Starting", tone: "blue", live: true },
  running: { label: "Working now", tone: "blue", live: true },
  waiting: { label: "Waiting on you", tone: "amber" },
  completed: { label: "Done", tone: "green" },
  stopped: { label: "Stopped", tone: "gray" },
  failed: { label: "Stopped with a problem", tone: "red" },
};

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function duration(a: string, b: string) {
  const m = Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000));
  return m < 1 ? "under a minute" : m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

type Group = { runId: string | null; items: ActivityItem[] };

/**
 * The work log. Newest first. With `sessions`, entries are grouped into work sessions with a
 * header (status, plan, duration, cost). `view` "highlights" hides small steps behind a toggle.
 */
export function WorkLog({
  items,
  sessions,
  showGoal,
  view,
}: {
  items: ActivityItem[];
  sessions?: Session[];
  showGoal?: boolean;
  view: "highlights" | "everything";
}) {
  const byId = useMemo(() => Object.fromEntries((sessions || []).map((s) => [s.id, s])), [sessions]);
  const groups = useMemo(() => {
    const sorted = [...items].sort((a, b) => b.id - a.id);
    const out: Group[] = [];
    for (const a of sorted) {
      const key = sessions && a.run_id && byId[a.run_id] ? a.run_id : null;
      const last = out[out.length - 1];
      if (last && last.runId === key && key !== null) last.items.push(a);
      else if (last && key === null && last.runId === null) last.items.push(a);
      else out.push({ runId: key, items: [a] });
    }
    return out;
  }, [items, sessions, byId]);

  if (!items.length) return <p className="px-4 py-12 text-center text-sm text-muted">Nothing here yet. Everything Oton does will show up here as it happens.</p>;

  return (
    <div className="space-y-4">
      {groups.map((g, i) =>
        g.runId ? (
          <SessionBlock key={g.runId + i} session={byId[g.runId]} items={g.items} view={view} showGoal={showGoal} />
        ) : (
          <ul key={"loose" + i} className="px-3">
            {g.items.filter((a) => view === "everything" || HIGHLIGHT_KINDS.has(a.kind) || a.kind === "system").map((a) => (
              <LogEntry key={a.id} a={a} showGoal={showGoal} />
            ))}
          </ul>
        ),
      )}
    </div>
  );
}

function SessionBlock({ session, items, view, showGoal }: { session: Session; items: ActivityItem[]; view: "highlights" | "everything"; showGoal?: boolean }) {
  const [showSteps, setShowSteps] = useState(false);
  const st = session.waiting_for === "computer"
    ? { label: "Waiting for your computer", tone: "gray" as const }
    : SESSION_STATUS[session.status] || { label: session.status, tone: "gray" as const };
  const all = items.filter((a) => a.kind !== "cycle");
  const plan = all.find((a) => a.kind === "plan");
  const latestUpdate = all.find((a) => a.kind === "update");
  const visible = view === "everything" || showSteps ? all : all.filter((a) => HIGHLIGHT_KINDS.has(a.kind) && a.kind !== "plan");
  const hidden = all.length - visible.length - (view === "everything" || showSteps ? 0 : plan ? 1 : 0);
  const end = st.live ? new Date().toISOString() : session.updated_at;

  return (
    <section className={cx("overflow-hidden rounded-xl border bg-white", st.live ? "border-brand-500/50 shadow-[0_0_0_3px_rgba(37,99,235,0.08)]" : "border-line")}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-stone-50/70 px-4 py-2.5">
        <span className="text-[13px] font-semibold">Work session {session.number}</span>
        <Badge tone={st.tone}>
          {st.live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />}
          {st.label}
        </Badge>
        <span className="text-xs text-muted">
          {new Date(session.started_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {duration(session.started_at, end)}
        </span>
        <span className="ml-auto text-xs text-muted">
          {plural(session.counts.action || 0, "action")}, {plural(session.counts.step || 0, "step")}, <span className="tabular font-semibold text-ink">{usd(session.cost_usd)}</span>
        </span>
      </header>

      {st.live && latestUpdate && (
        <div className="flex items-center gap-2 border-b border-line bg-brand-50/50 px-4 py-2 text-[13px] text-brand-700">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
          <span className="truncate">{latestUpdate.title}</span>
        </div>
      )}

      <div className="px-3 py-2">
        {plan && view === "highlights" && !showSteps && (
          <div className="mx-1 my-2 rounded-lg bg-stone-50/60 px-3 py-2.5">
            <div className="text-[12px] font-semibold text-stone-700">Plan for this session</div>
            <p className="mt-1 text-[13px]">{plan.title}</p>
            {Array.isArray(plan.details?.plan) && (
              <ol className="mt-1.5 list-decimal space-y-0.5 pl-5 text-[13px] text-stone-700">
                {(plan.details.plan as string[]).map((p, i) => <li key={i}>{p}</li>)}
              </ol>
            )}
          </div>
        )}
        <ul>
          {visible.map((a) => <LogEntry key={a.id} a={a} showGoal={showGoal} />)}
        </ul>
        {view === "highlights" && hidden > 0 && (
          <button onClick={() => setShowSteps(!showSteps)} className="mx-1 my-1 text-xs font-semibold text-brand-600 hover:underline">
            {showSteps ? "Show highlights only" : `Show ${hidden === 1 ? "1 more step" : `all ${hidden} smaller steps`} (pages opened, searches, clicks, notes)`}
          </button>
        )}
        {view === "highlights" && !visible.length && !plan && <p className="px-2 py-2 text-xs text-muted">No key actions in this session yet.</p>}
      </div>

      {session.summary && (
        <footer className="border-t border-line bg-stone-50/70 px-4 py-2.5 text-[13px]">
          <span className="font-semibold">Outcome: </span>
          {session.summary}
        </footer>
      )}
      {session.error && !session.summary && (
        <footer className="border-t border-red-100 bg-red-50 px-4 py-2.5 text-[13px] text-red-800">{session.error}</footer>
      )}
    </section>
  );
}

export function ViewToggle({ value, onChange }: { value: "highlights" | "everything"; onChange: (v: "highlights" | "everything") => void }) {
  return (
    <div className="inline-flex shrink-0 overflow-hidden rounded-md border border-line text-xs font-semibold">
      {(["highlights", "everything"] as const).map((v) => (
        <button key={v} onClick={() => onChange(v)} className={cx("whitespace-nowrap px-2.5 py-1.5", value === v ? "bg-ink text-white" : "bg-white text-muted hover:text-ink")}>
          {v === "highlights" ? "Highlights" : "Every step"}
        </button>
      ))}
    </div>
  );
}
