"use client";

import { Bot, Eye, ThumbsUp, X } from "lucide-react";
import { useEffect, useState } from "react";

const KEY = "autopilot:your-role-dismissed";

/** For everyone on the team: you don't need to learn AI. It does the work and shows it; you decide. */
export function YourRole() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { setShow(localStorage.getItem(KEY) !== "1"); } catch { setShow(true); }
  }, []);
  if (!show) return null;
  const hide = () => {
    setShow(false);
    try { localStorage.setItem(KEY, "1"); } catch { /* shows again next time */ }
  };
  const steps: [React.ReactNode, string, string][] = [
    [<Bot key="b" size={16} />, "AI does the work", "Oton works on your team's goals every day."],
    [<Eye key="e" size={16} />, "It shows its work", "Every draft, step, source and reason, ready to check."],
    [<ThumbsUp key="t" size={16} />, "You make the call", "You choose what goes out on its own; everything else waits for a person's yes."],
  ];
  return (
    <section className="relative rounded-2xl border border-line bg-white p-5 shadow-[var(--shadow-card)]">
      <button onClick={hide} aria-label="Hide" className="absolute right-3 top-3 rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-ink"><X size={16} /></button>
      <div className="text-[15px] font-semibold">No AI skills needed. You just approve.</div>
      <p className="mt-0.5 text-[13px] text-muted">Human accuracy at AI speed. Here&apos;s how it works for you.</p>
      <ol className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-3">
        {steps.map(([icon, title, text], i) => (
          <li key={title} className="flex gap-3">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100">{icon}</span>
            <span className="min-w-0">
              <span className="block text-[13.5px] font-semibold">{i + 1}. {title}</span>
              <span className="block text-[12.5px] leading-snug text-muted">{text}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
