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
  origin: string; // "setup" = suggested by setup research
  suggested_reason: string;
  first_deliverable: string;
  key_results: string[];
  target: TargetView | null;
  budget_basis: BudgetBasis | null;
  has_playbook: boolean;
  playbook?: Playbook | null; // full goal only
  pace?: { per_session_usd: number; sessions_measured: number; sessions_left: number; days_left: number } | null;
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

export type Period = "week" | "month" | "quarter";
export type TargetView = {
  period: Period | null; target: number | null; status?: "planned" | "active"; progress: number | null;
  start?: string | null; end?: string | null; days_left?: number | null; why?: string; set_by?: string;
  history: { period: Period; target: number; result: number | null; status: "hit" | "missed" | "replaced"; start?: string; end?: string }[];
};
export const PERIOD_WORD: Record<Period, string> = { week: "this week", month: "this month", quarter: "this quarter" };
export const PER_PERIOD: Record<Period, string> = { week: "a week", month: "a month", quarter: "a quarter" };

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
  kind: "action" | "login" | "connect" | "question" | "review" | "proposal";
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
    question?: string;
    options?: string[];
    deliverable_id?: string;
    handoff_to?: string | null;
    change?: { type: "target" | "pause" | "resume" | "new_goal" | "new_agent"; target?: number; period?: Period; by?: "agent" | "lead";
      agent?: { name: string; title: string; objective: string } };
    current?: TargetView | null;
    source?: "lead";
    lead?: string;
    budget_usd?: number;
  };
  est_spend_usd: number | null;
  decision_note: string | null;
  created_at: string;
  department_id: string | null;
  department_name: string | null;
  agent_name: string | null;
  agent_id: string | null;
  agent_title: string | null;
  campaign_metric: string | null;
  routed_to_me: boolean;
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
export type AgentSummary = {
  id: string; name: string; title: string; objective: string; reports_to: Person | null;
  handoff_to_agent_id: string | null; handoff_review: boolean;
  goals: number; active_goals: number; spent: number; working: boolean; needs_you: number;
};
export type LeadReviewInfo = {
  id: string; status: "queued" | "running" | "done" | "failed"; health: "" | "on_track" | "mixed" | "off_track"; summary: string;
  proposals: { type: string; goal_id: string; title: string; reasoning: string; request_id: string }[];
  research?: { looked_at?: string[]; sources?: { url: string; title: string }[] };
  error: string | null; cost_usd: number; created_at: string;
};
export type LeadInfo = {
  name: string; enabled: boolean; review_days: number; monthly_cap_usd: number; spent_this_month_usd: number;
  last_review_at: string | null; last: LeadReviewInfo | null;
};
/** head = the person on the team its AI employees report to (empty: the owner). */
export type DepartmentInfo = { id: string; name: string; kind: string; head: Person | null; people: Person[]; agents: AgentSummary[]; lead: LeadInfo };
export type BudgetBasis = {
  per_session_usd: number; sessions: number; cycle_hours: number; days: number; ai_usd: number; paid_spend_usd: number;
  suggested_usd: number; basis: "typical" | "history"; history_sessions: number; chosen_usd?: number;
  starter?: boolean; full_days?: number; full_sessions?: number; full_usd?: number; // one-week starter budgets
};
export type Mode = "auto" | "ask" | "never";
export type PlanStep = { text: string; action_type: string; tool: string };
export type Playbook = { steps: PlanStep[]; source: "setup" | "generated" | "default" };
export type Permission = {
  key: string; label: string; description: string; default: "auto" | "ask"; mode: Mode;
  set_at: "default" | "goal" | "department" | "org"; spend_limit_usd: number | null; only_on: string[];
};
export type Permissions = { action_types: Permission[]; department: string | null; approvers: string[]; built_in_rules: string[]; can_edit: boolean };
export type ToolNeed = {
  key: string; label: string; app: string | null; site: string | null; login_url: string | null;
  steps: number[]; required: boolean; status: "connected" | "signed_in" | "missing"; can_connect_app: boolean;
  kind: "app" | "github" | "postgres";
};
export type Deliverable = {
  id: string; kind: "prd" | "analysis" | "report"; title: string; summary: string; content: string;
  status: "submitted" | "approved" | "changes_requested" | "handed_off"; campaign_id: string; agent_id: string | null;
  handed_to_campaign_id: string | null; created_at: string;
};
export type IntegrationInfo = { id: string; kind: "github" | "postgres" | "github_pending" | "composio"; name: string; config: Record<string, unknown>; error: string | null };
export type Readiness = {
  tools: ToolNeed[]; composio_enabled: boolean; mcp_servers: { id: string; name: string; tools: number; error: string | null }[];
  permissions: Permission[]; department: string | null; approvers: string[]; playbook: Playbook | null;
};
export type McpServerInfo = {
  id: string; name: string; url: string; has_key: boolean; error: string | null; checked_at: string | null;
  tools: { name: string; description: string; kind: string; kind_label: string; asks_first: boolean }[];
};

/** Plain names for the tools in a plan (keys from the backend catalog). */
export const TOOL_LABELS: Record<string, string> = {
  web: "Web", none: "", database: "Database", googleanalytics: "Google Analytics", mixpanel: "Mixpanel", amplitude: "Amplitude",
  posthog: "PostHog", linear: "Linear", jira: "Jira", github: "GitHub", gmail: "Gmail", outlook: "Outlook", googlecalendar: "Google Calendar", calendly: "Calendly",
  linkedin: "LinkedIn", twitter: "X", instagram: "Instagram", facebook: "Facebook", reddit: "Reddit", youtube: "YouTube",
  hubspot: "HubSpot", salesforce: "Salesforce", pipedrive: "Pipedrive", apollo: "Apollo", slack: "Slack", notion: "Notion",
  googlesheets: "Google Sheets", googledocs: "Google Docs", mailchimp: "Mailchimp", shopify: "Shopify", stripe: "Stripe",
  googleads: "Google Ads", metaads: "Meta Ads", producthunt: "Product Hunt", wordpress: "WordPress", webflow: "Webflow",
  quickbooks: "QuickBooks", xero: "Xero", ramp: "Ramp", greenhouse: "Greenhouse", ashby: "Ashby", bamboohr: "BambooHR",
  gusto: "Gusto", googleworkspace: "Google Workspace admin", okta: "Okta", docusign: "DocuSign", googledrive: "Google Drive",
  zendesk: "Zendesk", intercom: "Intercom",
};

export type CompanyProfile = {
  summary: string; offering: string; customers: string; business_model: string; stage: string; funding: string;
  team: string; traction: string; current_focus: string[]; challenges: string[];
  sources?: { url: string; title: string }[]; researched_at?: string;
  revenue?: string; size?: "tiny" | "small" | "mid" | "large"; size_reason?: string; later?: LaterFunction[];
};
export type LaterFunction = { kind: string; name: string; when: string };
export const SIZE_LABEL: Record<string, string> = { tiny: "1-10 people", small: "11-50 people", mid: "51-250 people", large: "250+ people" };
export type SetupStep = { key: string; label: string; status: "pending" | "running" | "done" | "failed" | "skipped"; detail: string };
export type PlannedGoal = {
  name: string; goal_description: string; done_when: string; primary_metric: string; target_value: number | null; budget_usd: number;
  why: string; category: string; steps?: PlanStep[]; budget_basis?: BudgetBasis; first_week?: string; start_here?: boolean;
};
export type SetupInfo = {
  org: { id: string; name: string; website: string; description: string; profile: CompanyProfile | null };
  setup: null | {
    id: string; status: "queued" | "running" | "done" | "failed"; steps: SetupStep[]; error: string | null; cost_usd: number;
    plan: { profile: CompanyProfile; departments: { kind: string; name: string; agent_title: string; why: string; goals: PlannedGoal[] }[] } | null;
    created: { departments: string[]; agents: string[]; goals: string[] } | null; created_at: string;
  };
  can_research: boolean; can_run: boolean; has_team: boolean;
};
export type OrgInfo = {
  org: { id: string; name: string; website: string; description: string; profile: CompanyProfile | null };
  me: Person & { role: "owner" | "admin" | "member"; department_ids: string[]; is_admin: boolean };
  departments: DepartmentInfo[];
  members: (Person & { role: "owner" | "admin" | "member"; department_ids: string[] })[];
  invitations: { id: string; email: string; role: string; department_ids: string[]; head_department_ids: string[]; created_at: string }[];
};

/** Library category key -> the kind of department that usually handles it. */
export const CATEGORY_DEPARTMENT: Record<string, string> = {
  sales: "sales", marketing: "marketing", research: "research", product: "product", fundraising: "fundraising",
  hiring: "hiring", partnerships: "partnerships", success: "success", finance: "finance", operations: "operations",
  pr: "pr", intel: "research", agency: "sales", founder: "operations", legal: "legal", it: "it",
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
