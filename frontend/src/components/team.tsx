"use client";

import { Bot } from "lucide-react";

import { cx } from "./ui";

const PALETTE = [
  "from-sky-500 to-blue-600",
  "from-violet-500 to-purple-600",
  "from-emerald-500 to-teal-600",
  "from-amber-500 to-orange-600",
  "from-rose-500 to-pink-600",
  "from-indigo-500 to-blue-700",
  "from-lime-500 to-green-600",
  "from-fuchsia-500 to-violet-600",
];

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** An AI employee's avatar: a bot, coloured consistently by name. */
export function AgentAvatar({ name, size = 36, state }: { name: string; size?: number; state?: "working" | "waiting" | "idle" }) {
  return (
    <span className={cx("relative inline-grid shrink-0 place-items-center rounded-xl bg-gradient-to-br text-white", PALETTE[hash(name) % PALETTE.length])} style={{ width: size, height: size }}>
      <Bot size={size * 0.55} />
      {state && state !== "idle" && (
        <span className={cx("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white", state === "working" ? "animate-pulse bg-emerald-500" : "bg-amber-500")} />
      )}
    </span>
  );
}

/** A person's initials avatar. */
export function PersonAvatar({ name, size = 28, title }: { name: string; size?: number; title?: string }) {
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return (
    <span title={title || name} className="inline-grid shrink-0 place-items-center rounded-full bg-gray-200 text-[11px] font-bold text-gray-700 ring-2 ring-white" style={{ width: size, height: size }}>
      {initials || "?"}
    </span>
  );
}
