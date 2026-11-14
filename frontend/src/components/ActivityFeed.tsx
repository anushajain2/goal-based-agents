"use client";

import {
  AlertTriangle,
  Ban,
  Bell,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Compass,
  Info,
  RefreshCw,
  Send,
  ThumbsDown,
  ThumbsUp,
  Wallet,
  XCircle,
} from "lucide-react";
import { ReactNode, useState } from "react";

import { ActivityItem, timeAgo, usd } from "@/lib/api";
import { Badge, cx } from "./ui";

const KEY_KINDS = new Set(["action", "blocked", "decision", "request", "cycle", "strategy", "note", "budget", "error"]);

function iconFor(a: ActivityItem): ReactNode {
  if (a.kind === "action") return a.status === "failed" ? <XCircle size={16} className="text-red-600" /> : <Send size={16} className="text-brand-600" />;
  if (a.kind === "blocked") return <Ban size={16} className="text-red-600" />;
  if (a.kind === "decision") return a.status === "approved" ? <ThumbsUp size={16} className="text-emerald-600" /> : <ThumbsDown size={16} className="text-gray-500" />;
  if (a.kind === "request") return <Bell size={16} className="text-amber-600" />;
  if (a.kind === "cycle") return <RefreshCw size={16} className="text-violet-600" />;
  if (a.kind === "strategy") return <Compass size={16} className="text-violet-600" />;
  if (a.kind === "metric") return <BarChart3 size={16} className="text-gray-500" />;
  if (a.kind === "budget") return <Wallet size={16} className="text-red-600" />;
  if (a.kind === "error") return <AlertTriangle size={16} className="text-red-600" />;
  if (a.kind === "note") return <Info size={16} className="text-brand-600" />;
  return <CheckCircle2 size={16} className="text-gray-400" />;
}

function Details({ d }: { d: Record<string, unknown> }) {
  const shown: [string, unknown][] = [];
  const order = ["reason", "content", "strategy", "arguments", "result", "error", "note", "edited_fields", "url", "message", "next_check_in", "action"];
  for (const k of order) if (d[k] !== undefined && d[k] !== null && d[k] !== "") shown.push([k, d[k]]);
  if (!shown.length) return <p className="text-xs text-muted">No more details.</p>;
  return (
    <dl className="space-y-2 text-xs">
      {shown.map(([k, v]) => (
        <div key={k}>
          <dt className="font-semibold capitalize text-muted">{k.replace(/_/g, " ")}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap break-words font-mono text-[12px]">{typeof v === "string" ? v : JSON.stringify(v, null, 2)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const list = [...items].reverse().filter((a) => all || KEY_KINDS.has(a.kind));
  return (
    <div>
      <div className="flex items-center justify-between border-b border-line px-4 py-2 text-xs">
        <span className="text-muted">{list.length} entries · newest first</span>
        <div className="inline-flex overflow-hidden rounded-md border border-line font-semibold">
          <button className={cx("px-2.5 py-1", !all ? "bg-brand-50 text-brand-700" : "bg-white text-muted")} onClick={() => setAll(false)}>
            Key actions
          </button>
          <button className={cx("px-2.5 py-1", all ? "bg-brand-50 text-brand-700" : "bg-white text-muted")} onClick={() => setAll(true)}>
            Everything
          </button>
        </div>
      </div>
      {list.length === 0 && <p className="px-4 py-10 text-center text-sm text-muted">Nothing yet. Activity shows up here as the agent works.</p>}
      <ul>
        {list.map((a) => {
          const expanded = open === a.id;
          return (
            <li key={a.id} className={cx("border-b border-line/70 last:border-0", a.kind === "cycle" && "bg-violet-50/40")}>
              <button className="flex w-full items-start gap-3 px-4 py-2.5 text-left hover:bg-gray-50" onClick={() => setOpen(expanded ? null : a.id)}>
                <span className="mt-0.5">{iconFor(a)}</span>
                <span className="min-w-0 flex-1">
                  <span className={cx("block text-[13.5px]", a.kind === "cycle" && "font-semibold")}>{a.title}</span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    <span title={new Date(a.created_at).toLocaleString()}>{timeAgo(a.created_at)}</span>
                    {a.channel && <Badge>{a.channel}</Badge>}
                    {a.status === "blocked" && <Badge tone="red">blocked</Badge>}
                    {a.status === "failed" && <Badge tone="red">failed</Badge>}
                    {a.status === "waiting" && <Badge tone="amber">waiting for you</Badge>}
                    {a.details?.approved_by_user === true && <Badge tone="green">you approved</Badge>}
                    {a.details?.edited_by_user === true && <Badge tone="blue">you edited</Badge>}
                  </span>
                </span>
                {a.cost_usd !== null && <span className="tabular text-xs text-muted">{usd(a.cost_usd)}</span>}
                <ChevronDown size={15} className={cx("mt-0.5 text-gray-400 transition", expanded && "rotate-180")} />
              </button>
              {expanded && (
                <div className="px-11 pb-3">
                  <Details d={a.details || {}} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
