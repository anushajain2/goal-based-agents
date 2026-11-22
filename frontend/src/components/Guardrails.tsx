"use client";

import { Lock, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";

import { ActionType } from "@/lib/api";
import { Button, cx, Input } from "./ui";

export type Mode = "never" | "ask" | "auto";

const ALWAYS_ALLOWED = new Set(["research", "read_data"]);

/** One row per action type: Never / Ask me / Don't ask. */
export function PolicyMatrix({
  types,
  modes,
  locked,
  spendLimit,
  onChange,
  onSpendLimit,
}: {
  types: ActionType[];
  modes: Record<string, Mode>;
  locked?: Record<string, string>; // action_type -> reason (e.g. set globally)
  spendLimit?: string;
  onChange: (actionType: string, mode: Mode) => void;
  onSpendLimit?: (v: string) => void;
}) {
  return (
    <div className="divide-y divide-line">
      {types.map((t) => {
        const mode = modes[t.key] ?? (t.default === "auto" ? "auto" : "ask");
        const fixed = ALWAYS_ALLOWED.has(t.key);
        const lock = locked?.[t.key];
        return (
          <div key={t.key} className="flex flex-wrap items-center gap-3 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{t.label}</div>
              <div className="text-xs text-muted">{t.description}</div>
            </div>
            {fixed ? (
              <span className="flex items-center gap-1 text-xs text-muted">
                <ShieldCheck size={14} /> Always allowed
              </span>
            ) : lock ? (
              <span className="flex items-center gap-1 text-xs text-muted" title={lock}>
                <Lock size={13} /> {lock}
              </span>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex overflow-hidden rounded-md border border-line text-xs font-semibold">
                  {(["never", "ask", "auto"] as Mode[]).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => onChange(t.key, m)}
                      className={cx(
                        "px-2.5 py-1.5 transition",
                        mode === m
                          ? m === "never"
                            ? "bg-red-600 text-white"
                            : m === "ask"
                              ? "bg-amber-500 text-white"
                              : "bg-emerald-600 text-white"
                          : "bg-white text-muted hover:bg-gray-50",
                      )}
                    >
                      {m === "never" ? "Never" : m === "ask" ? "Ask me" : "Don't ask"}
                    </button>
                  ))}
                </div>
                {t.key === "spend_money" && mode === "auto" && onSpendLimit && (
                  <label className="flex items-center gap-1 text-xs text-muted">
                    up to $
                    <Input className="h-7 w-20 px-2 py-1 text-xs" type="number" min="0" step="0.01" value={spendLimit ?? ""} onChange={(e) => onSpendLimit(e.target.value)} />
                    each
                  </label>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Editable list of strings (blocked apps, blocked sites, free-text rules). */
export function ListEditor({
  items,
  placeholder,
  onAdd,
  onRemove,
  empty,
  readOnly,
  lockedLabel = "locked",
}: {
  items: { id: string; value: string; locked?: boolean }[];
  readOnly?: boolean;
  lockedLabel?: string;
  placeholder: string;
  onAdd: (v: string) => void;
  onRemove: (id: string) => void;
  empty: string;
}) {
  const [value, setValue] = useState("");
  return (
    <div>
      <ul className="mb-2 space-y-1.5">
        {items.length === 0 && <li className="text-xs text-muted">{empty}</li>}
        {items.map((i) => (
          <li key={i.id} className="flex items-center gap-2 rounded-md bg-gray-50 px-3 py-1.5 text-sm">
            <span className="flex-1">{i.value}</span>
            {i.locked ? (
              <span className="text-xs text-muted">{lockedLabel}</span>
            ) : (
              <button type="button" onClick={() => onRemove(i.id)} className="text-muted hover:text-red-600" aria-label="Remove">
                <Trash2 size={14} />
              </button>
            )}
          </li>
        ))}
      </ul>
      {!readOnly && <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) {
            onAdd(value.trim());
            setValue("");
          }
        }}
      >
        <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} />
        <Button type="submit">
          <Plus size={15} /> Add
        </Button>
      </form>}
    </div>
  );
}
