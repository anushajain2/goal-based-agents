"use client";

import {
  ArrowRight,
  Bot,
  Check,
  Compass,
  Hand,
  ListChecks,
  Lock,
  Plug,
  ShieldCheck,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { cx } from "@/components/ui";

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);
  const start = signedIn ? "/home" : "/signup";

  return (
    <div className="min-h-screen bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <EmployeeAvatar size={30} />
            <span className="text-[17px] font-semibold tracking-tight">Autopilot</span>
          </Link>
          <nav className="hidden gap-6 text-sm font-medium text-zinc-600 md:flex">
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#product" className="hover:text-ink">Product</a>
            <a href="#who" className="hover:text-ink">Who it&apos;s for</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!signedIn && <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 sm:inline-flex">Log in</Link>}
            <Link href={start} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
              {signedIn ? "Open dashboard" : "Get started"} <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[640px] bg-[radial-gradient(55%_60%_at_50%_0%,rgba(79,70,229,0.16),transparent),radial-gradient(40%_40%_at_90%_20%,rgba(139,92,246,0.12),transparent)]" />
        <div className="relative mx-auto max-w-6xl px-5 pb-16 pt-16 text-center sm:pt-24">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1 text-xs font-semibold text-zinc-600 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> AI employees for every team
          </span>
          <h1 className="mx-auto mt-6 max-w-4xl text-balance text-[40px] font-semibold leading-[1.05] tracking-tight sm:text-[60px]">
            Your AI team,{" "}
            <span className="bg-gradient-to-r from-brand-500 to-violet-600 bg-clip-text text-transparent">set up in minutes.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-[17px] leading-relaxed text-zinc-600">
            Share your website. Autopilot builds AI employees for every function, gives them goals and a budget, and asks you before anything goes out.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href={start} className="inline-flex h-12 items-center gap-2 rounded-xl bg-brand-500 px-6 text-[15px] font-semibold text-white shadow-lg shadow-brand-500/25 transition hover:bg-brand-600">
              Build my AI team <ArrowRight size={17} />
            </Link>
            <a href="#how" className="inline-flex h-12 items-center rounded-xl px-5 text-[15px] font-semibold text-zinc-700 hover:bg-zinc-100">See how it works</a>
          </div>
          <ul className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13px] text-zinc-500">
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> Starts at a few dollars a week</li>
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> Budgets it can&apos;t overspend</li>
            <li className="flex items-center gap-1.5"><Check size={14} className="text-emerald-600" /> Your OK before anything goes out</li>
          </ul>
          <div className="mx-auto mt-14 max-w-5xl">
            <Clip name="setup" label="From a website to an AI team" priority />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-t border-line bg-zinc-50/70 py-24">
        <div className="mx-auto max-w-6xl space-y-24 px-5">
          <Title eyebrow="How it works" title="Three steps. Then it just works." />
          <Step n={1} title="Connect your tools once" text="Apps, websites, GitHub and your data. Each shows what it does on its own and what needs your OK." clip="connect" label="Connections" />
          <Step n={2} title="Approve what matters" text="Every message, post, payment and merge waits for a yes. Edit it, comment, or say no." clip="approve" label="Needs you" flip />
          <Step n={3} title="It keeps getting better" text="AI team leads review results, research the market, and suggest better targets, goals and new hires." clip="lead" label="AI team lead" />
        </div>
      </section>

      {/* Product */}
      <section id="product" className="scroll-mt-20 py-24">
        <div className="mx-auto max-w-6xl px-5">
          <Title eyebrow="Product" title="Everything a team needs" />
          <div className="mt-12 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <Feature icon={<Target size={18} />} title="Goals with targets" text="Ongoing goals. Weekly targets that grow with results." />
            <Feature icon={<Compass size={18} />} title="AI team leads" text="Always reviewing each team and suggesting what's next." />
            <Feature icon={<Users size={18} />} title="Your org chart" text="Every request goes to the right person." />
            <Feature icon={<Wallet size={18} />} title="Hard budgets" text="A limit per goal. Work stops when it's spent." />
            <Feature icon={<ListChecks size={18} />} title="Every step logged" text="What each AI employee did, and what it cost." />
            <Feature icon={<Bot size={18} />} title="50+ AI roles" text="Sales, marketing, support, finance, engineering and more." />
            <Feature icon={<Plug size={18} />} title="1,000+ apps" text="Plus your sites, GitHub, database and MCP tools." />
            <Feature icon={<ShieldCheck size={18} />} title="Guardrails" text="Rules in plain words. Blocks enforced in code." />
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section id="who" className="scroll-mt-20 border-t border-line bg-zinc-50/70 py-24">
        <div className="mx-auto max-w-6xl px-5">
          <Title eyebrow="Who it's for" title="A team that fits your company" sub="It reads your website and picks the right AI employees for your type and size of company." />
          <div className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
            <Who title="B2B startups" roles={["Outbound", "Product", "Fundraising"]} />
            <Who title="Solo founders" roles={["SEO", "Community", "Support"]} />
            <Who title="Agencies" roles={["New clients", "Client work", "Reports"]} />
            <Who title="Expert firms" roles={["Proposals", "Client intake", "Collections"]} />
            <Who title="E-commerce brands" roles={["Ads", "Creators", "Merchandising"]} />
          </div>
        </div>
      </section>

      {/* Trust */}
      <section className="bg-ink py-20 text-white">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/10"><Lock size={20} /></span>
            <h2 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Nothing goes out without your OK.</h2>
          </div>
          <ul className="grid gap-3 sm:grid-cols-3">
            <Trust icon={<Hand size={17} />} text="Send, post, pay and merge are blocked in code until approved" />
            <Trust icon={<Wallet size={17} />} text="Budgets are hard limits, checked before every step" />
            <Trust icon={<ShieldCheck size={17} />} text="It never sees or types your passwords" />
          </ul>
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 py-24 text-center">
        <h2 className="mx-auto max-w-2xl text-3xl font-semibold tracking-tight sm:text-5xl">Build your AI team today.</h2>
        <p className="mt-4 text-zinc-600">Two minutes to set up. You approve everything that matters.</p>
        <Link href={start} className="mt-8 inline-flex h-12 items-center gap-2 rounded-xl bg-brand-500 px-7 text-[15px] font-semibold text-white shadow-lg shadow-brand-500/25 transition hover:bg-brand-600">
          Get started <ArrowRight size={17} />
        </Link>
      </section>

      <footer className="border-t border-line py-8 text-center text-xs text-zinc-500">
        <div className="flex items-center justify-center gap-2"><EmployeeAvatar size={18} /> Autopilot</div>
      </footer>
    </div>
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
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[0_30px_80px_-24px_rgba(16,24,40,0.35),0_2px_8px_rgba(16,24,40,0.06)]">
      <div className="flex items-center gap-1.5 border-b border-line bg-zinc-50 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-zinc-300" /><span className="h-2.5 w-2.5 rounded-full bg-zinc-300" /><span className="h-2.5 w-2.5 rounded-full bg-zinc-300" />
        <span className="ml-3 truncate text-[12px] font-medium text-zinc-500">{label}</span>
      </div>
      <video ref={ref} src={`/clips/${name}.mp4`} poster={`/clips/${name}.jpg`} autoPlay muted loop playsInline
        preload={priority ? "auto" : "metadata"} className="block aspect-[8/5] w-full bg-zinc-50" aria-label={label} />
    </div>
  );
}

function Title({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <div className="text-[12.5px] font-semibold uppercase tracking-[0.08em] text-brand-600">{eyebrow}</div>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-[40px]">{title}</h2>
      {sub && <p className="mt-3 text-zinc-600">{sub}</p>}
    </div>
  );
}

function Step({ n, title, text, clip, label, flip }: { n: number; title: string; text: string; clip: string; label: string; flip?: boolean }) {
  return (
    <div className={cx("grid items-center gap-10", flip ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]" : "lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]")}>
      <div className={flip ? "lg:order-2" : ""}>
        <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-500 text-sm font-semibold text-white">{n}</span>
        <h3 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h3>
        <p className="mt-3 max-w-sm text-[16px] leading-relaxed text-zinc-600">{text}</p>
      </div>
      <div className={flip ? "lg:order-1" : ""}><Clip name={clip} label={label} /></div>
    </div>
  );
}

function Feature({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pop)] sm:p-5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-50 text-brand-600">{icon}</span>
      <div className="mt-4 font-semibold">{title}</div>
      <p className="mt-1 text-[13.5px] leading-relaxed text-zinc-600">{text}</p>
    </div>
  );
}

function Who({ title, roles }: { title: string; roles: string[] }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5 shadow-[var(--shadow-card)]">
      <div className="font-semibold">{title}</div>
      <ul className="mt-3 space-y-1.5">
        {roles.map((r) => (
          <li key={r} className="flex items-center gap-2 text-[13px] text-zinc-600">
            <span className="grid h-5 w-5 place-items-center rounded-full bg-violet-50 text-violet-600"><Bot size={11} /></span> {r}
          </li>
        ))}
      </ul>
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
