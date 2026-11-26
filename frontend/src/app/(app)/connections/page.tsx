"use client";

import { Check, CircleAlert, Database, ExternalLink, GitBranch, Hand, KeyRound, Loader2, Plug, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DatabaseForm, GitHubForm } from "@/components/Connections";
import { AgentChrome, McpServers } from "@/components/ConnectionsExtras";
import { Badge, Button, Card, cx, ErrorNote, Input, Label, PageHeader, Select } from "@/components/ui";
import { api, IntegrationInfo, OrgInfo, useApi } from "@/lib/api";

type ToolStatus = {
  key: string; label: string; app: string | null; site: string | null; login_url: string | null; kind: "app" | "github" | "postgres";
  goals: { id: string; name: string; status: string }[]; required: boolean; on_its_own: string[]; needs_ok: string[];
  status: "connected" | "signed_in" | "missing"; live_goals: number; can_connect_app: boolean;
};
type ConnectionsOverview = {
  tools: ToolStatus[];
  summary: { needed: number; connected: number; missing_live: number };
  composio: { enabled: boolean; source: "platform" | "org" | null; error: string | null };
  github_sign_in: boolean;
  code_and_data: string[];
  mcp_servers: number;
};
type AppConnections = { composio_enabled: boolean; apps: { id: string; app: string; status: string }[]; error: string | null };

const POPULAR = ["gmail", "linkedin", "hubspot", "slack", "googlecalendar", "googlesheets", "notion", "twitter", "shopify", "stripe", "mixpanel", "quickbooks"];

export default function ConnectionsPage() {
  return <Suspense><ConnectionsInner /></Suspense>;
}

function ConnectionsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { data, reload } = useApi<ConnectionsOverview>("/api/connections/overview", { live: false });
  const { data: org } = useApi<OrgInfo>("/api/org", { live: false });
  const admin = !!org?.me.is_admin;
  const github = params.get("github");

  // Coming back from an app's sign-in page in another tab: refresh what's connected.
  useEffect(() => {
    const f = () => reload();
    window.addEventListener("focus", f);
    return () => window.removeEventListener("focus", f);
  }, [reload]);

  const s = data?.summary;
  return (
    <div className="space-y-8">
      <PageHeader
        title="Connections"
        subtitle="Connect the accounts Autopilot uses, once. Anything that sends, posts, pays or changes still waits for your OK."
        actions={s && s.needed > 0 && <ReadyMeter connected={s.connected} needed={s.needed} />}
      />

      {github === "choose" && admin && <RepoPicker onDone={() => { router.replace("/connections"); reload(); }} />}
      {github && github !== "choose" && (
        <ErrorNote>{github === "cancelled" ? "GitHub sign-in was cancelled." : github === "expired" ? "That GitHub sign-in link expired. Try again." : "GitHub sign-in didn't work. Try again, or use a token."}</ErrorNote>
      )}

      {s && s.missing_live > 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-signal-200 bg-gradient-to-r from-signal-50 to-white px-4 py-3 text-[13.5px]">
          <CircleAlert size={18} className="shrink-0 text-signal-600" />
          <span><b className="font-semibold">{s.missing_live} {s.missing_live === 1 ? "tool your live goals use isn't" : "tools your live goals use aren't"} connected yet.</b>{" "}
            <span className="text-stone-600">Autopilot will ask in Needs you when it gets there, or connect now.</span></span>
        </div>
      )}

      <section>
        <Label className="mb-3">What your goals use</Label>
        {!data ? <p className="text-muted">Loading…</p> : data.tools.length === 0 ? (
          <Card className="px-5 py-6 text-[14px] text-muted">None of your goals needs an app or site yet. Start a goal and its tools show up here.</Card>
        ) : (
          <Card className="divide-y divide-line overflow-hidden">
            {data.tools.map((t) => <ToolRow key={t.key} t={t} githubSignIn={data.github_sign_in} admin={admin} onChanged={reload} />)}
          </Card>
        )}
      </section>

      <section className="space-y-3">
        <Label>Apps</Label>
        <AppsCard overview={data} admin={admin} onChanged={reload} />
      </section>

      <section className="space-y-3">
        <Label>Code &amp; data</Label>
        <CodeAndDataCards githubSignIn={!!data?.github_sign_in} admin={admin} onChanged={reload} />
      </section>

      <section className="space-y-3">
        <Label>Websites and your own tools</Label>
        <AgentChrome />
        <McpServers />
      </section>
    </div>
  );
}

function ReadyMeter({ connected, needed }: { connected: number; needed: number }) {
  const pct = needed ? connected / needed : 1;
  const r = 16, c = 2 * Math.PI * r;
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-2 shadow-[var(--shadow-card)]">
      <svg width="40" height="40" viewBox="0 0 40 40" className="-rotate-90">
        <circle cx="20" cy="20" r={r} fill="none" stroke="#f4f4f5" strokeWidth="4" />
        <circle cx="20" cy="20" r={r} fill="none" stroke={pct >= 1 ? "#10b981" : "#18181b"} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} />
      </svg>
      <div className="leading-tight">
        <div className="tabular text-[15px] font-semibold">{connected} of {needed}</div>
        <div className="text-[12px] text-muted">tools ready</div>
      </div>
    </div>
  );
}

function ToolRow({ t, githubSignIn, admin, onChanged }: { t: ToolStatus; githubSignIn: boolean; admin: boolean; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const done = t.status !== "missing";

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const connectApp = () => run(async () => {
    const r = await api<{ redirect_url: string }>(`/api/connections/${encodeURIComponent(t.app!)}/connect?back=/connections`, { method: "POST" });
    window.open(r.redirect_url, "_blank", "noopener");
    setOpened(true);
  });
  const openSite = () => run(async () => { await api("/api/browser/open", { method: "POST", json: { url: t.login_url || t.site } }); setOpened(true); });
  const markSignedIn = () => run(async () => { await api("/api/sites/signed-in", { method: "POST", json: { site: t.site } }); onChanged(); });
  const signInGitHub = () => run(async () => { window.location.href = (await api<{ url: string }>("/api/integrations/github/sign-in")).url; });

  const icon = t.kind === "github" ? <GitBranch size={17} /> : t.kind === "postgres" ? <Database size={17} /> : <span className="text-[15px] font-bold">{t.label.slice(0, 1)}</span>;
  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", done ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-600")}>{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14.5px] font-semibold">{t.label}</span>
            {done ? <Badge tone="green"><Check size={11} /> {t.status === "signed_in" ? "Signed in" : "Connected"}</Badge>
              : t.live_goals ? <Badge tone="amber">Needed now</Badge> : <Badge>Not connected</Badge>}
          </div>
          <div className="mt-0.5 truncate text-[12.5px] text-muted" title={t.goals.map((g) => g.name).join(", ")}>
            Used by {t.goals[0]?.name}{t.goals.length > 1 ? ` and ${t.goals.length - 1} more` : ""}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
            {t.on_its_own.length > 0 && <span className="inline-flex items-center gap-1 text-emerald-700"><Zap size={12} /> On its own: {t.on_its_own.join(", ")}</span>}
            {t.needs_ok.length > 0 && <span className="inline-flex items-center gap-1 text-signal-700"><Hand size={12} /> Needs your OK: {t.needs_ok.join(", ")}</span>}
          </div>
        </div>
        {!done && (
          <div className="flex flex-wrap items-center gap-2">
            {t.kind === "github" ? (
              admin && (githubSignIn
                ? <Button size="sm" variant="primary" disabled={busy} onClick={signInGitHub}><GitBranch size={13} /> Sign in with GitHub</Button>
                : <Button size="sm" variant="primary" onClick={() => setOpen(!open)}>Connect</Button>)
            ) : t.kind === "postgres" ? (
              admin && <Button size="sm" variant="primary" onClick={() => setOpen(!open)}>Connect</Button>
            ) : t.can_connect_app ? (
              <Button size="sm" variant="primary" disabled={busy} onClick={connectApp}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />} Connect</Button>
            ) : t.site ? (
              opened
                ? <Button size="sm" variant="primary" disabled={busy} onClick={markSignedIn}><Check size={13} /> I&apos;ve signed in</Button>
                : <Button size="sm" variant="primary" disabled={busy} onClick={openSite}><KeyRound size={13} /> Sign in</Button>
            ) : null}
            {t.kind === "app" && t.can_connect_app && t.site && (
              <button onClick={openSite} className="text-[12px] font-semibold text-muted hover:text-ink">or sign in in Agent Chrome</button>
            )}
          </div>
        )}
      </div>
      {opened && t.can_connect_app && !done && (
        <p className="mt-2 pl-14 text-[12.5px] text-muted">Finish signing in in the new tab; this updates when you come back.</p>
      )}
      {opened && !t.can_connect_app && t.site && !done && (
        <p className="mt-2 pl-14 text-[12.5px] text-muted">Sign in to {t.site} in the Agent Chrome window, then click &quot;I&apos;ve signed in&quot;. Autopilot never sees your password.</p>
      )}
      {open && !done && (
        <div className="mt-3 pl-14">
          {t.kind === "github" ? <GitHubForm onDone={() => { setOpen(false); onChanged(); }} /> : <DatabaseForm onDone={() => { setOpen(false); onChanged(); }} />}
        </div>
      )}
      {err && <div className="mt-2 pl-14"><ErrorNote>{err}</ErrorNote></div>}
    </div>
  );
}

/** App connections: ready out of the box with Autopilot's key, or with the organization's own. */
function AppsCard({ overview, admin, onChanged }: { overview?: ConnectionsOverview | null; admin: boolean; onChanged: () => void }) {
  const { data: conns, reload } = useApi<AppConnections>("/api/connections", { live: false });
  const { data: integrations, reload: reloadInt } = useApi<IntegrationInfo[]>("/api/integrations", { live: false });
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [app, setApp] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const comp = overview?.composio;
  const own = (integrations || []).find((i) => i.kind === "composio");
  const connected = new Set((conns?.apps || []).filter((a) => a.status === "ACTIVE").map((a) => a.app));

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      reload();
      reloadInt();
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const connect = (slug: string) => run(async () => {
    const r = await api<{ redirect_url: string }>(`/api/connections/${encodeURIComponent(slug.toLowerCase())}/connect?back=/connections`, { method: "POST" });
    window.open(r.redirect_url, "_blank", "noopener");
  });

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start gap-4">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Plug size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14.5px] font-semibold">1,000+ apps, one click each</span>
            {comp?.enabled ? <Badge tone="green"><Check size={11} /> Ready</Badge> : <Badge tone="amber">Not set up</Badge>}
          </div>
          <p className="mt-0.5 text-[13px] text-muted">
            {comp?.source === "org" ? <>Using your own Composio key (····{own?.config?.key_hint as string || ""}).</>
              : comp?.enabled ? "Sign in with each app's own login page. Your accounts stay separate from every other company's."
              : "App connections need a Composio key. Without one, Autopilot signs in to sites through Agent Chrome instead."}
          </p>
        </div>
        {admin && comp?.source === "org" && own && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => api(`/api/integrations/${own.id}`, { method: "DELETE" }))}>Stop using my key</Button>
        )}
        {admin && comp?.source !== "org" && !showKey && (
          <button onClick={() => setShowKey(true)} className="text-[12.5px] font-semibold text-muted hover:text-ink">{comp?.enabled ? "Use my own Composio key" : "Add a Composio key"}</button>
        )}
      </div>

      {showKey && admin && comp?.source !== "org" && (
        <form className="mt-4 space-y-2 rounded-xl bg-stone-50 p-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/api/integrations/composio", { method: "POST", json: { api_key: key.trim() } }); setKey(""); setShowKey(false); }); }}>
          <div className="flex gap-2">
            <Input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Composio API key" />
            <Button variant="primary" disabled={busy || key.trim().length < 10}>{busy ? "Checking…" : "Save"}</Button>
          </div>
          <p className="text-[12px] text-muted">
            Get one at <a href="https://platform.composio.dev" target="_blank" rel="noreferrer" className="font-semibold text-brand-700 hover:underline">platform.composio.dev <ExternalLink size={11} className="inline" /></a>.
            Stored encrypted and used only for {"your organization"}. No restart needed.
          </p>
        </form>
      )}

      {comp?.enabled && (
        <div className="mt-5 space-y-3">
          {comp.error && <ErrorNote>{comp.error}</ErrorNote>}
          <div className="flex flex-wrap gap-2">
            {POPULAR.map((p) => (
              <button key={p} disabled={busy} onClick={() => !connected.has(p) && connect(p)}
                className={cx("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium ring-1 ring-inset transition",
                  connected.has(p) ? "bg-emerald-50 text-emerald-700 ring-emerald-100" : "bg-white text-stone-700 ring-line hover:ring-brand-200 hover:text-brand-700")}>
                {connected.has(p) ? <Check size={12} /> : <Plug size={12} />} {p}
              </button>
            ))}
          </div>
          <form className="flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); if (app.trim()) connect(app.trim()); }}>
            <Input value={app} onChange={(e) => setApp(e.target.value)} placeholder="Another app, e.g. instagram" />
            <Button type="submit" disabled={busy || !app.trim()}>Connect</Button>
          </form>
        </div>
      )}
      {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
    </Card>
  );
}

function CodeAndDataCards({ githubSignIn, admin, onChanged }: { githubSignIn: boolean; admin: boolean; onChanged: () => void }) {
  const { data, reload } = useApi<IntegrationInfo[]>("/api/integrations", { live: false });
  const [open, setOpen] = useState<"github" | "postgres" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const has = (k: string) => (data || []).find((i) => i.kind === k);
  const done = () => { setOpen(null); reload(); onChanged(); };

  const card = (kind: "github" | "postgres", icon: React.ReactNode, title: string, what: string, action: React.ReactNode, form: React.ReactNode) => {
    const i = has(kind);
    return (
      <Card className="p-5">
        <div className="flex items-start gap-4">
          <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", i ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-600")}>{icon}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14.5px] font-semibold">{title}</span>
              {i && <Badge tone="green"><Check size={11} /> {i.name}</Badge>}
            </div>
            <p className="mt-0.5 text-[13px] text-muted">{what}</p>
            {admin && !i && <div className="mt-3">{action}</div>}
          </div>
          {admin && i && (
            <Button size="sm" variant="ghost" onClick={async () => { setErr(null); try { await api(`/api/integrations/${i.id}`, { method: "DELETE" }); done(); } catch (e) { setErr((e as Error).message); } }}>Disconnect</Button>
          )}
        </div>
        {open === kind && !i && <div className="mt-4 pl-14">{form}</div>}
      </Card>
    );
  };

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {card("github", <GitBranch size={18} />, "GitHub", "On Engineering goals, Autopilot reads code and opens pull requests. Merging always waits for an engineer.",
        githubSignIn ? (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="primary" onClick={async () => { setErr(null); try { window.location.href = (await api<{ url: string }>("/api/integrations/github/sign-in")).url; } catch (e) { setErr((e as Error).message); } }}>
              <GitBranch size={13} /> Sign in with GitHub
            </Button>
            <button onClick={() => setOpen(open === "github" ? null : "github")} className="text-[12px] font-semibold text-muted hover:text-ink">or use a token</button>
          </div>
        ) : <Button size="sm" variant="primary" onClick={() => setOpen(open === "github" ? null : "github")}>Connect</Button>,
        <GitHubForm onDone={done} />)}
      {card("postgres", <Database size={18} />, "Database", "On Product goals, Autopilot queries it read-only to explain metric changes.",
        <Button size="sm" variant="primary" onClick={() => setOpen(open === "postgres" ? null : "postgres")}>Connect</Button>,
        <DatabaseForm onDone={done} />)}
      {err && <div className="lg:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
    </div>
  );
}

/** After "Sign in with GitHub": pick the repository Autopilot works on. */
function RepoPicker({ onDone }: { onDone: () => void }) {
  const { data: repos, error } = useApi<{ full_name: string; private: boolean }[]>("/api/integrations/github/repos", { live: false });
  const [repo, setRepo] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (repos?.length && !repo) setRepo(repos[0].full_name); }, [repos, repo]);
  return (
    <Card className="border-brand-200 p-5 ring-4 ring-brand-50">
      <div className="flex items-center gap-2 text-[15px] font-semibold"><GitBranch size={17} className="text-brand-600" /> Signed in to GitHub. Which repository?</div>
      <p className="mt-0.5 text-[13px] text-muted">On Engineering goals, Autopilot will read this code and open pull requests on <code>autopilot/…</code> branches.</p>
      {error ? <div className="mt-3"><ErrorNote>{error}</ErrorNote></div> : !repos ? <p className="mt-3 text-muted">Loading your repositories…</p> : repos.length === 0 ? (
        <p className="mt-3 text-[13px] text-muted">No repositories you can push to. Ask for access, then sign in again.</p>
      ) : (
        <div className="mt-3 flex max-w-xl gap-2">
          <Select value={repo} onChange={(e) => setRepo(e.target.value)}>
            {repos.map((r) => <option key={r.full_name} value={r.full_name}>{r.full_name}{r.private ? " (private)" : ""}</option>)}
          </Select>
          <Button variant="primary" disabled={busy || !repo} onClick={async () => {
            setBusy(true); setErr(null);
            try { await api("/api/integrations/github/repo", { method: "POST", json: { repo } }); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
          }}>Use this repository</Button>
        </div>
      )}
      {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
      <p className="mt-3 text-[12px] text-muted">Prefer to limit access to one repository? <Link href="/connections" className="font-semibold text-brand-700">Use a fine-grained token instead</Link>.</p>
    </Card>
  );
}
