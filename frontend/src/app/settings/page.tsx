"use client";

import { Chrome, ExternalLink, Globe, KeyRound, Plug, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ListEditor } from "@/components/Guardrails";
import { Badge, Button, Card, CardHeader, Dot, ErrorNote, Input } from "@/components/ui";
import { api, Exclusion, Grant, timeAgo, usd, useApi } from "@/lib/api";

type Connections = {
  composio_enabled: boolean;
  apps: { id: string; app: string; status: string }[];
  error: string | null;
  sites: { site: string; signed_in_at: string | null }[];
};
type Status = { chrome_path: string | null; agent_chrome_running: boolean; manual_signin_mode: boolean; composio_enabled: boolean };

const POPULAR = ["twitter", "linkedin", "gmail", "slack", "hubspot", "shopify", "notion", "googlesheets", "reddit", "youtube", "mailchimp", "googleads"];

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted">Connections, sign-ins and the permissions you have given the agent.</p>
      </div>
      <AppConnections />
      <AgentChrome />
      <Permissions />
      <GlobalGuardrails />
    </div>
  );
}

function AppConnections() {
  const { data, reload } = useApi<Connections>("/api/connections", { live: false });
  const [app, setApp] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function connect(slug: string) {
    setError(null);
    try {
      const r = await api<{ redirect_url: string }>(`/api/connections/${encodeURIComponent(slug.toLowerCase())}/connect`, { method: "POST" });
      window.open(r.redirect_url, "_blank", "noopener");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Plug size={16} /> App connectors</span>}
        subtitle="1,000+ apps through Composio: connect once with each app's official sign-in. Cheaper and more reliable than the browser."
        action={<Button size="sm" onClick={reload}>Refresh</Button>}
      />
      <div className="space-y-4 p-4">
        {data && !data.composio_enabled ? (
          <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Optional: add <code className="font-mono">COMPOSIO_API_KEY</code> to <code className="font-mono">.env</code> and restart to enable app connectors. Without it, the
            agent does everything through Agent Chrome.
          </div>
        ) : (
          <>
            {data?.error && <ErrorNote>{data.error}</ErrorNote>}
            <div>
              <div className="mb-1.5 text-[13px] font-semibold">Connected</div>
              {data && data.apps.length === 0 && <p className="text-sm text-muted">No apps connected yet. The agent will also ask when it needs one.</p>}
              <div className="flex flex-wrap gap-2">
                {(data?.apps || []).map((a) => (
                  <Badge key={a.id} tone={a.status === "ACTIVE" ? "green" : "amber"}>
                    <Dot tone={a.status === "ACTIVE" ? "green" : "amber"} /> {a.app} · {a.status.toLowerCase()}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1.5 text-[13px] font-semibold">Connect an app</div>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {POPULAR.map((p) => (
                  <button key={p} onClick={() => connect(p)} className="rounded-full border border-line px-2.5 py-1 text-xs hover:border-brand-500 hover:text-brand-600">
                    {p}
                  </button>
                ))}
              </div>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (app.trim()) connect(app.trim()); }}>
                <Input value={app} onChange={(e) => setApp(e.target.value)} placeholder="Any app slug, e.g. instagram" />
                <Button type="submit" variant="primary">Connect</Button>
              </form>
            </div>
            {error && <ErrorNote>{error}</ErrorNote>}
          </>
        )}
      </div>
    </Card>
  );
}

function AgentChrome() {
  const { data: status, reload } = useApi<Status>("/api/status", { live: false, pollMs: 5000 });
  const { data: conns } = useApi<Connections>("/api/connections", { live: false });
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, body?: unknown) {
    setError(null);
    try {
      await api(path, { method: "POST", json: body ?? {} });
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Chrome size={16} /> Agent Chrome</span>}
        subtitle="Your installed Chrome with its own profile. Sign in to a site once and the agent can use it; it never sees your passwords."
      />
      <div className="space-y-4 p-4 text-sm">
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-2">
            <Dot tone={status?.chrome_path ? "green" : "red"} /> {status?.chrome_path ? "Chrome found" : "Chrome not found: install it or set CHROME_PATH"}
          </span>
          <span className="flex items-center gap-2">
            <Dot tone={status?.agent_chrome_running ? "green" : "gray"} /> {status?.agent_chrome_running ? "Running" : "Not running (starts when needed)"}
          </span>
          {status?.manual_signin_mode && <Badge tone="violet">Manual sign-in mode</Badge>}
        </div>

        {status?.manual_signin_mode && (
          <div className="rounded-md bg-violet-50 p-3">
            <p>Agent Chrome is open without remote control so you can sign in normally. When you&apos;re done, click Done. The agent picks up the saved sign-in.</p>
            <Button className="mt-2" variant="primary" size="sm" onClick={() => call("/api/browser/manual-signin/done")}>
              Done signing in
            </Button>
          </div>
        )}

        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Sign in to a site ahead of time</div>
          <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (url.trim()) call("/api/browser/open", { url: url.trim() }); }}>
            <Input className="min-w-60 flex-1" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="e.g. x.com/login" />
            <Button type="submit"><ExternalLink size={14} /> Open in Agent Chrome</Button>
            <Button type="button" variant="ghost" onClick={() => url.trim() && call("/api/browser/manual-signin", { url: url.trim() })} title="For sites like Google that block sign-in in a remote-controlled browser">
              <KeyRound size={14} /> Manual sign-in mode
            </Button>
          </form>
        </div>

        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Sites you signed in to for the agent</div>
          {conns && conns.sites.length === 0 && <p className="text-muted">None yet.</p>}
          <ul className="flex flex-wrap gap-2">
            {(conns?.sites || []).map((s) => (
              <li key={s.site}>
                <Badge tone="green"><Globe size={12} /> {s.site} · {timeAgo(s.signed_in_at)}</Badge>
              </li>
            ))}
          </ul>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
      </div>
    </Card>
  );
}

function Permissions() {
  const { data, reload } = useApi<Grant[]>("/api/grants");
  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><ShieldCheck size={16} /> Permissions</span>}
        subtitle={`Everything you said "don't ask me next time" to. Revoke any of them and the agent asks again.`}
      />
      {data && data.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted">No standing permissions. The agent asks before every important action.</p>
      ) : (
        <ul className="divide-y divide-line">
          {(data || []).map((g) => (
            <li key={g.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <span className="flex-1">
                <b>{g.action_label}</b>
                {g.scope ? <> on {g.scope}</> : " anywhere"}
                {g.spend_limit_usd ? ` · up to ${usd(g.spend_limit_usd)} each` : ""}
                <span className="block text-xs text-muted">
                  {g.campaign_name ? `Campaign: ${g.campaign_name}` : "All campaigns"} · since {new Date(g.created_at).toLocaleDateString()}
                </span>
              </span>
              <Button size="sm" variant="danger" onClick={async () => { await api(`/api/grants/${g.id}`, { method: "DELETE" }); reload(); }}>
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function GlobalGuardrails() {
  const { data, reload } = useApi<Exclusion[]>("/api/exclusions");
  const globals = (data || []).filter((e) => !e.campaign_id);
  const list = (kind: string) => globals.filter((e) => e.kind === kind).map((e) => ({ id: e.id, value: e.label || e.value }));
  const add = (kind: string) => async (value: string) => {
    await api("/api/exclusions", { method: "POST", json: { campaign_id: null, kind, value } });
    reload();
  };
  const remove = async (id: string) => {
    await api(`/api/exclusions/${id}`, { method: "DELETE" });
    reload();
  };
  return (
    <Card>
      <CardHeader title="Guardrails for all campaigns" subtitle="Applied on top of each campaign's own guardrails." />
      <div className="grid gap-5 p-4 md:grid-cols-3">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Blocked apps</div>
          <ListEditor items={list("app")} placeholder="e.g. tiktok" onAdd={add("app")} onRemove={remove} empty="None." />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Blocked websites</div>
          <ListEditor items={list("site")} placeholder="e.g. reddit.com" onAdd={add("site")} onRemove={remove} empty="None." />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Rules</div>
          <ListEditor items={list("text")} placeholder="e.g. Never swear" onAdd={add("text")} onRemove={remove} empty="None." />
        </div>
      </div>
    </Card>
  );
}
