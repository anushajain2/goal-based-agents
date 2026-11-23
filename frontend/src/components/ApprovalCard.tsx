"use client";

import { ArrowRight, Check, Compass, ExternalLink, FileText, HelpCircle, KeyRound, Link2, Lock, MessageSquare, ShieldQuestion, TrendingUp, Users, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, API_URL, num, OrgInfo, PER_PERIOD, timeAgo, usd, useApi, UserRequest } from "@/lib/api";
import { TargetHistory } from "./Target";
import { AgentAvatar } from "./team";
import { Badge, Button, Card, cx, ErrorNote, Input, Select, Textarea } from "./ui";

export const KIND_BADGE: Record<UserRequest["kind"], { label: string; tone: "amber" | "violet" | "blue" | "green"; icon: React.ReactNode }> = {
  action: { label: "Approval", tone: "amber", icon: <ShieldQuestion size={12} /> },
  question: { label: "Question", tone: "blue", icon: <HelpCircle size={12} /> },
  login: { label: "Sign-in", tone: "violet", icon: <KeyRound size={12} /> },
  connect: { label: "Connect an app", tone: "blue", icon: <Link2 size={12} /> },
  review: { label: "Review", tone: "green", icon: <FileText size={12} /> },
  proposal: { label: "Suggestion", tone: "green", icon: <TrendingUp size={12} /> },
};

const PROPOSAL_YES: Record<string, string> = { target: "Approve new target", pause: "Pause it", resume: "Restart it", new_goal: "Start this goal" };

/**
 * One thing an AI employee needs from a person: an approval, an answer, a sign-in or an app
 * connection. `detail` is the roomy layout used in the Needs you inbox.
 */
export function ApprovalCard({ req, onDone, showCampaign, detail }: { req: UserRequest; onDone: () => void; showCampaign?: boolean; detail?: boolean }) {
  const editable = req.preview.editable || [];
  const fields = req.preview.fields || {};
  const [edits, setEdits] = useState<Record<string, string>>(() => Object.fromEntries(editable.map((k) => [k, String(fields[k] ?? "")])));
  const [remember, setRemember] = useState(false);
  const [rememberScope, setRememberScope] = useState<"goal" | "department" | "org">("goal");
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false, pollMs: 300000 });
  const canDecide = req.can_decide !== false;
  const decided = req.status !== "pending";
  const [anyChannel, setAnyChannel] = useState(false);
  const [limit, setLimit] = useState(req.est_spend_usd ? String(req.est_spend_usd) : "");
  const [rejecting, setRejecting] = useState(false);
  const [commenting, setCommenting] = useState(!!detail);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const agent = req.agent_name || "Your AI employee";
  const to = req.routed_to_me ? "you" : req.approvers?.join(", ") || "an admin";

  async function decide(decision: "approve" | "reject", rememberThis = false) {
    setBusy(true);
    setError(null);
    const changed = Object.fromEntries(Object.entries(edits).filter(([k, v]) => v !== String(fields[k] ?? "")));
    try {
      await api(`/api/requests/${req.id}/decide`, {
        method: "POST",
        json: {
          decision,
          note: note.trim() || null,
          edited_fields: decision === "approve" && Object.keys(changed).length ? changed : null,
          remember: rememberThis,
          remember_scope: rememberScope,
          remember_any_channel: anyChannel,
          spend_limit_usd: req.action_type === "spend_money" && limit ? Number(limit) : null,
        },
      });
      setNote("");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openInAgentChrome(url: string, manual = false) {
    setError(null);
    try {
      await api(manual ? "/api/browser/manual-signin" : "/api/browser/open", { method: "POST", json: { url } });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const k = KIND_BADGE[req.kind] || KIND_BADGE.action;
  const Wrapper = detail ? "div" : Card;

  return (
    <Wrapper className={cx(detail ? "space-y-4" : "p-4")}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        {detail && req.agent_name && <AgentAvatar name={req.agent_name} size={28} />}
        {detail && req.agent_name && (
          <span className="mr-1">
            <span className="block text-[13px] font-semibold text-ink">{req.agent_name}</span>
            <span className="block">{[req.agent_title, req.department_name].filter(Boolean).join(" · ")}</span>
          </span>
        )}
        <Badge tone={k.tone}>{k.icon} {req.kind === "action" ? req.action_label || k.label : k.label}</Badge>
        {req.scope && req.kind !== "question" && <Badge>{req.scope}</Badge>}
        {!detail && req.agent_name && <Badge tone="violet">{req.agent_name}</Badge>}
        {req.preview.source === "lead" && <Badge tone="blue"><Compass size={12} /> From {req.preview.lead}</Badge>}
        {showCampaign && req.campaign_name && (
          <Link href={`/goals/${req.campaign_id}`} className="font-semibold text-brand-600 hover:underline">{req.campaign_name}</Link>
        )}
        <span>{timeAgo(req.created_at)}</span>
      </div>

      <h4 className={cx("font-semibold leading-snug", detail ? "text-xl" : "mt-2 text-[15px]")}>
        {req.kind === "action" ? `${agent} wants to: ${req.title}` : req.kind === "question" ? req.preview.question || req.title : req.title}
      </h4>
      {req.rationale && (
        <p className={cx("text-sm text-muted", !detail && "mt-1")}>
          {req.kind === "question" ? <><b className="text-gray-700">Why it asks:</b> {req.rationale}</> : req.kind === "proposal" ? <><b className="text-gray-700">Why:</b> {req.rationale}</> : req.rationale}
        </p>
      )}

      {req.kind === "proposal" && req.preview.change && (
        <div className={cx("space-y-2 rounded-lg border border-line p-3 text-sm", !detail && "mt-3")}>
          {req.preview.current?.target != null && req.preview.current.period && (
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="w-12 shrink-0 text-xs font-semibold uppercase text-muted">{req.preview.change.type === "new_goal" ? "Target" : "Now"}</span>
              <span>{num(req.preview.current.target)} {req.campaign_metric || "results"} {PER_PERIOD[req.preview.current.period]}
                {req.preview.current.progress != null && <span className="text-muted"> · {num(req.preview.current.progress)} so far</span>}</span>
            </div>
          )}
          {req.preview.change.type === "target" && req.preview.change.period && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="w-12 shrink-0 text-xs font-semibold uppercase text-emerald-700">New</span>
              {canDecide && !decided ? (
                <input inputMode="decimal" aria-label="New target" className="h-8 w-20 rounded-md border border-line px-2 text-sm font-semibold"
                  value={edits.target ?? ""} onChange={(e) => setEdits({ ...edits, target: e.target.value })} />
              ) : <b>{edits.target}</b>}
              <span>{req.campaign_metric || "results"} {PER_PERIOD[req.preview.change.period]}</span>
            </div>
          )}
          {req.preview.change.type === "new_goal" && (
            <p>Starts with a first-week budget of <b>{usd(req.preview.budget_usd ?? 0)}</b>. <Link href={`/goals/${req.campaign_id}`} className="inline-flex items-center gap-0.5 font-semibold text-brand-700 hover:underline">See the plan <ArrowRight size={12} /></Link></p>
          )}
          {req.preview.change.type === "pause" && <p className="text-muted">Pausing stops its work and spending; restart any time.</p>}
          <TargetHistory target={req.preview.current || null} />
          {!decided && <p className="flex items-center gap-1.5 text-xs text-emerald-800"><Lock size={12} /> Nothing changes unless you approve.</p>}
        </div>
      )}

      {req.kind === "review" && req.preview.handoff_to && !decided && (
        <p className={cx("inline-flex items-center gap-1.5 rounded-md bg-violet-50 px-2 py-1 text-xs font-medium text-violet-800", !detail && "mt-2")}>
          Approving sends it to {req.preview.handoff_to}, who starts building it.
        </p>
      )}
      {(req.kind === "action" || req.kind === "review") && (
        <div className={cx("space-y-3", !detail && "mt-3")}>
          {req.kind === "action" && !decided && canDecide && (
            <p className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800">
              <Lock size={12} /> Nothing has been sent or changed yet. It only happens if you approve.
            </p>
          )}
          {editable.map((key) => (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-xs font-semibold text-muted">
                <span>{req.kind === "review" ? "The document" : key === "content" ? "Exact content" : key}</span>
                {canDecide && !decided && <span>You can edit this before approving</span>}
              </div>
              <Textarea disabled={!canDecide || decided} value={edits[key]} onChange={(e) => setEdits({ ...edits, [key]: e.target.value })} rows={rowsFor(edits[key], detail)} />
            </div>
          ))}
          {Object.keys(fields).filter((key) => !editable.includes(key)).length > 0 && (
            <details className="rounded-md bg-gray-50 px-3 py-2 text-xs" open={detail}>
              <summary className="cursor-pointer font-semibold text-muted">Details{req.preview.action_name ? ` · ${req.preview.action_name}` : ""}</summary>
              <pre className="mt-2 whitespace-pre-wrap break-all font-mono">
                {JSON.stringify(Object.fromEntries(Object.entries(fields).filter(([key]) => !editable.includes(key))), null, 2)}
              </pre>
            </details>
          )}
          {req.preview.details && <p className="text-sm">{req.preview.details}</p>}
          {req.preview.screenshot && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`${API_URL}/api/screenshots/${req.preview.screenshot}`} alt="Current page in Agent Chrome" className="max-h-72 rounded-md border border-line" />
          )}
          {req.est_spend_usd !== null && <p className="text-sm">Will spend up to <b>{usd(req.est_spend_usd)}</b> from this goal&apos;s budget.</p>}
        </div>
      )}

      {req.kind === "question" && !decided && canDecide && (
        <div className={cx("space-y-2", !detail && "mt-3")}>
          {(req.preview.options || []).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {req.preview.options!.map((o) => (
                <button key={o} type="button" onClick={() => setNote(toggleOption(note, o))} className={cx("rounded-full border px-3 py-1 text-sm", picked(note, o) ? "border-brand-500 bg-brand-50 font-semibold text-brand-700" : "border-line hover:border-gray-400")}>{o}</button>
              ))}
            </div>
          )}
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Your answer" />
        </div>
      )}

      {req.kind === "login" && req.preview.url && (
        <div className={cx("rounded-md bg-violet-50/60 p-3 text-sm", !detail && "mt-3")}>
          <p>
            Sign in to <b>{req.preview.site}</b> in the <b>Agent Chrome</b> window, then click &quot;I&apos;ve signed in&quot;. You stay signed in, so you only do
            this once per site. The AI employee never sees your password.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => openInAgentChrome(req.preview.url!)}><ExternalLink size={13} /> Open login page in Agent Chrome</Button>
            <Button size="sm" variant="ghost" onClick={() => openInAgentChrome(req.preview.url!, true)} title="For sites like Google that block sign-in in a remote-controlled browser">
              Site won&apos;t let me sign in? Use manual sign-in mode
            </Button>
          </div>
        </div>
      )}

      {req.kind === "connect" && req.preview.url && (
        <div className={cx("rounded-md bg-brand-50/60 p-3 text-sm", !detail && "mt-3")}>
          <p>Connect <b>{req.preview.app}</b> through its official sign-in page. You only do this once.</p>
          <a href={req.preview.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline">
            <ExternalLink size={13} /> Open {req.preview.app} sign-in
          </a>
        </div>
      )}

      {error && <div className={cx(!detail && "mt-3")}><ErrorNote>{error}</ErrorNote></div>}

      {decided ? (
        <div className={cx("rounded-md bg-gray-50 px-3 py-2 text-sm", !detail && "mt-3")}>
          <b>{req.status === "approved" ? (req.kind === "question" ? "Answered" : "Approved") : req.kind === "question" ? "Skipped" : req.kind === "review" ? "Changes requested" : req.kind === "proposal" ? "Kept as is" : "Declined"}</b>
          {req.decided_by_name ? ` by ${req.decided_by_name}` : ""}
          {req.decision_note && <p className="mt-1 text-gray-700">&ldquo;{req.decision_note}&rdquo;</p>}
        </div>
      ) : (
        <>
          <p className={cx("flex flex-wrap items-center gap-1.5 text-xs text-muted", !detail && "mt-3")}>
            <Users size={13} />
            <span>{req.routed_to_me ? "Waiting on you" : <>Waiting on <b className="text-ink">{to}</b></>}{req.department_name ? ` · ${req.department_name}` : ""}</span>
          </p>

          {!canDecide ? (
            <div className={cx("rounded-md bg-gray-50 px-3 py-2 text-sm text-muted", !detail && "mt-3")}>
              Waiting for {to}. You can see it, but only they (or an admin) can decide.
            </div>
          ) : req.kind === "question" ? (
            <div className={cx("flex flex-wrap gap-2", !detail && "mt-3")}>
              <Button variant="primary" disabled={busy || !note.trim()} onClick={() => decide("approve")}><MessageSquare size={15} /> Send answer</Button>
              <Button variant="ghost" disabled={busy} onClick={() => decide("reject")}>Skip: let it decide</Button>
            </div>
          ) : rejecting ? (
            <div className={cx("space-y-2", !detail && "mt-4")}>
              <Input autoFocus placeholder={`Tell ${agent} why (it will adjust)`} value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex gap-2">
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}><X size={15} /> {req.kind === "review" ? "Send back" : req.kind === "proposal" ? "Keep as is" : "Decline"}</Button>
                <Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className={cx("space-y-3", !detail && "mt-4")}>
              {(req.kind === "action" || req.kind === "review" || req.kind === "proposal") && (commenting ? (
                <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder={`Comment for ${agent} (optional), e.g. "Go ahead, and mention our pricing page"`} />
              ) : (
                <button onClick={() => setCommenting(true)} className="flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline"><MessageSquare size={12} /> Add a comment</button>
              ))}
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="primary" disabled={busy} onClick={() => decide("approve", req.kind === "action" && remember)}>
                  <Check size={15} />
                  {req.kind === "login" ? "I've signed in" : req.kind === "connect" ? "I've connected it"
                    : req.kind === "review" ? (req.preview.handoff_to ? `Approve & send to ${req.preview.handoff_to}` : "Approve")
                    : req.kind === "proposal" ? PROPOSAL_YES[req.preview.change?.type || ""] || "Approve"
                    : remember ? "Approve & don't ask again" : "Approve"}
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => setRejecting(true)}>
                  {req.kind === "action" ? "Don't do this" : req.kind === "review" ? "Ask for changes" : req.kind === "proposal" ? "Keep as is" : "Not now"}
                </Button>
                {req.kind === "action" && (
                  <label className="ml-1 flex cursor-pointer items-center gap-2 text-sm">
                    <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 accent-brand-500" />
                    Don&apos;t ask next time
                  </label>
                )}
              </div>
            </div>
          )}

          {remember && canDecide && req.kind === "action" && !rejecting && (
            <div className="mt-3 grid gap-2 rounded-md border border-line bg-gray-50 p-3 text-sm sm:grid-cols-3">
              <div>
                <div className="mb-1 text-xs font-semibold text-muted">Applies to</div>
                <Select value={rememberScope} onChange={(e) => setRememberScope(e.target.value as "goal" | "department" | "org")}>
                  <option value="goal">This goal</option>
                  {req.department_name && <option value="department">Every goal in {req.department_name}</option>}
                  {org?.me.is_admin && <option value="org">The whole organization</option>}
                </Select>
              </div>
              {req.scope && (
                <div>
                  <div className="mb-1 text-xs font-semibold text-muted">Where</div>
                  <Select value={anyChannel ? "any" : "this"} onChange={(e) => setAnyChannel(e.target.value === "any")}>
                    <option value="this">Only on {req.scope}</option>
                    <option value="any">Any app or site</option>
                  </Select>
                </div>
              )}
              {req.action_type === "spend_money" && (
                <div>
                  <div className="mb-1 text-xs font-semibold text-muted">Up to (per action)</div>
                  <Input type="number" min="0" step="0.01" value={limit} onChange={(e) => setLimit(e.target.value)} />
                </div>
              )}
              <p className="text-xs text-muted sm:col-span-3">
                {agent} won&apos;t ask before &quot;{req.action_label}&quot;
                {rememberScope === "department" ? ` for any ${req.department_name} goal` : rememberScope === "org" ? " anywhere in the organization" : " on this goal"}. Revoke it anytime in Settings → Permissions.
              </p>
            </div>
          )}
        </>
      )}
    </Wrapper>
  );
}

/** Enough rows to read the whole thing without scrolling, within reason. */
function rowsFor(text: string, detail?: boolean) {
  const lines = text.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 90)), 0);
  return Math.min(detail ? 16 : 8, Math.max(2, lines));
}

/** Answer chips add up ("A, B"), so questions like "which 3 customers?" are one click each. */
const parts = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const picked = (answer: string, option: string) => parts(answer).includes(option);
function toggleOption(answer: string, option: string) {
  const current = parts(answer);
  return (picked(answer, option) ? current.filter((x) => x !== option) : [...current, option]).join(", ");
}
