"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Empty = same origin: Next.js proxies /api/* to the backend (see next.config.mjs).
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export type Budget = {
  total: number;
  spent: number;
  reserved: number;
  ai_usage: number;
  other_spend: number;
  remaining: number;
  today: number;
  daily_cap: number | null;
};

export type Campaign = {
  id: string;
  name: string;
  goal_type: string;
  goal_description: string;
  primary_metric: string;
  target_value: number | null;
  done_when: string;
  category: string;
  use_case: string;
  client_name: string;
  actions_taken: number;
  agent: { id: string; name: string; title: string } | null;
  department: { id: string; name: string } | null;
  can_manage: boolean | null;
  last_activity: { title: string; kind: string; at: string } | null;
  status: "draft" | "active" | "paused" | "out_of_budget" | "completed";
  channels: string[];
  budget: Budget;
  results: { baseline: number | null; current: number | null; results: number | null };
  cost_per_result: number | null;
  pending_requests: number;
  cycles_completed: number;
  next_cycle_at: string | null;
  end_date: string | null;
  daily_cap: number | null;
  budget_total: number;
  cycle_hours: number;
  current_run: { id: string; status: string; cycle_number: number; summary: string | null; error: string | null } | null;
  created_at: string;
  context?: string;
  strategy?: string;
  metrics?: { metric: string; value: number; source: string; note: string; recorded_at: string }[];
};

export type ActivityItem = {
  id: number;
  campaign_name?: string | null;
  campaign_id: string;
  run_id: string | null;
  kind: string;
  action_type: string | null;
  channel: string | null;
  title: string;
  status: string;
  cost_usd: number | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type UserRequest = {
  id: string;
  campaign_id: string;
  campaign_name: string | null;
  kind: "action" | "login" | "connect";
  status: string;
  action_type: string | null;
  action_label: string | null;
  scope: string | null;
  title: string;
  rationale: string;
  preview: {
    fields?: Record<string, unknown>;
    editable?: string[];
    url?: string;
    site?: string;
    app?: string;
    action?: string;
    action_name?: string;
    details?: string;
    screenshot?: string | null;
  };
  est_spend_usd: number | null;
  decision_note: string | null;
  created_at: string;
  department_id: string | null;
  department_name: string | null;
  agent_name: string | null;
  approvers: string[];
  can_decide: boolean;
  decided_by_name: string | null;
};

export type Session = {
  id: string;
  number: number;
  status: string;
  summary: string | null;
  error: string | null;
  started_at: string;
  updated_at: string;
  cost_usd: number;
  ai_calls: number;
  counts: Record<string, number>;
};

export type Overview = {
  goals: { total: number; active: number };
  working_on: string[];
  waiting_on_you: number;
  waiting_goals: string[];
  now: ActivityItem | null;
  next_check_in: string | null;
  spend_this_month: { total: number; ai_usage: number; other: number };
  budget_total: number;
  actions_this_week: number;
  steps_this_week: number;
};

export type Level = "goal" | "department" | "org";
export type Exclusion = { id: string; campaign_id: string | null; department_id: string | null; level: Level; kind: string; value: string; label: string | null };
export type Grant = {
  id: string;
  campaign_id: string | null;
  campaign_name: string | null;
  action_type: string;
  action_label: string;
  scope: string | null;
  spend_limit_usd: number | null;
  created_at: string;
  department_id?: string | null;
  department_name?: string | null;
  level: Level;
};

export type Person = { id: string; name: string; email: string };
export type AgentSummary = { id: string; name: string; title: string; goals: number; active_goals: number; spent: number; working: boolean; needs_you: number };
export type DepartmentInfo = { id: string; name: string; kind: string; people: Person[]; agents: AgentSummary[] };
export type OrgInfo = {
  org: { id: string; name: string };
  me: Person & { role: "owner" | "admin" | "member"; department_ids: string[]; is_admin: boolean };
  departments: DepartmentInfo[];
  members: (Person & { role: "owner" | "admin" | "member"; department_ids: string[] })[];
  invitations: { id: string; email: string; role: string; department_ids: string[]; created_at: string }[];
};

/** Library category key -> the kind of department that usually handles it. */
export const CATEGORY_DEPARTMENT: Record<string, string> = {
  sales: "sales", marketing: "marketing", research: "research", product: "product", fundraising: "fundraising",
  hiring: "hiring", partnerships: "partnerships", success: "success", finance: "finance", operations: "operations",
  pr: "pr", intel: "research", agency: "sales", founder: "operations", legal: "operations",
};

export type ActionType = { key: string; label: string; description: string; default: "auto" | "ask" };

export class ApiError extends Error {
  constructor(message: string, public status = 0) {
    super(message);
  }
}

export type User = { id: string; email: string; name: string };

/** Signed out (or the session expired) while using the app: go to the login page, then come back. */
function toLogin() {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  const next = window.location.pathname + window.location.search;
  window.location.href = `/login?next=${encodeURIComponent(next)}`;
}

export async function api<T = unknown>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init || {};
  const res = await fetch(API_URL + path, {
    ...rest,
    headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...(rest.headers || {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {}
    if (res.status === 401 && !path.startsWith("/api/auth/")) toLogin();
    if (res.status === 409 && msg === "no_organization" && typeof window !== "undefined" && !window.location.pathname.startsWith("/welcome")) {
      window.location.href = "/welcome";
    }
    throw new ApiError(msg, res.status);
  }
  return res.json() as Promise<T>;
}

/** Subscribe to live server events (activity, requests, campaign changes). */
type LiveEvent = { type: string; campaign_id: string | null };
type Listener = (e: LiveEvent) => void;

// One shared connection for the whole tab. Browsers allow only ~6 connections per site, so
// one EventSource per panel would starve normal requests and hang the page.
const listeners = new Set<Listener>();
let shared: EventSource | null = null;

function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  if (!shared) {
    shared = new EventSource(API_URL + "/api/events");
    const handler = (ev: MessageEvent) => {
      let e: LiveEvent;
      try {
        e = JSON.parse(ev.data);
      } catch {
        return;
      }
      listeners.forEach((l) => l(e));
    };
    for (const t of ["activity", "request", "campaign", "run", "metric", "guardrails"]) shared.addEventListener(t, handler);
  }
  return () => {
    listeners.delete(fn);
    if (!listeners.size && shared) {
      shared.close();
      shared = null;
    }
  };
}

export function useLiveEvents(onEvent: Listener, campaignId?: string) {
  const ref = useRef(onEvent);
  ref.current = onEvent;
  useEffect(
    () =>
      subscribe((e) => {
        // campaign_id null means "something changed somewhere": every panel refreshes.
        if (!campaignId || !e.campaign_id || e.campaign_id === campaignId) ref.current(e);
      }),
    [campaignId],
  );
}

/** Fetch JSON, refetch on live events (debounced) and every `pollMs` as a fallback. */
export function useApi<T>(path: string | null, opts: { campaignId?: string; pollMs?: number; live?: boolean } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    reload();
    const id = setInterval(reload, opts.pollMs ?? 15000);
    return () => clearInterval(id);
  }, [reload, opts.pollMs]);

  useLiveEvents(() => {
    if (opts.live === false) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(reload, 250);
  }, opts.campaignId);

  return { data, error, loading, reload, setData };
}

export const usd = (n: number | null | undefined, digits?: number) => {
  if (n === null || n === undefined) return "—";
  // Small amounts (a single AI step, cost per follower) need more precision than cents.
  const d = digits ?? (n !== 0 && Math.abs(n) < 0.1 ? (Math.abs(n) < 0.01 ? 4 : 3) : 2);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
};

export const num = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  const s = Math.round((Date.now() - d) / 1000);
  const abs = Math.abs(s);
  const fmt = (v: number, u: string) => `${v} ${u}${v === 1 ? "" : "s"}`;
  const out =
    abs < 60 ? "just now" : abs < 3600 ? fmt(Math.round(abs / 60), "min") : abs < 86400 ? fmt(Math.round(abs / 3600), "hour") : fmt(Math.round(abs / 86400), "day");
  if (out === "just now") return out;
  return s >= 0 ? `${out} ago` : `in ${out}`;
}
