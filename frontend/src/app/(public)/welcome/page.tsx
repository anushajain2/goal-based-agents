"use client";

import { ArrowRight, Bot, Check, Globe, Plus, Sparkles, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { Button, cx, ErrorNote, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";

const DEFAULT = ["sales", "marketing", "research"];

export default function WelcomePage() {
  const router = useRouter();
  const [presets, setPresets] = useState<{ kind: string; name: string }[]>([]);
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [description, setDescription] = useState("");
  const [manual, setManual] = useState(false);
  const [picked, setPicked] = useState<string[]>(DEFAULT);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Already in an organization (e.g. joined through an invitation)? Straight to the app.
    fetch("/api/org", { cache: "no-store" }).then((r) => {
      if (r.ok) router.replace("/home");
      else if (r.status === 401) router.replace("/login?next=/welcome");
    });
    fetch("/api/org/presets").then((r) => r.json()).then((d) => setPresets(d.departments)).catch(() => null);
  }, [router]);

  const toggle = (k: string) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const customs = picked.filter((p) => !presets.some((x) => x.kind === p));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (manual && !picked.length) return setError("Pick at least one department.");
    if (!manual && !website.trim() && !description.trim()) return setError("Add your website or a sentence about what you do.");
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ setup_id: string | null; setup_skipped?: string }>("/api/org", {
        method: "POST",
        json: { name, website, description, departments: manual ? picked : [] },
      });
      router.replace(r.setup_id ? "/setup" : `/team?welcome=1${r.setup_skipped ? "&basic=1" : ""}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 flex items-center gap-2.5">
          <EmployeeAvatar size={32} />
          <span className="text-[17px] font-bold tracking-tight">Autopilot</span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight">Tell us about your company</h1>
        <p className="mt-2 text-gray-600">
          Autopilot reads your website, researches your company on the web, then sets up AI employees for the functions that matter
          most right now, each with a few goals that fit where you are. You review everything before any work starts.
        </p>

        <form onSubmit={submit} className="mt-8 space-y-7 rounded-2xl border border-line bg-white p-6">
          <Field label="Company name">
            <Input required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc." />
          </Field>
          <Field label="Website">
            <div className="relative">
              <Globe size={15} className="absolute left-3 top-3 text-muted" />
              <Input className="pl-9" inputMode="url" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="acme.com" />
            </div>
          </Field>
          <Field label={`What does ${name.trim() || "your company"} do?`} hint="A sentence or two: what you sell, to whom, and what you're focused on right now.">
            <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Route-planning software for mid-size logistics companies in Europe. We just raised our seed and are hiring our first salespeople." />
          </Field>

          {!manual ? (
            <button type="button" onClick={() => setManual(true)} className="text-xs font-semibold text-muted hover:text-ink">
              Prefer to pick departments yourself?
            </button>
          ) : (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[13px] font-semibold">Departments</span>
              <button type="button" onClick={() => setManual(false)} className="text-xs font-semibold text-brand-600">Let Autopilot work them out instead</button>
            </div>
            <div className="mb-1 text-[13px] font-semibold">Departments</div>
            <p className="mb-3 text-xs text-muted">Pick the parts of the business you want AI employees for. You&apos;ll be in all of them to start with.</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {presets.map((p) => {
                const on = picked.includes(p.kind);
                return (
                  <button
                    type="button"
                    key={p.kind}
                    onClick={() => toggle(p.kind)}
                    className={cx("flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition", on ? "border-brand-500 bg-brand-50" : "border-line hover:border-gray-400")}
                  >
                    <span className={cx("grid h-5 w-5 place-items-center rounded border", on ? "border-brand-500 bg-brand-500 text-white" : "border-gray-300")}>{on && <Check size={13} />}</span>
                    <span className="flex-1 font-semibold">{p.name}</span>
                    {on && <span className="flex items-center gap-1 text-xs text-brand-700"><Bot size={13} /> {p.name} Agent</span>}
                  </button>
                );
              })}
            </div>
            {customs.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {customs.map((c) => (
                  <span key={c} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-sm font-semibold text-brand-700">
                    {c}
                    <button type="button" onClick={() => toggle(c)} aria-label={`Remove ${c}`}><X size={13} /></button>
                  </span>
                ))}
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Another department, e.g. Client Delivery" />
              <Button type="button" onClick={() => { if (custom.trim()) { setPicked((p) => [...p, custom.trim()]); setCustom(""); } }}>
                <Plus size={15} /> Add
              </Button>
            </div>
          </div>
          )}

          {error && <ErrorNote>{error}</ErrorNote>}
          <Button variant="primary" className="h-11 w-full" disabled={busy || !name.trim()}>
            {busy ? "Setting up…" : manual ? `Create ${name.trim() || "organization"}` : <><Sparkles size={15} /> Research {name.trim() || "my company"} and set up my team</>}{" "}
            {!busy && <ArrowRight size={15} />}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted">Joining your team instead? Ask an admin to invite your email, then sign in again.</p>
      </div>
    </div>
  );
}
