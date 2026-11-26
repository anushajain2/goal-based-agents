"use client";

import { Check, ChevronDown, Info, UserRound } from "lucide-react";
import { useState } from "react";

import { Autonomy, AutonomyPreset, AutonomyRow, Mode } from "@/lib/api";
import { MODE_ICON, MODE_STYLE, MODE_WORDS, modesFor } from "./GoalPlan";
import { cx } from "./ui";

export type AutonomyChoice = {
  preset: AutonomyPreset["key"];
  overrides: Record<string, { mode: Mode; daily_cap: number | null }>;
  personal: string[];
};

const ORDER: AutonomyPreset["key"][] = ["cautious", "balanced", "fast"];
const STRICT: Record<Mode, number> = { auto: 0, heads_up: 1, ask: 2, never: 3 };

/** The preset to start with: the strictest any of the goals recommends (a client goal wins). */
export function initialChoice(autonomies: Autonomy[]): AutonomyChoice {
  const keys = autonomies.map((a) => a.current || a.recommended);
  const preset = keys.length ? keys.reduce((a, b) => (ORDER.indexOf(b) < ORDER.indexOf(a) ? b : a)) : "balanced";
  return { preset, overrides: {}, personal: [] };
}

/** The rows of the chosen preset with the person's changes on top. */
export function chosenRows(a: Autonomy, choice: AutonomyChoice): AutonomyRow[] {
  return a.presets[choice.preset].rows.map((r) => {
    const o = choice.overrides[r.key];
    return o ? { ...r, ...o, gain: gainWords(r, o.mode, o.daily_cap, a.heads_up_minutes) } : r;
  });
}

function gainWords(r: AutonomyRow, mode: Mode, cap: number | null, minutes: number) {
  if (mode === "auto") return cap ? `Up to ${cap} a day without waiting for anyone` : "Never waits for anyone";
  if (mode === "heads_up") return cap ? `Up to ${cap} a day, each going out ${minutes} minutes after a heads-up` : `Goes out ${minutes} minutes after a heads-up`;
  if (mode === "never") return "Never happens";
  return `Each "${r.label.toLowerCase()}" waits for a yes`;
}

/**
 * How much Oton does on its own, chosen when goals start: three presets (one
 * recommended, with the reason), every kind of action with what it means for speed, daily
 * limits, and which accounts are someone's personal profile. Everything can change later.
 */
export function AutonomySetup({ autonomy, inPlan, choice, onChange, team, multiple }: {
  autonomy: Autonomy; inPlan: Set<string>; choice: AutonomyChoice; onChange: (c: AutonomyChoice) => void; team: string; multiple: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const rows = chosenRows(autonomy, choice);
  const used = rows.filter((r) => inPlan.has(r.key) || r.in_plan);
  const others = rows.filter((r) => !(inPlan.has(r.key) || r.in_plan));
  const shown = showAll || used.length === 0 ? rows : used;
  const out = used.filter((r) => r.mode === "auto" || r.mode === "heads_up");

  function setPreset(preset: AutonomyPreset["key"]) {
    onChange({ ...choice, preset, overrides: {} });
  }
  function setRow(r: AutonomyRow, mode: Mode, cap: number | null) {
    const base = autonomy.presets[choice.preset].rows.find((x) => x.key === r.key)!;
    const overrides = { ...choice.overrides };
    if (mode === base.mode && cap === base.daily_cap) delete overrides[r.key];
    else overrides[r.key] = { mode, daily_cap: mode === "auto" || mode === "heads_up" ? cap : null };
    onChange({ ...choice, overrides });
  }

  return (
    <section className="space-y-3 rounded-xl border border-line bg-white p-4">
      <div>
        <h3 className="text-[15px] font-bold">How much should {multiple ? "they" : "it"} do without asking?</h3>
        <p className="mt-0.5 text-[13px] text-muted">
          Waiting for a yes on everything slows goals down. Pick how much goes out on its own; anything that costs money, can&apos;t be undone or
          touches code still asks {team}.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Autonomy preset">
        {ORDER.map((k) => {
          const p = autonomy.presets[k];
          const on = choice.preset === k;
          return (
            <button key={k} type="button" role="radio" aria-checked={on} onClick={() => setPreset(k)}
              className={cx("rounded-lg border px-3 py-2.5 text-left transition", on ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-500" : "border-line hover:border-stone-400")}>
              <span className="flex items-center gap-1.5 text-[13.5px] font-bold">
                {on && <Check size={14} className="text-brand-600" />} {p.label}
                {autonomy.recommended === k && <span className="ml-auto rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10.5px] font-semibold text-emerald-800">Recommended</span>}
              </span>
              <span className="mt-1 block text-[11.5px] leading-snug text-muted">{p.summary}</span>
            </button>
          );
        })}
      </div>
      {autonomy.reasons.length > 0 && (
        <p className="flex items-start gap-1.5 text-[12px] text-stone-700"><Info size={13} className="mt-0.5 shrink-0 text-muted" /> {autonomy.reasons.join(" ")}</p>
      )}

      <ul className="divide-y divide-line rounded-lg border border-line">
        {shown.map((r) => (
          <li key={r.key} className="flex flex-wrap items-start gap-x-3 gap-y-1.5 px-3 py-2.5">
            <div className="min-w-0 flex-1 basis-56">
              <div className="flex items-center gap-1.5 text-[13px] font-semibold">
                {r.label}
                {choice.overrides[r.key] && <span className="rounded bg-stone-100 px-1 text-[10.5px] font-semibold text-stone-600">changed</span>}
              </div>
              <div className="text-[11.5px] leading-snug text-muted">{r.why || r.description}</div>
              <div className={cx("mt-0.5 text-[11.5px] font-semibold", r.mode === "auto" ? "text-emerald-700" : r.mode === "heads_up" ? "text-sky-700" : r.mode === "ask" ? "text-signal-700" : "text-stone-400")}>{r.gain}</div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <RowModes row={r} onChange={(m) => setRow(r, m, m === "auto" || m === "heads_up" ? r.daily_cap ?? defaultCap(autonomy, r.key) : null)} />
              {(r.mode === "auto" || r.mode === "heads_up") && (
                <label className="flex items-center gap-1 text-[11px] text-muted">
                  At most
                  <input inputMode="numeric" aria-label={`Daily limit for ${r.label}`} value={r.daily_cap ?? ""} placeholder="no limit"
                    onChange={(e) => {
                      const v = e.target.value.replace(/[^0-9]/g, "");
                      setRow(r, r.mode, v ? Math.min(1000, Math.max(1, Number(v))) : null);
                    }}
                    className="h-6 w-14 rounded border border-line px-1.5 text-[11.5px] text-ink" />
                  a day
                </label>
              )}
            </div>
          </li>
        ))}
      </ul>
      {others.length > 0 && used.length > 0 && (
        <button type="button" onClick={() => setShowAll(!showAll)} className="flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline">
          <ChevronDown size={13} className={cx("transition", showAll && "rotate-180")} />
          {showAll ? "Only what the plan uses" : `${others.length} more kinds of action the plan doesn't use yet`}
        </button>
      )}

      {autonomy.personal_candidates.length > 0 && (
        <div className="rounded-lg bg-stone-50 px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-[12.5px] font-semibold"><UserRound size={13} /> Is any of these someone&apos;s personal profile?</div>
          <p className="text-[11.5px] text-muted">Posts, replies and messages there always ask first, whatever you picked above: it&apos;s that person&apos;s name and reputation.</p>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
            {autonomy.personal_candidates.map((p) => (
              <label key={p.key} className="flex items-center gap-1.5 text-[12.5px]">
                <input type="checkbox" className="h-3.5 w-3.5 accent-brand-500" checked={choice.personal.includes(p.key)}
                  onChange={(e) => onChange({ ...choice, personal: e.target.checked ? [...choice.personal, p.key] : choice.personal.filter((x) => x !== p.key) })} />
                {p.label} is a personal profile
              </label>
            ))}
          </div>
        </div>
      )}

      <p className="text-[11.5px] leading-snug text-muted">
        {out.length > 0 && <>A <b className="text-sky-800">heads-up</b> shows in Needs you and goes out after {autonomy.heads_up_minutes} minutes unless someone edits or stops it. </>}
        Even when something is allowed, it still asks if the content is sensitive (prices, legal or health claims, competitors, complaints), if it
        doesn&apos;t pass the quality check, or once it reaches the daily limit. After a few approvals you didn&apos;t change, it suggests asking
        less; if people stop or flag what went out, it asks first again. You can change all of this on the goal page.
      </p>
    </section>
  );
}

function defaultCap(a: Autonomy, key: string) {
  for (const k of ["balanced", "fast"] as const) {
    const cap = a.presets[k].rows.find((r) => r.key === key)?.daily_cap;
    if (cap) return cap;
  }
  return 10;
}

function RowModes({ row, onChange }: { row: AutonomyRow; onChange: (m: Mode) => void }) {
  const options = modesFor({ key: row.key, default: "ask" }).filter((m) => !(row.key === "spend_money" && m === "auto"));
  return (
    <div className="inline-flex shrink-0 overflow-hidden rounded-md border border-line text-[11.5px] font-semibold">
      {options.map((m) => (
        <button key={m} type="button" onClick={() => m !== row.mode && onChange(m)} title={MODE_WORDS[m].long("the team")}
          className={cx("inline-flex items-center gap-1 px-2 py-1 transition", row.mode === m ? cx(MODE_STYLE[m], "ring-0") : "bg-white text-muted hover:bg-stone-50")}>
          {row.mode === m && MODE_ICON[m]} {MODE_WORDS[m].short}
        </button>
      ))}
    </div>
  );
}

/** For each kind of action, the mode that will apply once the goals start (strictest wins). */
export function modeFromChoice(autonomies: Autonomy[], choice: AutonomyChoice): (k: string) => Mode | undefined {
  const byKey: Record<string, Mode> = {};
  for (const a of autonomies) {
    for (const r of chosenRows(a, choice)) {
      byKey[r.key] = byKey[r.key] && STRICT[byKey[r.key]] > STRICT[r.mode] ? byKey[r.key] : r.mode;
    }
  }
  return (k) => byKey[k];
}
