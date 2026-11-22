"use client";

import { Check, ExternalLink, KeyRound, Link2, ShieldQuestion, Users, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, API_URL, OrgInfo, timeAgo, usd, useApi, UserRequest } from "@/lib/api";
import { Badge, Button, Card, ErrorNote, Input, Select, Textarea } from "./ui";

export function ApprovalCard({ req, onDone, showCampaign }: { req: UserRequest; onDone: () => void; showCampaign?: boolean }) {
  const editable = req.preview.editable || [];
  const fields = req.preview.fields || {};
  const [edits, setEdits] = useState<Record<string, string>>(() =>
    Object.fromEntries(editable.map((k) => [k, String(fields[k] ?? "")])),
  );
  const [remember, setRemember] = useState(false);
  const [rememberScope, setRememberScope] = useState<"goal" | "department" | "org">("goal");
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false, pollMs: 300000 });
  const canDecide = req.can_decide !== false;
  const team = req.department_name ? `${req.department_name} team` : "admins";
  const [anyChannel, setAnyChannel] = useState(false);
  const [limit, setLimit] = useState(req.est_spend_usd ? String(req.est_spend_usd) : "");
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject", rememberThis = false) {
    setBusy(true);
    setError(null);
    const changed = Object.fromEntries(Object.entries(edits).filter(([k, v]) => v !== String(fields[k] ?? "")));
    try {
      await api(`/api/requests/${req.id}/decide`, {
        method: "POST",
        json: {
          decision,
          note: note || null,
          edited_fields: decision === "approve" && Object.keys(changed).length ? changed : null,
          remember: rememberThis,
          remember_scope: rememberScope,
          remember_any_channel: anyChannel,
          spend_limit_usd: req.action_type === "spend_money" && limit ? Number(limit) : null,
        },
      });
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

  const header = (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      {req.kind === "action" && (
        <Badge tone="amber">
          <ShieldQuestion size={12} /> {req.action_label || "Action"}
        </Badge>
      )}
      {req.kind === "login" && (
        <Badge tone="violet">
          <KeyRound size={12} /> Sign-in needed
        </Badge>
      )}
      {req.kind === "connect" && (
        <Badge tone="blue">
          <Link2 size={12} /> Connect an app
        </Badge>
      )}
      {req.scope && <Badge>{req.scope}</Badge>}
      {req.agent_name && <Badge tone="violet">{req.agent_name}</Badge>}
      {showCampaign && req.campaign_name && (
        <Link href={`/goals/${req.campaign_id}`} className="font-semibold text-brand-600 hover:underline">
          {req.campaign_name}
        </Link>
      )}
      <span>{timeAgo(req.created_at)}</span>
    </div>
  );

  return (
    <Card className="p-4">
      {header}
      <h4 className="mt-2 text-[15px] font-semibold">
        {req.kind === "action" ? `${req.agent_name || "Autopilot"} wants to: ${req.title}. Can it go ahead?` : req.title}
      </h4>
      {req.rationale && <p className="mt-1 text-sm text-muted">{req.rationale}</p>}

      {req.kind === "action" && (
        <div className="mt-3 space-y-3">
          {editable.map((k) => (
            <div key={k}>
              <div className="mb-1 flex items-center justify-between text-xs font-semibold text-muted">
                <span>{k === "content" ? "Exact content" : k}</span>
                <span>You can edit this before approving</span>
              </div>
              <Textarea disabled={!canDecide} value={edits[k]} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} rows={Math.min(8, Math.max(3, edits[k].length / 70))} />
            </div>
          ))}
          {Object.keys(fields).filter((k) => !editable.includes(k)).length > 0 && (
            <details className="rounded-md bg-gray-50 px-3 py-2 text-xs">
              <summary className="cursor-pointer font-semibold text-muted">
                Details{req.preview.action_name ? ` · ${req.preview.action_name}` : ""}
              </summary>
              <pre className="mt-2 whitespace-pre-wrap break-all font-mono">
                {JSON.stringify(Object.fromEntries(Object.entries(fields).filter(([k]) => !editable.includes(k))), null, 2)}
              </pre>
            </details>
          )}
          {req.preview.details && <p className="text-sm">{req.preview.details}</p>}
          {req.preview.screenshot && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`${API_URL}/api/screenshots/${req.preview.screenshot}`} alt="Current page in Agent Chrome" className="max-h-72 rounded-md border border-line" />
          )}
          {req.est_spend_usd !== null && (
            <p className="text-sm">
              Will spend up to <b>{usd(req.est_spend_usd)}</b> from this goal's budget.
            </p>
          )}
        </div>
      )}

      {req.kind === "login" && req.preview.url && (
        <div className="mt-3 rounded-md bg-violet-50/60 p-3 text-sm">
          <p>
            Sign in to <b>{req.preview.site}</b> in the <b>Agent Chrome</b> window, then click &quot;I&apos;ve signed in&quot;. You stay signed in, so
            you only do this once per site. The agent never sees your password.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => openInAgentChrome(req.preview.url!)}>
              <ExternalLink size={13} /> Open login page in Agent Chrome
            </Button>
            <Button size="sm" variant="ghost" onClick={() => openInAgentChrome(req.preview.url!, true)} title="For sites like Google that block sign-in in a remote-controlled browser">
              Site won&apos;t let me sign in? Use manual sign-in mode
            </Button>
          </div>
        </div>
      )}

      {req.kind === "connect" && req.preview.url && (
        <div className="mt-3 rounded-md bg-brand-50/60 p-3 text-sm">
          <p>
            Connect <b>{req.preview.app}</b> through its official sign-in page. You only do this once.
          </p>
          <a href={req.preview.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 font-semibold text-brand-600 hover:underline">
            <ExternalLink size={13} /> Open {req.preview.app} sign-in
          </a>
        </div>
      )}

      {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}

      <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <Users size={13} />
        <span>
          Routed to the <b className="text-ink">{team}</b>
          {req.approvers?.length ? `: ${req.approvers.join(", ")}` : null}
        </span>
      </p>

      {!canDecide ? (
        <div className="mt-3 rounded-md bg-gray-50 px-3 py-2 text-sm text-muted">
          Waiting for the {team} to decide. You can see it, but only they (or an admin) can approve it.
        </div>
      ) : rejecting ? (
        <div className="mt-4 space-y-2">
          <Input autoFocus placeholder="Optional: tell the agent why (it will adjust)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button variant="danger" disabled={busy} onClick={() => decide("reject")}>
              <X size={15} /> Decline
            </Button>
            <Button variant="ghost" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" disabled={busy} onClick={() => decide("approve", req.kind === "action" && remember)}>
            <Check size={15} />
            {req.kind === "login" ? "I've signed in" : req.kind === "connect" ? "I've connected it" : remember ? "Approve & don't ask again" : "Go ahead"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => setRejecting(true)}>
            {req.kind === "action" ? "Don't do this" : "Not now"}
          </Button>
          {req.kind === "action" && (
            <label className="ml-1 flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 accent-brand-500" />
              Don&apos;t ask me next time
            </label>
          )}
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
            {req.agent_name || "Autopilot"} won&apos;t ask before &quot;{req.action_label}&quot;
            {rememberScope === "department" ? ` for any ${req.department_name} goal` : rememberScope === "org" ? " anywhere in the organization" : " on this goal"}. Revoke it anytime in Settings → Permissions.
          </p>
        </div>
      )}
    </Card>
  );
}
