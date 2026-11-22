"use client";

import { Building2, Chrome, ExternalLink, Globe, KeyRound, Mail, Plug, Plus, RefreshCw, Server, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import { useState } from "react";

import { ListEditor } from "@/components/Guardrails";
import { PersonAvatar } from "@/components/team";
import { Badge, Button, Card, CardHeader, Dot, ErrorNote, Input, Select } from "@/components/ui";
import { api, Exclusion, Grant, Level, McpServerInfo, OrgInfo, timeAgo, usd, useApi } from "@/lib/api";

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
        <p className="text-sm text-muted">Your organization and its people, what your AI employees are connected to, and the permissions you&apos;ve given them.</p>
      </div>
      <Organization />
      <People />
      <Staffing />
      <AppConnections />
      <McpServers />
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

function McpServers() {
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

const ROLE_INFO: { role: "planner" | "worker" | "checker"; title: string; text: string }[] = [
  { role: "planner", title: "Plans each work session", text: "Reviews results and decides what to do next. One call per session, so the most capable model is worth it here." },
  { role: "worker", title: "Does the work", text: "Carries out the plan step by step: research, browsing, writing, using apps. Most of the calls, so a fast, cheaper model." },
  { role: "checker", title: "Checks every outgoing action", text: "A quick yes/no review against your guardrails before anything is posted, sent or spent." },
];

function Staffing() {
  const { data } = useApi<{ models: Record<string, string> }>("/api/status", { live: false });
  return (
    <Card>
      <CardHeader title="How Autopilot is staffed" subtitle="Each job uses the cheapest Claude model that does it well. Change them in the .env file." />
      <div className="grid gap-3 p-4 sm:grid-cols-3">
        {ROLE_INFO.map((r) => (
          <div key={r.role} className="rounded-lg bg-gray-50 p-3">
            <div className="text-[13px] font-semibold">{r.title}</div>
            <div className="mt-1 font-mono text-xs text-brand-700">{data?.models?.[r.role] ?? "…"}</div>
            <p className="mt-1.5 text-xs text-muted">{r.text}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Organization() {
  const { data: org, reload } = useApi<OrgInfo>("/api/org");
  const [name, setName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!org) return null;
  return (
    <Card>
      <CardHeader title={<span className="flex items-center gap-2"><Building2 size={16} /> Organization</span>} subtitle={`You're ${org.me.role === "owner" ? "an owner" : org.me.role === "admin" ? "an admin" : "a member"} of ${org.org.name}.`} />
      <div className="p-4">
        {org.me.is_admin ? (
          <form className="flex flex-wrap gap-2" onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try { await api("/api/org", { method: "PATCH", json: { name: name ?? org.org.name } }); setName(null); reload(); } catch (err) { setError((err as Error).message); }
          }}>
            <Input className="max-w-sm" value={name ?? org.org.name} onChange={(e) => setName(e.target.value)} aria-label="Organization name" />
            <Button type="submit" disabled={name === null || !name.trim()}>Rename</Button>
          </form>
        ) : (
          <p className="text-sm">{org.org.name}</p>
        )}
        {error && <div className="mt-2"><ErrorNote>{error}</ErrorNote></div>}
      </div>
    </Card>
  );
}

const ROLE_LABEL = { owner: "Owner", admin: "Admin", member: "Member" } as const;

function People() {
  const { data: org, reload } = useApi<OrgInfo>("/api/org");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [depts, setDepts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  if (!org) return null;
  const admin = org.me.is_admin;
  const deptName = (id: string) => org.departments.find((d) => d.id === id)?.name || "?";

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div id="people" className="scroll-mt-20"><Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Users size={16} /> People</span>}
        subtitle="People approve the work of AI employees in their departments. Admins can manage everything and approve for teams with nobody in them."
      />
      <ul className="divide-y divide-line">
        {org.members.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <PersonAvatar name={m.name || m.email} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold">{m.name || m.email}{m.id === org.me.id ? " (you)" : ""}</span>
              <span className="block truncate text-xs text-muted">{m.name ? m.email : ""}</span>
            </span>
            {admin ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {org.departments.map((d) => {
                    const on = m.department_ids.includes(d.id);
                    return (
                      <button key={d.id} type="button" title={on ? `Remove from ${d.name}` : `Add to ${d.name}`}
                        onClick={() => act(() => api(`/api/members/${m.id}`, { method: "PATCH", json: { department_ids: on ? m.department_ids.filter((x) => x !== d.id) : [...m.department_ids, d.id] } }))}
                        className={on ? "rounded-full border border-brand-500 bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700" : "rounded-full border border-line px-2 py-0.5 text-xs text-muted hover:border-gray-400"}>
                        {d.name}
                      </button>
                    );
                  })}
                </div>
                <div className="w-28">
                  <Select className="h-8 py-1 text-xs" value={m.role} onChange={(e) => act(() => api(`/api/members/${m.id}`, { method: "PATCH", json: { role: e.target.value } }))}>
                    {(org.me.role === "owner" || m.role === "owner" ? ["owner", "admin", "member"] : ["admin", "member"]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r as keyof typeof ROLE_LABEL]}</option>)}
                  </Select>
                </div>
                {m.id !== org.me.id && (
                  <button title="Remove from organization" onClick={() => confirm(`Remove ${m.name || m.email} from ${org.org.name}?`) && act(() => api(`/api/members/${m.id}`, { method: "DELETE" }))} className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"><Trash2 size={14} /></button>
                )}
              </>
            ) : (
              <span className="text-xs text-muted">{ROLE_LABEL[m.role]} · {m.department_ids.map(deptName).join(", ") || "No department"}</span>
            )}
          </li>
        ))}
      </ul>

      {admin && (
        <div className="space-y-3 border-t border-line p-4">
          {org.invitations.length > 0 && (
            <div>
              <div className="mb-1.5 text-[13px] font-semibold">Invited, not signed in yet</div>
              <ul className="space-y-1.5">
                {org.invitations.map((i) => (
                  <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-md bg-gray-50 px-3 py-1.5 text-sm">
                    <Mail size={14} className="text-muted" />
                    <span className="min-w-0 flex-1 truncate">{i.email}</span>
                    <span className="text-xs text-muted">{ROLE_LABEL[i.role as keyof typeof ROLE_LABEL] || i.role} · {i.department_ids.map(deptName).join(", ") || "No department"}</span>
                    <Button size="sm" variant="ghost" onClick={() => act(() => api(`/api/invitations/${i.id}`, { method: "DELETE" }))}>Cancel</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <form className="space-y-2" onSubmit={(e) => {
            e.preventDefault();
            const to = email.trim();
            act(async () => {
              await api("/api/invitations", { method: "POST", json: { email: to, role, department_ids: depts } });
              setEmail(""); setDepts([]); setSent(to);
            });
          }}>
            <div className="text-[13px] font-semibold">Invite someone</div>
            <div className="flex flex-wrap gap-2">
              <Input type="email" required className="min-w-60 flex-1" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
              <div className="w-32">
                <Select value={role} onChange={(e) => setRole(e.target.value as "member" | "admin")}>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </Select>
              </div>
              <Button type="submit" variant="primary"><UserPlus size={15} /> Invite</Button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted">Departments (they approve work here):</span>
              {org.departments.map((d) => {
                const on = depts.includes(d.id);
                return (
                  <button key={d.id} type="button" onClick={() => setDepts(on ? depts.filter((x) => x !== d.id) : [...depts, d.id])}
                    className={on ? "rounded-full border border-brand-500 bg-brand-50 px-2 py-0.5 font-semibold text-brand-700" : "rounded-full border border-line px-2 py-0.5 text-muted hover:border-gray-400"}>
                    {d.name}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted">They get an email. When they sign in with that address (Google or email code), they join {org.org.name} automatically.</p>
            {sent && <p className="text-xs text-emerald-700">Invitation sent to {sent}.</p>}
          </form>
        </div>
      )}
      {error && <div className="px-4 pb-4"><ErrorNote>{error}</ErrorNote></div>}
    </Card></div>
  );
}

function levelText(g: { level: Level; campaign_name?: string | null; department_name?: string | null }) {
  if (g.level === "goal") return `Goal: ${g.campaign_name || "?"}`;
  if (g.level === "department") return `Every ${g.department_name || "department"} goal`;
  return "The whole organization";
}

function Permissions() {
  const { data, reload } = useApi<Grant[]>("/api/grants");
  const [error, setError] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><ShieldCheck size={16} /> Permissions</span>}
        subtitle={`Everything your team said "don't ask me next time" to. Revoke any of them and the AI employee asks again.`}
      />
      {error && <div className="px-4 pt-3"><ErrorNote>{error}</ErrorNote></div>}
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
                  {levelText(g)} · since {new Date(g.created_at).toLocaleDateString()}
                </span>
              </span>
              <Button size="sm" variant="danger" onClick={async () => {
                setError(null);
                try { await api(`/api/grants/${g.id}`, { method: "DELETE" }); } catch (e) { setError((e as Error).message); }
                reload();
              }}>
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
  const { data: org } = useApi<OrgInfo>("/api/org");
  const [dept, setDept] = useState("");
  const { data, reload } = useApi<Exclusion[]>(dept ? `/api/exclusions?department_id=${dept}` : "/api/exclusions");
  const [error, setError] = useState<string | null>(null);
  const level: Level = dept ? "department" : "org";
  const canEdit = !!org && (org.me.is_admin || (!!dept && org.me.department_ids.includes(dept)));
  const rows = (data || []).filter((e) => e.level === level && (level === "org" || e.department_id === dept));
  const list = (kind: string) => rows.filter((e) => e.kind === kind).map((e) => ({ id: e.id, value: e.label || e.value, locked: !canEdit }));
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); }
    reload();
  };
  const add = (kind: string) => (value: string) => run(() => api("/api/exclusions", { method: "POST", json: { campaign_id: null, department_id: dept || null, kind, value } }));
  const remove = (id: string) => run(() => api(`/api/exclusions/${id}`, { method: "DELETE" }));
  const deptLabel = org?.departments.find((d) => d.id === dept)?.name;
  return (
    <Card>
      <CardHeader
        title="Shared guardrails"
        subtitle={dept ? `Applied to every goal in ${deptLabel}, on top of each goal's own guardrails.` : "Applied to every goal in the organization, on top of each goal's own guardrails."}
        action={
          <div className="w-52">
            <Select className="h-8 py-1 text-xs" value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">Whole organization</option>
              {(org?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name} department</option>)}
            </Select>
          </div>
        }
      />
      {!canEdit && org && <p className="px-4 pt-3 text-xs text-muted">{dept ? "Only people in this department or admins can change these." : "Only admins can change organization-wide guardrails."}</p>}
      {error && <div className="px-4 pt-3"><ErrorNote>{error}</ErrorNote></div>}
      <div className="grid gap-5 p-4 md:grid-cols-3">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Blocked apps</div>
          <ListEditor items={list("app")} placeholder="e.g. tiktok" onAdd={add("app")} onRemove={remove} empty="None." readOnly={!canEdit} lockedLabel="view only" />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Blocked websites</div>
          <ListEditor items={list("site")} placeholder="e.g. reddit.com" onAdd={add("site")} onRemove={remove} empty="None." readOnly={!canEdit} lockedLabel="view only" />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-semibold">Rules</div>
          <ListEditor items={list("text")} placeholder="e.g. Never swear" onAdd={add("text")} onRemove={remove} empty="None." readOnly={!canEdit} lockedLabel="view only" />
        </div>
      </div>
    </Card>
  );
}
