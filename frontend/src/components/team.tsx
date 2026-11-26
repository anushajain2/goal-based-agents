"use client";

import { cx } from "./ui";

/** Soft tints: [background, text]. Each name keeps its colour everywhere. */
const PALETTE: [string, string][] = [
  ["#e8f0ff", "#2456d6"],
  ["#fff0e6", "#c2410c"],
  ["#e7f6ee", "#15803d"],
  ["#fdeef5", "#be185d"],
  ["#fdf5dc", "#a16207"],
  ["#e6f6f8", "#0e7490"],
  ["#f0f1f5", "#475467"],
  ["#eef2ff", "#1e3a8a"],
];

/** "Outbound Agent" -> "O", "People & Hiring Agent" -> "PH". */
function monogram(name: string) {
  const words = name.split(/\s+/).filter((w) => /^[A-Za-z0-9]/.test(w) && w.toLowerCase() !== "agent");
  return (words.length ? words : [name]).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** A soft colour pair [background, text] that stays the same for a name (a team, a goal). */
export function tintFor(name: string): [string, string] {
  return PALETTE[hash(name) % PALETTE.length];
}

/** A team's name as a small coloured tag. */
export function TeamTag({ name }: { name: string }) {
  const [bg, fg] = tintFor(name);
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-0.5 pl-2 pr-2.5 text-[12px] font-medium" style={{ background: bg, color: fg }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: fg }} />{name}
    </span>
  );
}

/** An agent's avatar: a monogram on a soft tint, coloured consistently by name. */
export function AgentAvatar({ name, size = 36, state }: { name: string; size?: number; state?: "working" | "waiting" | "idle" }) {
  const [bg, fg] = PALETTE[hash(name) % PALETTE.length];
  return (
    <span className="relative inline-grid shrink-0 place-items-center rounded-full font-semibold"
      style={{ width: size, height: size, fontSize: Math.max(11, size * 0.4), letterSpacing: "-0.03em", background: bg, color: fg }} aria-label={name}>
      {monogram(name)}
      {state && state !== "idle" && (
        <span className={cx("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white", state === "working" ? "animate-pulse bg-emerald-500" : "bg-signal-500")} />
      )}
    </span>
  );
}

/** A person's initials avatar. */
export function PersonAvatar({ name, size = 28, title }: { name: string; size?: number; title?: string }) {
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return (
    <span title={title || name} className="inline-grid shrink-0 place-items-center rounded-full bg-stone-100 text-[11px] font-bold text-stone-700 ring-2 ring-white" style={{ width: size, height: size }}>
      {initials || "?"}
    </span>
  );
}
