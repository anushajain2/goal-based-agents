"use client";

import { Check, Database, GitBranch, Trash2 } from "lucide-react";
import { useState } from "react";

import { api, IntegrationInfo, useApi } from "@/lib/api";
import { Button, Card, CardHeader, ErrorNote, Input } from "./ui";

/** Connect a GitHub repository: a fine-grained token with read/write access to code and pull requests. */
export function GitHubForm({ onDone }: { onDone: () => void }) {
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form className="space-y-2" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setErr(null);
      try {
        await api("/api/integrations/github", { method: "POST", json: { repo: repo.trim(), token: token.trim() } });
        onDone();
      } catch (e2) {
        setErr((e2 as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input required value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/repository" />
        <Input required type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="GitHub token" />
      </div>
      <p className="text-[11.5px] text-muted">
        Use a fine-grained token for just this repository with <b>Contents</b> and <b>Pull requests</b> (read and write) and <b>Issues</b> (read).
        Oton opens pull requests; merging always waits for an engineer.
      </p>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <Button size="sm" variant="primary" disabled={busy}>{busy ? "Checking…" : "Connect GitHub"}</Button>
    </form>
  );
}

/** Connect a Postgres database for read-only analysis. */
export function DatabaseForm({ onDone }: { onDone: () => void }) {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form className="space-y-2" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      setErr(null);
      try {
        await api("/api/integrations/postgres", { method: "POST", json: { name: "Database", url: url.trim() } });
        onDone();
      } catch (e2) {
        setErr((e2 as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <Input required type="password" autoComplete="off" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgresql://readonly_user:password@host:5432/db" />
      <p className="text-[11.5px] text-muted">Read-only: Oton can only run SELECT queries, and every query runs in a read-only transaction. A read-only user or a replica is best.</p>
      {err && <p className="text-xs text-red-600">{err}</p>}
      <Button size="sm" variant="primary" disabled={busy}>{busy ? "Checking…" : "Connect database"}</Button>
    </form>
  );
}

/** Settings: code and data connections. */
export function CodeAndData() {
  const { data, reload } = useApi<IntegrationInfo[]>("/api/integrations", { live: false });
  const [open, setOpen] = useState<"github" | "postgres" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const has = (k: string) => (data || []).find((i) => i.kind === k);
  const rows: { kind: "github" | "postgres"; label: string; icon: React.ReactNode; what: string }[] = [
    { kind: "github", label: "GitHub", icon: <GitBranch size={16} />, what: "Engineering goals read code and open pull requests. Merging asks an engineer." },
    { kind: "postgres", label: "Database", icon: <Database size={16} />, what: "Product goals query it read-only to explain metric changes." },
  ];
  return (
    <Card>
      <CardHeader title="Code & data" subtitle="For Product and Engineering goals. Analytics tools connect under App connectors." />
      <ul className="divide-y divide-line">
        {rows.map((r) => {
          const i = has(r.kind);
          return (
            <li key={r.kind} className="space-y-2 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-stone-100 text-stone-600">{r.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{r.label}{i ? <span className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><Check size={12} /> {i.name}</span> : null}</div>
                  <div className="text-xs text-muted">{r.what}</div>
                </div>
                {i ? (
                  <Button size="sm" variant="ghost" onClick={async () => {
                    setErr(null);
                    try { await api(`/api/integrations/${i.id}`, { method: "DELETE" }); reload(); } catch (e) { setErr((e as Error).message); }
                  }}><Trash2 size={13} /> Disconnect</Button>
                ) : (
                  <Button size="sm" onClick={() => setOpen(open === r.kind ? null : r.kind)}>Connect</Button>
                )}
              </div>
              {open === r.kind && !i && (
                <div className="pl-11">{r.kind === "github" ? <GitHubForm onDone={() => { setOpen(null); reload(); }} /> : <DatabaseForm onDone={() => { setOpen(null); reload(); }} />}</div>
              )}
            </li>
          );
        })}
      </ul>
      {err && <div className="px-4 pb-3"><ErrorNote>{err}</ErrorNote></div>}
    </Card>
  );
}
