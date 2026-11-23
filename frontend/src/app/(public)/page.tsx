"use client";

import { ArrowRight, Check, Globe, Hand, Lock, ShieldCheck, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/Shell";
import { cx } from "@/components/ui";

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3">
          <Logo />
          <nav className="hidden gap-6 text-sm font-medium text-stone-600 md:flex">
            <a href="#why" className="hover:text-ink">Why goals</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#results" className="hover:text-ink">Results</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!signedIn && <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-sm font-semibold text-stone-700 hover:bg-stone-200/60 sm:inline-flex">Log in</Link>}
            <Link href={signedIn ? "/home" : "/signup"} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
              {signedIn ? "Open dashboard" : "Get started"} <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(20,20,19,0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgba(20,20,19,0.045)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_70%)]" />
        <div className="relative mx-auto max-w-6xl px-5 pb-16 pt-16 text-center sm:pt-24">
          <span className="inline-flex items-center gap-2.5 rounded-full border border-line bg-white px-3.5 py-1.5 font-mono text-[11.5px] font-medium uppercase tracking-[0.08em] text-stone-600 shadow-sm">
            <span className="signal-dot" /> Goal-based AI agents
          </span>
          <h1 className="display mx-auto mt-7 max-w-4xl text-[56px] leading-[0.98] sm:text-[92px]">
            Stop prompting.
            <br />
            Start hitting <em className="italic">goals</em><span className="text-signal-500">.</span>
          </h1>
          <p className="mx-auto mt-7 max-w-2xl text-balance text-[18px] leading-relaxed text-stone-600">
            Enter your website. We analyze your company, set up AI agents for every team with the right goals, and they work on them every day.
            <b className="font-semibold text-ink"> You just approve.</b>
          </p>
          <div className="mx-auto mt-9 max-w-xl"><WebsiteStart signedIn={signedIn} /></div>
          <div className="mt-6 flex justify-center"><LiveTicker /></div>
          <div className="mx-auto mt-14 max-w-5xl">
            <Clip name="setup" label="Your website → your AI team, in two minutes" priority />
          </div>
          <Stats />
        </div>
      </section>

      {/* The old way */}
      <section id="why" className="scroll-mt-20 border-t border-line bg-white py-24">
        <div className="mx-auto max-w-5xl px-5">
          <Title kicker="01 · Why goals" title={<>Prompting is the <em className="italic">old</em> way.</>} sub="Chat AI makes you the manager, the prompt writer and the worker. Autopilot flips it." />
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-line bg-canvas p-7">
              <div className="font-mono text-[11.5px] font-medium uppercase tracking-[0.08em] text-stone-400">Chat AI</div>
              <ul className="mt-5 space-y-3.5">
                {["You figure out what to ask", "You write and rewrite prompts", "You copy, paste and do the work", "It forgets everything tomorrow"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] text-stone-500">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-stone-200/70 text-stone-400"><X size={13} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-3xl bg-ink p-7 text-white shadow-[0_30px_70px_-25px_rgba(20,20,19,0.55)]">
              <div className="flex items-center gap-2 font-mono text-[11.5px] font-medium uppercase tracking-[0.08em] text-white/60"><span className="signal-dot" /> Autopilot</div>
              <ul className="mt-5 space-y-3.5">
                {["We work out what your company needs", "You set goals, not prompts", "Agents do the work, every day", "You approve what goes out", "They get better every week"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] font-medium">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-signal-500 text-white"><Check size={13} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-t border-line py-24">
        <div className="mx-auto max-w-6xl space-y-24 px-5">
          <Title kicker="02 · How it works" title={<>Then they work. <em className="italic">Every day.</em></>} sub="You stay in charge without doing the work." />
          <Step n="01" title="Connect once" text="Gmail, LinkedIn, HubSpot, GitHub, your database. One click each." clip="connect" label="Connections" />
          <Step n="02" title="Approve, don't operate" text="Agents prepare everything. You say yes, edit it, or say no." clip="approve" label="Needs you" flip />
          <Step n="03" title="They get better every week" text="AI team leads raise targets, cut what isn't working, and hire new agents." clip="lead" label="AI team lead" />
        </div>
      </section>

      {/* Results */}
      <section id="results" className="scroll-mt-20 border-t border-line bg-white py-24">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="03 · Results" title={<>What your AI team gets done in <em className="italic">week one</em></>} />
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Result team="Sales" text="40 qualified leads, each with a personal email ready to send" />
            <Result team="Marketing" text="A month of posts, written in your voice" />
            <Result team="Product" text="Why signups dropped, with the numbers behind it" />
            <Result team="Support" text="Every new ticket answered within the hour" />
            <Result team="Finance" text="Every overdue invoice chased, politely" />
            <Result team="Hiring" text="20 ranked candidates for your open role" />
          </div>
          <p className="mt-10 text-center font-mono text-[12px] uppercase tracking-[0.08em] text-stone-500">
            For B2B startups · agencies · e-commerce brands · expert firms · solo founders
          </p>
        </div>
      </section>

      {/* Trust */}
      <section className="bg-ink py-20 text-white">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/10"><Lock size={20} /></span>
            <h2 className="display mt-5 text-[44px] leading-[1.02] sm:text-[56px]">Autonomous. <em className="italic text-white/70">Never out of control.</em></h2>
          </div>
          <ul className="grid gap-3 sm:grid-cols-3">
            <Trust icon={<Hand size={17} />} text="Sends, posts, payments and merges wait for your yes" />
            <Trust icon={<Wallet size={17} />} text="Hard budgets. A few dollars a week to start" />
            <Trust icon={<ShieldCheck size={17} />} text="Never sees or types your passwords" />
          </ul>
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 py-28 text-center">
        <h2 className="display mx-auto max-w-3xl text-balance text-[48px] leading-[1.02] sm:text-[72px]">
          Your AI team is one <em className="italic">website</em> away<span className="text-signal-500">.</span>
        </h2>
        <div className="mx-auto mt-10 max-w-xl"><WebsiteStart signedIn={signedIn} /></div>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 text-xs text-stone-500">
          <Logo small />
          <span className="font-mono uppercase tracking-[0.08em]">Goals, not prompts</span>
        </div>
      </footer>
    </div>
  );
}

function Logo({ small }: { small?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <BrandMark size={small ? 22 : 30} />
      <span className={cx("display leading-none", small ? "text-[19px] text-ink" : "text-[25px]")}>Autopilot</span>
    </Link>
  );
}

/** What AI teams are doing right now (examples), one line at a time. */
const LIVE = [
  ["Outbound Agent", "drafted 12 personal emails for review"],
  ["Marketing Lead", "raised a weekly target from 40 to 70 signups"],
  ["Support Agent", "answered 9 tickets in under an hour"],
  ["Collections Agent", "chased 5 overdue invoices"],
  ["Product Agent", "explained why activation dropped 8%"],
  ["Recruiting Agent", "shortlisted 6 account executives"],
];

function LiveTicker() {
  const [i, setI] = useState(0);
  const [show, setShow] = useState(true);
  useEffect(() => {
    const t = setInterval(() => {
      setShow(false);
      setTimeout(() => { setI((x) => (x + 1) % LIVE.length); setShow(true); }, 280);
    }, 2600);
    return () => clearInterval(t);
  }, []);
  const [who, what] = LIVE[i];
  return (
    <div className="inline-flex max-w-full items-center gap-2.5 rounded-full border border-line bg-white/80 px-4 py-2 text-[13px] shadow-sm">
      <span className="signal-dot shrink-0" />
      <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-stone-400">Live</span>
      <span className={cx("min-w-0 truncate transition-all duration-300", show ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0")}>
        <b className="font-semibold">{who}</b> <span className="text-stone-600">{what}</span>
      </span>
    </div>
  );
}

/** Numbers that count up when they come into view. */
function Stats() {
  const ref = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setOn(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect(); } }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const items: [number, string, string][] = [[51, "", "AI roles"], [21, "", "teams"], [1000, "+", "apps"], [5, "", "company packs"]];
  return (
    <div ref={ref} className="mx-auto mt-12 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-4">
      {items.map(([n, plus, label]) => (
        <div key={label} className="bg-canvas px-4 py-5">
          <div className="tabular text-[30px] font-semibold leading-none"><CountUp to={n} on={on} />{plus}</div>
          <div className="mt-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-stone-500">{label}</div>
        </div>
      ))}
    </div>
  );
}

function CountUp({ to, on }: { to: number; on: boolean }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!on) return;
    const start = performance.now(), ms = 1200;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      setV(Math.round(to * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [on, to]);
  return <>{v.toLocaleString()}</>;
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
    <form onSubmit={go} className="flex flex-col gap-2 rounded-2xl border border-line bg-white p-2 shadow-[0_20px_50px_-20px_rgba(20,20,19,0.3)] sm:flex-row sm:items-center">
      <label className="flex min-w-0 flex-1 items-center gap-2.5 px-3">
        <Globe size={18} className="shrink-0 text-stone-400" />
        <input value={site} onChange={(e) => setSite(e.target.value)} placeholder="yourcompany.com" aria-label="Your website"
          className="h-11 w-full bg-transparent font-mono text-[15px] outline-none placeholder:text-stone-400" />
      </label>
      <button className="inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-signal-500 px-6 text-[15px] font-semibold text-white shadow-lg shadow-signal-500/25 transition hover:bg-signal-600">
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
    <div className="overflow-hidden rounded-2xl border border-line bg-white text-left shadow-[0_30px_80px_-24px_rgba(20,20,19,0.35),0_2px_8px_rgba(20,20,19,0.06)]">
      <div className="flex items-center gap-1.5 border-b border-line bg-canvas px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-stone-300" /><span className="h-2.5 w-2.5 rounded-full bg-stone-300" /><span className="h-2.5 w-2.5 rounded-full bg-stone-300" />
        <span className="ml-3 truncate font-mono text-[11px] uppercase tracking-[0.06em] text-stone-500">{label}</span>
      </div>
      <video ref={ref} src={`/clips/${name}.mp4`} poster={`/clips/${name}.jpg`} autoPlay muted loop playsInline
        preload={priority ? "auto" : "metadata"} className="block aspect-[8/5] w-full bg-canvas" aria-label={label} />
    </div>
  );
}

function Title({ kicker, title, sub }: { kicker: string; title: ReactNode; sub?: string }) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <div className="font-mono text-[11.5px] font-medium uppercase tracking-[0.1em] text-signal-600">{kicker}</div>
      <h2 className="display mt-3 text-balance text-[42px] leading-[1.02] sm:text-[60px]">{title}</h2>
      {sub && <p className="mt-4 text-[17px] text-stone-600">{sub}</p>}
    </div>
  );
}

function Step({ n, title, text, clip, label, flip }: { n: string; title: string; text: string; clip: string; label: string; flip?: boolean }) {
  return (
    <div className={cx("grid items-center gap-10", flip ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]" : "lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]")}>
      <div className={flip ? "lg:order-2" : ""}>
        <span className="font-mono text-[13px] font-medium text-signal-600">{n}</span>
        <h3 className="display mt-2 text-[36px] leading-[1.05] sm:text-[44px]">{title}</h3>
        <p className="mt-3 max-w-sm text-[17px] leading-relaxed text-stone-600">{text}</p>
      </div>
      <div className={flip ? "lg:order-1" : ""}><Clip name={clip} label={label} /></div>
    </div>
  );
}

function Result({ team, text }: { team: string; text: string }) {
  return (
    <div className="rounded-2xl border border-line bg-canvas p-6 transition hover:-translate-y-0.5 hover:bg-white hover:shadow-[var(--shadow-pop)]">
      <div className="flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-stone-500">
        <span className="h-1.5 w-1.5 rounded-full bg-signal-500" />{team}
      </div>
      <p className="display mt-3 text-[25px] leading-[1.15]">{text}</p>
    </div>
  );
}

function Trust({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="rounded-2xl bg-white/5 p-4 ring-1 ring-inset ring-white/10">
      <span className="text-signal-400">{icon}</span>
      <p className="mt-2 text-[14px] leading-snug text-white/85">{text}</p>
    </li>
  );
}
