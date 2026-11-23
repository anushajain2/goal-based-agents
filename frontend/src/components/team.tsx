"use client";

import { cx } from "./ui";

const PALETTE = ["bg-stone-900", "bg-stone-800", "bg-black", "bg-stone-700", "bg-neutral-800", "bg-stone-800"];

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

/** An AI employee's avatar: a bot, coloured consistently by name. */
export function AgentAvatar({ name, size = 36, state }: { name: string; size?: number; state?: "working" | "waiting" | "idle" }) {
  return (
    <span className={cx("relative inline-grid shrink-0 place-items-center rounded-xl font-mono font-semibold text-white", PALETTE[hash(name) % PALETTE.length])}
      style={{ width: size, height: size, fontSize: Math.max(11, size * 0.42), letterSpacing: "-0.04em" }} aria-label={name}>
      {monogram(name)}
      {state && state !== "idle" && (
        <span className={cx("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white", state === "working" ? "animate-pulse bg-signal-500" : "bg-signal-500")} />
      )}
    </span>
  );
}

/** A person's initials avatar. */
export function PersonAvatar({ name, size = 28, title }: { name: string; size?: number; title?: string }) {
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return (
    <span title={title || name} className="inline-grid shrink-0 place-items-center rounded-full bg-stone-200 text-[11px] font-bold text-stone-700 ring-2 ring-white" style={{ width: size, height: size }}>
      {initials || "?"}
    </span>
  );
}
