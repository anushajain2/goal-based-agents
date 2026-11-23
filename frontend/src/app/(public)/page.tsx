"use client";

import { ArrowRight, Check, Globe, Hand, Lock, ShieldCheck, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { cx } from "@/components/ui";

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);

  return (
    <div className="min-h-screen bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <EmployeeAvatar size={30} />
            <span className="text-[17px] font-semibold tracking-tight">Autopilot</span>
          </Link>
          <nav className="hidden gap-6 text-sm font-medium text-zinc-600 md:flex">
            <a href="#why" className="hover:text-ink">Why goals</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#results" className="hover:text-ink">Results</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!signedIn && <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 sm:inline-flex">Log in</Link>}
            <Link href={signedIn ? "/home" : "/signup"} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
              {signedIn ? "Open dashboard" : "Get started"} <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[680px] bg-[radial-gradient(55%_60%_at_50%_0%,rgba(0,0,0,0.05),transparent),radial-gradient(40%_40%_at_90%_20%,rgba(0,0,0,0.03),transparent)]" />
        <div className="relative mx-auto max-w-6xl px-5 pb-16 pt-16 text-center sm:pt-24">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1 text-xs font-semibold text-zinc-600 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Goal-based AI agents
          </span>
          <h1 className="mx-auto mt-6 max-w-4xl text-balance text-[44px] font-semibold leading-[1.02] tracking-tight sm:text-[68px]">
            Stop prompting.{" "}
            <span className="text-zinc-400">Start hitting goals.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-balance text-[18px] leading-relaxed text-zinc-600">
            Enter your website. We analyze your company, set up AI agents for every team with the right goals, and they work on them every day.
            <b className="font-semibold text-ink"> You just approve.</b>
          </p>
          <div className="mx-auto mt-9 max-w-xl"><WebsiteStart signedIn={signedIn} /></div>
          <ul className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13px] text-zinc-500">
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> No prompts to write</li>
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> Team ready in minutes</li>
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> Nothing goes out without your OK</li>
          </ul>
          <div className="mx-auto mt-14 max-w-5xl">
            <Clip name="setup" label="Your website → your AI team, in two minutes" priority />
          </div>
        </div>
      </section>

      {/* The old way */}
      <section id="why" className="scroll-mt-20 border-t border-line bg-zinc-50/70 py-24">
        <div className="mx-auto max-w-5xl px-5">
          <Title title="Prompting is the old way." sub="Chat AI makes you the manager, the prompt writer and the worker. Autopilot flips it." />
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-line bg-white p-7">
              <div className="text-[13px] font-semibold uppercase tracking-[0.08em] text-zinc-400">Chat AI</div>
              <ul className="mt-5 space-y-3.5">
                {["You figure out what to ask", "You write and rewrite prompts", "You copy, paste and do the work", "It forgets everything tomorrow"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] text-zinc-500">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-400"><X size={13} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-3xl bg-zinc-900 p-7 text-white shadow-[0_30px_70px_-25px_rgba(0,0,0,0.35)]">
              <div className="text-[13px] font-semibold uppercase tracking-[0.08em] text-white/70">Autopilot</div>
              <ul className="mt-5 space-y-3.5">
                {["We work out what your company needs", "You set goals, not prompts", "Agents do the work, every day", "You approve what goes out", "They get better every week"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] font-medium">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/20"><Check size={13} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 py-24">
        <div className="mx-auto max-w-6xl space-y-24 px-5">
          <Title title="Then they work. Every day." sub="You stay in charge without doing the work." />
          <Step n={1} title="Connect once" text="Gmail, LinkedIn, HubSpot, GitHub, your database. One click each." clip="connect" label="Connections" />
          <Step n={2} title="Approve, don't operate" text="Agents prepare everything. You say yes, edit it, or say no." clip="approve" label="Needs you" flip />
          <Step n={3} title="They get better every week" text="AI team leads raise targets, cut what isn't working, and hire new agents." clip="lead" label="AI team lead" />
        </div>
      </section>

      {/* Results */}
      <section id="results" className="scroll-mt-20 border-t border-line bg-zinc-50/70 py-24">
        <div className="mx-auto max-w-6xl px-5">
          <Title title="What your AI team gets done in week one" />
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Result team="Sales" text="40 qualified leads, each with a personal email ready to send" />
            <Result team="Marketing" text="A month of posts, written in your voice" />
            <Result team="Product" text="Why signups dropped, with the numbers behind it" />
            <Result team="Support" text="Every new ticket answered within the hour" />
            <Result team="Finance" text="Every overdue invoice chased, politely" />
            <Result team="Hiring" text="20 ranked candidates for your open role" />
          </div>
          <p className="mt-10 text-center text-[14px] text-zinc-500">
            For B2B startups · agencies · e-commerce brands · expert firms · solo founders
          </p>
        </div>
      </section>

      {/* Trust */}
      <section className="bg-ink py-20 text-white">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/10"><Lock size={20} /></span>
            <h2 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Autonomous. Never out of control.</h2>
          </div>
          <ul className="grid gap-3 sm:grid-cols-3">
            <Trust icon={<Hand size={17} />} text="Sends, posts, payments and merges wait for your yes" />
            <Trust icon={<Wallet size={17} />} text="Hard budgets. A few dollars a week to start" />
            <Trust icon={<ShieldCheck size={17} />} text="Never sees or types your passwords" />
          </ul>
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 py-24 text-center">
        <h2 className="mx-auto max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-5xl">Your AI team is one website away.</h2>
        <div className="mx-auto mt-8 max-w-xl"><WebsiteStart signedIn={signedIn} /></div>
      </section>

      <footer className="border-t border-line py-8 text-center text-xs text-zinc-500">
        <div className="flex items-center justify-center gap-2"><EmployeeAvatar size={18} /> Autopilot</div>
      </footer>
    </div>
  );
}

/** "yourcompany.com → Build my AI team": the website goes with them into setup. */
function WebsiteStart({ signedIn }: { signedIn: boolean }) {
  const router = useRouter();
  const [site, setSite] = useState("");
  function go(e: FormEvent) {
    e.preventDefault();
    try {
      if (site.trim()) localStorage.setItem("autopilot:website", site.trim());
    } catch { /* fine: they type it again in setup */ }
    router.push(signedIn ? "/welcome" : "/signup");
  }
  return (
    <form onSubmit={go} className="flex flex-col gap-2 rounded-2xl border border-line bg-white p-2 shadow-[0_20px_50px_-20px_rgba(16,24,40,0.3)] sm:flex-row sm:items-center">
      <label className="flex min-w-0 flex-1 items-center gap-2.5 px-3">
        <Globe size={18} className="shrink-0 text-zinc-400" />
        <input value={site} onChange={(e) => setSite(e.target.value)} placeholder="yourcompany.com" aria-label="Your website"
          className="h-11 w-full bg-transparent text-[16px] outline-none placeholder:text-zinc-400" />
      </label>
      <button className="inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-brand-500 px-6 text-[15px] font-semibold text-white shadow-lg shadow-black/15 transition hover:bg-brand-600">
        Build my AI team <ArrowRight size={17} />
      </button>
    </form>
  );
}

/** A looping product clip in a window frame. Plays like a GIF; only while on screen. */
function Clip({ name, label, priority }: { name: string; label: string; priority?: boolean }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) v.play().catch(() => null); else v.pause(); }, { threshold: 0.25 });
    io.observe(v);
    return () => io.disconnect();
  }, []);
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white text-left shadow-[0_30px_80px_-24px_rgba(16,24,40,0.35),0_2px_8px_rgba(16,24,40,0.06)]">
      <div className="flex items-center gap-1.5 border-b border-line bg-zinc-50 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-zinc-300" /><span className="h-2.5 w-2.5 rounded-full bg-zinc-300" /><span className="h-2.5 w-2.5 rounded-full bg-zinc-300" />
        <span className="ml-3 truncate text-[12px] font-medium text-zinc-500">{label}</span>
      </div>
      <video ref={ref} src={`/clips/${name}.mp4`} poster={`/clips/${name}.jpg`} autoPlay muted loop playsInline
        preload={priority ? "auto" : "metadata"} className="block aspect-[8/5] w-full bg-zinc-50" aria-label={label} />
    </div>
  );
}

function Title({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-[44px] sm:leading-[1.1]">{title}</h2>
      {sub && <p className="mt-3 text-[17px] text-zinc-600">{sub}</p>}
    </div>
  );
}

function Step({ n, title, text, clip, label, flip }: { n: number; title: string; text: string; clip: string; label: string; flip?: boolean }) {
  return (
    <div className={cx("grid items-center gap-10", flip ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]" : "lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]")}>
      <div className={flip ? "lg:order-2" : ""}>
        <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-500 text-sm font-semibold text-white">{n}</span>
        <h3 className="mt-4 text-2xl font-semibold tracking-tight sm:text-[32px]">{title}</h3>
        <p className="mt-3 max-w-sm text-[17px] leading-relaxed text-zinc-600">{text}</p>
      </div>
      <div className={flip ? "lg:order-1" : ""}><Clip name={clip} label={label} /></div>
    </div>
  );
}

function Result({ team, text }: { team: string; text: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-6 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.06em] text-brand-600">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-brand-50"><Check size={12} /></span>{team}
      </div>
      <p className="mt-3 text-[18px] font-semibold leading-snug tracking-tight">{text}</p>
    </div>
  );
}

function Trust({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="rounded-2xl bg-white/5 p-4 ring-1 ring-inset ring-white/10">
      <span className="text-emerald-400">{icon}</span>
      <p className="mt-2 text-[14px] leading-snug text-white/85">{text}</p>
    </li>
  );
}
