"use client";

import { Chrome, ExternalLink, Globe, KeyRound, Plus, RefreshCw, Server, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, CardHeader, Dot, ErrorNote, Input } from "@/components/ui";
import { api, McpServerInfo, OrgInfo, timeAgo, useApi } from "@/lib/api";

type Status = { chrome_path: string | null; agent_chrome_running: boolean; manual_signin_mode: boolean; composio_enabled: boolean };
type Connections = { sites: { site: string; signed_in_at: string | null }[] };

export function McpServers() {
  const { data: servers, reload } = useApi<McpServerInfo[]>("/api/mcp-servers", { live: false });
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false });
  const [form, setForm] = useState({ name: "", url: "", auth_header: "" });
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const admin = !!org?.me.is_admin;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="mcp" className="scroll-mt-20">
      <Card>
        <CardHeader
          title={<span className="flex items-center gap-2"><Server size={16} /> Your own tools (MCP servers)</span>}
          subtitle="Connect internal systems or tools that offer an MCP server. Autopilot calls them itself, so anything that changes something waits for approval like every other action."
          action={admin && !adding ? <Button size="sm" onClick={() => setAdding(true)}><Plus size={14} /> Add server</Button> : undefined}
        />
        <div className="space-y-3 p-4">
          {adding && (
            <form className="space-y-2 rounded-lg border border-line bg-gray-50 p-3" onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api("/api/mcp-servers", { method: "POST", json: { ...form, auth_header: form.auth_header || null } });
                setForm({ name: "", url: "", auth_header: "" });
                setAdding(false);
              });
            }}>
              <div className="grid gap-2 sm:grid-cols-[160px_1fr]">
                <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name, e.g. crm" />
                <Input required value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://example.com/mcp" />
              </div>
              <Input type="password" autoComplete="off" value={form.auth_header} onChange={(e) => setForm({ ...form, auth_header: e.target.value })}
                placeholder="API key (optional): a key, or a header like X-Api-Key: abc123" />
              <p className="text-xs text-muted">The key is stored encrypted and only sent to this server.</p>
              <div className="flex gap-2">
                <Button type="submit" variant="primary" disabled={busy}>{busy ? "Connecting…" : "Connect"}</Button>
                <Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
              </div>
            </form>
          )}
          {error && <ErrorNote>{error}</ErrorNote>}
          {servers && servers.length === 0 && !adding && <p className="text-sm text-muted">No MCP servers yet.</p>}
          {(servers || []).map((m) => (
            <div key={m.id} className="rounded-lg border border-line">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
                <Dot tone={m.error ? "red" : "green"} />
                <span className="font-semibold">{m.name}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted">{m.url}{m.has_key ? " · key saved" : ""}</span>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => api(`/api/mcp-servers/${m.id}/refresh`, { method: "POST" }))}><RefreshCw size={13} /> Check</Button>
                {admin && <Button size="sm" variant="ghost" disabled={busy} onClick={() => confirm(`Remove ${m.name}?`) && run(() => api(`/api/mcp-servers/${m.id}`, { method: "DELETE" }))}><Trash2 size={13} /></Button>}
              </div>
              {m.error ? (
                <p className="px-3 py-2 text-sm text-red-600">{m.error}</p>
              ) : (
                <ul className="divide-y divide-line">
                  {m.tools.map((t) => (
                    <li key={t.name} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                      <span className="font-mono text-[12.5px]">{t.name}</span>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted">{t.description}</span>
                      {t.asks_first
                        ? <Badge tone="amber">Asks first · {t.kind_label}</Badge>
                        : <Badge tone="green">On its own · only reads</Badge>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          <p className="text-xs text-muted">
            Only tools the server marks as read-only run on their own. Everything else asks first, and you can turn a kind of action off for any goal.
          </p>
        </div>
      </Card>
    </div>
  );
}

export function AgentChrome() {
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
