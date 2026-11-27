"use client";

import { Loader2, Plus, Ruler } from "lucide-react";
import { useState } from "react";

import { api, CompanyProfile, SIZE_LABEL } from "@/lib/api";
import { ErrorNote } from "./ui";

/** Why the team is this size, and the functions worth adding as the company grows. */
export function TeamSize({ profile, canAdd, onAdding }: { profile: CompanyProfile | null; canAdd: boolean; onAdding: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!profile || (!profile.size && !profile.later?.length && !profile.pack_label)) return null;
  const later = profile.later || [];

  async function add(key: string) {
    setBusy(key);
    setErr(null);
    try {
      await api("/api/org/setup", { method: "POST", json: { add_functions: [key] } });
      onAdding();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3">
      {(profile.size || profile.pack_label) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
          <Ruler size={15} className="text-brand-600" />
          <b>{[profile.pack_label, profile.size ? `sized for ${SIZE_LABEL[profile.size]}` : ""].filter(Boolean).join(", ")}</b>
          {profile.size_reason && <span className="text-muted">· {profile.size_reason}</span>}
        </div>
      )}
      {later.length > 0 && (
        <div className={profile.size || profile.pack_label ? "mt-3" : ""}>
          <div className="mb-1.5 text-[12px] font-bold text-muted">Add when you&apos;re ready</div>
          <ul className="flex flex-wrap gap-2">
            {later.map((x) => {
              const key = x.kind || x.name;
              return (
                <li key={key} className="flex items-center gap-2 rounded-lg border border-line bg-stone-50 py-1 pl-3 pr-1 text-[13px]">
                  <span><b>{x.name}</b>{x.when && <span className="text-muted">: {x.when}</span>}</span>
                  {canAdd && (
                    <button disabled={!!busy} onClick={() => add(key)}
                      className="inline-flex h-7 items-center gap-1 rounded-md bg-white px-2 text-xs font-semibold text-brand-700 ring-1 ring-line hover:bg-brand-50 disabled:opacity-50">
                      {busy === key ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add now
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {err && <div className="mt-2"><ErrorNote>{err}</ErrorNote></div>}
    </div>
  );
}
