"use client";

import { ArrowRight, Building2, Chrome, ExternalLink, Globe, KeyRound, Mail, Plug, Plus, RefreshCw, Server, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import { useState } from "react";

import Link from "next/link";
import { ListEditor } from "@/components/Guardrails";
import { PersonAvatar } from "@/components/team";
import { Badge, Button, Card, CardHeader, Dot, ErrorNote, Input, Select, PageHeader } from "@/components/ui";
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
      <PageHeader title="Settings" subtitle="Your organization, people and permissions." />
      <Organization />
      <People />
      <Staffing />
      <Link href="/connections" className="flex items-center gap-3 rounded-2xl border border-line bg-white px-5 py-4 shadow-[var(--shadow-card)] transition hover:shadow-[var(--shadow-pop)]">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-50 text-brand-600"><Plug size={17} /></span>
        <span className="min-w-0 flex-1"><b className="block text-[14px] font-semibold">Connections</b><span className="text-[13px] text-muted">Apps, sites, GitHub, databases and your own tools now have their own page.</span></span>
        <ArrowRight size={16} className="text-zinc-400" />
      </Link>
      <Permissions />
      <GlobalGuardrails />
    </div>
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
