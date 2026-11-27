"use client";

import { Check, Loader2, Pencil, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, SocialProfiles as Socials, SocialUsed } from "@/lib/api";
import { Button, ErrorNote, Input } from "./ui";

const PLATFORM = { linkedin: "LinkedIn", x: "X" } as const;

/** "x.com/acme" -> "@acme"; LinkedIn URLs without the scheme. */
export function profileLabel(platform: "linkedin" | "x", url: string): string {
  const bare = url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  return platform === "x" ? "@" + bare.replace(/^(x|twitter)\.com\//, "") : bare;
}

/** On a social media finding: which of the company's profiles the numbers come from, and a way to
 *  add a missing one or correct a wrong one (then social media is checked again). */
export function ProfilesUsed({ used, orgName, canEdit }: { used?: SocialUsed; orgName: string; canEdit: boolean }) {
  const [editing, setEditing] = useState(false);
  const company = (used?.profiles || []).filter((p) => p.who === "company");
  const founders = (used?.profiles || []).filter((p) => p.who === "founder");
  const none = !company.length && !founders.length;
  return (
    <div className="mt-5 rounded-xl border border-line bg-canvas px-4 py-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold text-ink">{none ? `No LinkedIn or X profile found for ${orgName}` : used?.confirmed ? "Profiles you confirmed" : "Profiles we found"}</span>
        {canEdit && !editing && (
          <button onClick={() => setEditing(true)} className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline">
            {none ? <><Plus size={13} /> Have one? Add it</> : <><Pencil size={12} /> Not right? Change</>}
          </button>
        )}
      </div>
      {!none && (
        <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-stone-700">
          {[...company, ...founders].map((p) => (
            <li key={p.url}>
              <span className="text-muted">{p.who === "founder" ? `${p.name || "Founder"}, ${PLATFORM[p.platform]}` : PLATFORM[p.platform]}: </span>
              <a href={p.url} target="_blank" rel="noreferrer" className="font-medium text-ink underline decoration-stone-300 underline-offset-2 hover:decoration-ink">
                {profileLabel(p.platform, p.url)}
              </a>
            </li>
          ))}
        </ul>
      )}
      {none && !editing && <p className="mt-1 text-muted">If {orgName} has a LinkedIn page or X account (or the founders post), add it so these numbers are right.</p>}
      {editing && <ProfilesForm used={used} onClose={() => setEditing(false)} />}
    </div>
  );
}

/** Edit the company's and founders' profiles, then check social media again. */
function ProfilesForm({ used, onClose }: { used?: SocialUsed; onClose: () => void }) {
  const [form, setForm] = useState<Required<Socials> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ confirmed: Socials }>("/api/org/socials").then(({ confirmed }) => {
      // Start from what the company confirmed, else from what the check found.
      const found = used?.profiles || [];
      const pick = (platform: "linkedin" | "x") => confirmed[platform] || found.find((p) => p.who === "company" && p.platform === platform)?.url || "";
      const founderNames = [...new Set(found.filter((p) => p.who === "founder").map((p) => p.name))];
      const founders = confirmed.founders?.length ? confirmed.founders.map((f) => ({ name: f.name, linkedin: f.linkedin || "", x: f.x || "" }))
        : founderNames.map((n) => ({
          name: n,
          linkedin: found.find((p) => p.who === "founder" && p.name === n && p.platform === "linkedin")?.url || "",
          x: found.find((p) => p.who === "founder" && p.name === n && p.platform === "x")?.url || "",
        }));
      setForm({ linkedin: pick("linkedin"), x: pick("x"), founders: founders.length ? founders : [{ name: "", linkedin: "", x: "" }] });
    }).catch((e) => setErr((e as Error).message));
  }, [used]);

  async function save() {
    if (!form) return;
    setBusy(true);
    setErr(null);
    try {
      await api("/api/org/socials", { method: "PUT", json: form });
      await api("/api/org/setup", { method: "POST", json: { mode: "social" } });
      window.location.href = "/opportunities";  // shows the re-check, then the updated findings
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  if (!form) return <p className="mt-2 flex items-center gap-2 text-muted"><Loader2 size={13} className="animate-spin" /> Loading…</p>;
  const setFounder = (i: number, k: "name" | "linkedin" | "x", v: string) =>
    setForm({ ...form, founders: form.founders.map((f, j) => (j === i ? { ...f, [k]: v } : f)) });
  return (
    <div className="mt-3 space-y-3 border-t border-line pt-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-[12px] font-semibold text-muted">Company LinkedIn page</span>
          <Input value={form.linkedin || ""} onChange={(e) => setForm({ ...form, linkedin: e.target.value })} placeholder="linkedin.com/company/your-company" />
        </label>
        <label className="block">
          <span className="mb-1 block text-[12px] font-semibold text-muted">Company X account</span>
          <Input value={form.x || ""} onChange={(e) => setForm({ ...form, x: e.target.value })} placeholder="@yourcompany" />
        </label>
      </div>
      <div className="space-y-2">
        <span className="block text-[12px] font-semibold text-muted">Founders</span>
        {form.founders.map((f, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1.3fr_1fr_auto]">
            <Input value={f.name} onChange={(e) => setFounder(i, "name", e.target.value)} placeholder="Name" />
            <Input value={f.linkedin || ""} onChange={(e) => setFounder(i, "linkedin", e.target.value)} placeholder="linkedin.com/in/…" />
            <Input value={f.x || ""} onChange={(e) => setFounder(i, "x", e.target.value)} placeholder="@handle" />
            <button onClick={() => setForm({ ...form, founders: form.founders.filter((_, j) => j !== i) })} aria-label="Remove"
              className="grid h-9 w-9 place-items-center rounded-lg text-stone-400 hover:bg-white hover:text-ink"><X size={14} /></button>
          </div>
        ))}
        {form.founders.length < 5 && (
          <button onClick={() => setForm({ ...form, founders: [...form.founders, { name: "", linkedin: "", x: "" }] })}
            className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-brand-700 hover:underline"><Plus size={13} /> Add a founder</button>
        )}
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={busy} onClick={save}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save and check again
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <span className="text-[12px] text-muted">Only social media is checked again (about a minute); your other findings stay.</span>
      </div>
    </div>
  );
}
