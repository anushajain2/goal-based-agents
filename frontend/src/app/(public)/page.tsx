"use client";

import { Activity, ArrowRight, Check, Eye, Hand, Home, Inbox, Plug, ShieldCheck, Sparkles, Target, Users, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/Shell";
import { cx } from "@/components/ui";

/** Each team keeps one soft colour: [background, text]. */
const TEAM: Record<string, [string, string]> = {
  Sales: ["#e8f0ff", "#2456d6"],
  Marketing: ["#fff0e6", "#c2410c"],
  Product: ["#e7f6ee", "#15803d"],
  Support: ["#fdeef5", "#be185d"],
  Finance: ["#fdf5dc", "#a16207"],
  Hiring: ["#e6f6f8", "#0e7490"],
};

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-5 py-3.5">
          <Logo />
          <nav className="hidden gap-7 text-[14.5px] font-medium text-stone-600 md:flex">
            <a href="#why" className="hover:text-ink">Why Autopilot</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#results" className="hover:text-ink">Results</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!signedIn && <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-[14.5px] font-semibold text-stone-700 hover:bg-stone-100 sm:inline-flex">Log in</Link>}
            <Link href={signedIn ? "/home" : "/signup"} className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
              {signedIn ? "Open dashboard" : "Get started"}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative">
        <div className="pointer-events-none absolute inset-x-0 -top-20 h-[900px] bg-[linear-gradient(to_right,rgba(16,24,40,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(16,24,40,0.05)_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_55%_60%_at_50%_30%,black_30%,transparent_75%)]" />
        <div className="pointer-events-none absolute left-1/2 top-[300px] h-[500px] w-[900px] max-w-full -translate-x-1/2 bg-[radial-gradient(closest-side,rgba(30,64,175,0.11),transparent)]" />
        <div className="relative mx-auto max-w-6xl px-5 pt-14 text-center sm:pt-20">
          <a href="#how" className="inline-flex items-center gap-2 rounded-full border border-line bg-white py-1 pl-1 pr-3 text-[13.5px] font-medium text-stone-700 shadow-[0_1px_2px_rgba(16,24,40,0.04)] hover:border-stone-300">
            <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-[12px] font-semibold text-brand-700">New</span>
            AI team leads that suggest their own goals <ArrowRight size={13} />
          </a>
          <h1 className="display mx-auto mt-7 max-w-4xl text-[48px] leading-[1.02] tracking-[-0.05em] sm:text-[84px]">
            Stop prompting.
            <br />
            Start hitting <Underlined>goals.</Underlined>
          </h1>
          <p className="mx-auto mt-6 max-w-[600px] text-balance text-[17px] leading-relaxed text-stone-600 sm:text-[19px]">
            Become an AI-native company without teaching anyone to use AI. We set up AI employees for every team. They do the work and show it. <b className="font-semibold text-ink">Your people give the final yes.</b>
          </p>
          <div className="mx-auto mt-9 max-w-[560px]"><WebsiteStart signedIn={signedIn} /></div>
          <div className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13.5px] text-muted">
            {["No AI skills needed", "See what you're missing", "Humans approve everything"].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check size={14} strokeWidth={2.5} className="text-brand-600" />{t}</span>
            ))}
          </div>
        </div>
        <ProductPreview />
        <div className="relative mt-14 px-5 text-center">
          <div className="text-[13px] text-stone-400">Works with the tools you already use</div>
          <div className="mt-2.5 text-balance text-[16px] font-semibold tracking-tight text-stone-400">
            Gmail · Slack · HubSpot · Salesforce · GitHub · Stripe · Notion · Linear · Shopify · 1000+ more
          </div>
        </div>
      </section>

      {/* Why goals */}
      <section id="why" className="scroll-mt-20 pt-28">
        <div className="mx-auto max-w-5xl px-5">
          <Title kicker="Why Autopilot" title="AI isn't the bottleneck. Knowing how to use it is." sub="Most companies stall at “where do we even use AI?” Autopilot answers that for every team, so nobody has to." />
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-line bg-canvas p-7">
              <div className="text-[13px] font-semibold text-stone-400">AI the usual way</div>
              <ul className="mt-5 space-y-3.5">
                {["Everyone has to learn prompting", "Each person works out where AI helps", "You copy, paste and do the work", "Adoption stalls after the pilot"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] text-stone-500">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-stone-200/70 text-stone-400"><X size={13} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative overflow-hidden rounded-3xl bg-brand-600 p-7 text-white shadow-[0_30px_70px_-25px_rgba(30,64,175,0.6)]">
              <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
              <div className="relative flex items-center gap-2 text-[13px] font-semibold text-white/70"><BrandMark size={18} /> Autopilot</div>
              <ul className="relative mt-5 space-y-3.5">
                {["AI set up for every team, automatically", "Nobody needs to learn AI", "Agents work on real goals, every day", "AI shows its work, people approve", "Better every week"].map((t) => (
                  <li key={t} className="flex items-center gap-3 text-[16px] font-medium">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white text-brand-600"><Check size={13} strokeWidth={3} /></span>{t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* What you're missing */}
      <section id="missing" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="Before anything else" title="See what you're missing out on."
            sub="We search for what your customers search, ask AI assistants what they recommend, and check what's public about you and your competitors. Each gap comes with the AI employee that fixes it, and what it costs, in steps." />
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            <Missing team="Marketing" title="Competitors own the searches buyers make" evidence="Rank 6 for “route planning software”. Asked the same question, AI assistants recommend three competitors and not you."
              steps={[["Start: page 1 for 3 searches", "$30"], ["Full: top 3 for the main search", "~$1,750"]]} fix="Win the searches" agent="Content Agent" />
            <Missing team="Support" title="Few reviews where buyers look" evidence="12 G2 reviews at 4.1 stars. Your two main competitors have 180 and 240."
              fix="Collect reviews from happy customers" agent="Reviews Agent" />
            <Missing team="Hiring" title="A key role open for 94 days" evidence="The Senior AE post has been up since August, with a job ad that doesn't mention pay or the product."
              fix="Fill the Senior AE role" agent="Recruiting Agent" />
          </div>
          <p className="mx-auto mt-6 max-w-2xl text-center text-[13.5px] text-muted">
            Examples. Yours are based on your company and its competitors, with sources. Connect your tools and your AI employees measure the rest for real.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl space-y-24 px-5">
          <Title kicker="How it works" title="Then they work. Every day." sub="You stay in charge without doing the work." />
          <Step n="1" title="Your website in, your AI team out" text="We read your site, show you what you're missing, and set up the right AI employees and goals for each team. Nobody has to figure it out." clip="setup" label="Setup" />
          <Step n="2" title="Connect once" text="Gmail, LinkedIn, HubSpot, GitHub, your database. One click each." clip="connect" label="Connections" flip />
          <Step n="3" title="AI shows its work. You decide." text="Agents prepare everything and show why. A person says yes, edits it, or says no." clip="approve" label="Needs you" />
          <Step n="4" title="They get better every week" text="AI team leads raise targets, cut what isn't working, and suggest new AI employees." clip="lead" label="AI team lead" flip />
        </div>
      </section>

      {/* Results */}
      <section id="results" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="Results" title="What your AI team gets done in week one" />
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Result team="Sales" text="40 qualified leads, each with a personal email ready to send" />
            <Result team="Marketing" text="A month of posts, written in your voice" />
            <Result team="Product" text="Why signups dropped, with the numbers behind it" />
            <Result team="Support" text="Every new ticket answered within the hour" />
            <Result team="Finance" text="Every overdue invoice chased, politely" />
            <Result team="Hiring" text="20 ranked candidates for your open role" />
          </div>
          <p className="mt-10 text-center text-[14px] text-muted">
            Built for B2B startups, agencies, e-commerce brands, expert firms and solo founders.
          </p>
        </div>
      </section>

      {/* Trust */}
      <section className="pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="Humans in charge" title="AI does the work. People make the call." sub="Human accuracy at AI speed." />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Trust icon={<Eye size={18} />} title="Shows its work" text="Every draft, step, source and reason is there to check." />
            <Trust icon={<Hand size={18} />} title="Final yes is yours" text="Sends, posts, payments and merges wait for a person." />
            <Trust icon={<Wallet size={18} />} title="Hard budgets" text="A few dollars a week to start. Never a cent over." />
            <Trust icon={<ShieldCheck size={18} />} title="No passwords" text="Agents never see or type your passwords." />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 pb-20 pt-32">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-[28px] bg-brand-600 px-6 py-20 text-center text-white">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.07)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.07)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_70%)]" />
          <h2 className="display relative mx-auto max-w-3xl text-balance text-[40px] leading-[1.04] sm:text-[60px]">Become AI-native this week.</h2>
          <p className="relative mt-4 text-[17px] text-white/75">No AI training. No prompts. Your team just approves.</p>
          <div className="relative mx-auto mt-9 max-w-[560px]"><WebsiteStart signedIn={signedIn} onDark /></div>
        </div>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 text-[13px] text-muted">
          <Logo small />
          <span>AI speed. Human judgment.</span>
        </div>
      </footer>
    </div>
  );
}

function Logo({ small }: { small?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <BrandMark size={small ? 22 : 28} />
      <span className={cx("font-bold tracking-[-0.02em]", small ? "text-[15px] text-ink" : "text-[18px]")}>Autopilot</span>
    </Link>
  );
}

function Underlined({ children }: { children: ReactNode }) {
  return (
    <span className="relative whitespace-nowrap text-brand-600">
      {children}
      <svg viewBox="0 0 300 20" preserveAspectRatio="none" aria-hidden className="absolute bottom-[-0.06em] left-[2%] h-[0.2em] w-[96%]">
        <path d="M3 15 C 80 4, 200 2, 297 9" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      </svg>
    </span>
  );
}

function Chip({ team }: { team: string }) {
  const [bg, fg] = TEAM[team];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-0.5 pl-2 pr-2.5 text-[12px] font-medium" style={{ background: bg, color: fg }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: fg }} />{team}
    </span>
  );
}

function Avatar({ name, team, size = 24 }: { name: string; team: string; size?: number }) {
  const [bg, fg] = TEAM[team];
  return (
    <span className="inline-grid shrink-0 place-items-center rounded-full font-semibold" style={{ width: size, height: size, background: bg, color: fg, fontSize: size * 0.42 }}>
      {name[0]}
    </span>
  );
}

function Spark({ pts, w = 84, h = 26 }: { pts: number[]; w?: number; h?: number }) {
  const mx = Math.max(...pts), mn = Math.min(...pts);
  const xy = pts.map((p, i) => [(i * w) / (pts.length - 1), h - 2 - ((p - mn) / (mx - mn || 1)) * (h - 6)]);
  const line = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="text-brand-600" aria-hidden>
      <polygon points={`0,${h} ${line} ${w},${h}`} fill="currentColor" opacity="0.1" />
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx - 1} cy={ly} r="2.6" fill="currentColor" />
    </svg>
  );
}

const ROWS: [string, string, string, string, number, number[], boolean][] = [
  ["Book meetings with ideal customers", "Sales", "Outbound Agent", "3 of 4 this week", 75, [2, 3, 2, 4, 3, 5, 6], true],
  ["Grow newsletter signups", "Marketing", "Content Agent", "46 of 40 this week", 100, [3, 4, 4, 6, 5, 8, 9], true],
  ["Ship weekly product updates", "Product", "PM Agent", "2 of 3 this week", 66, [2, 2, 3, 2, 3, 3, 4], true],
  ["Answer every ticket within 2 hours", "Support", "Support Agent", "91% this week", 91, [6, 5, 7, 6, 8, 7, 9], true],
  ["Close the books by the 5th", "Finance", "Books Agent", "Day 3 of 5", 60, [1, 2, 2, 3, 3, 4, 4], false],
];

/** A still of the product: goals by team, plus an approval and a team lead suggestion floating over it. */
function ProductPreview() {
  const side: [typeof Home, string][] = [[Home, "Home"], [Inbox, "Needs you"], [Users, "Team"], [Target, "Goals"], [Activity, "Work log"], [Plug, "Connections"]];
  return (
    <div className="relative mx-auto mt-16 max-w-[1160px] px-5" aria-hidden>
      <div className="relative h-[360px] overflow-hidden rounded-[18px] border border-[#e4e7ec] bg-white shadow-[0_0_0_8px_rgba(255,255,255,0.7),0_0_0_9px_#eef0f3,0_50px_100px_-40px_rgba(16,24,40,0.35)] sm:h-[470px]">
        <div className="flex h-10 items-center gap-[7px] border-b border-[#f2f4f7] bg-[#fcfcfd] px-4">
          <i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" />
          <span className="mx-auto -translate-x-6 rounded-md bg-[#f2f4f7] px-3.5 py-1 text-[12px] text-stone-400">app.autopilot.ai/goals</span>
        </div>
        <div className="grid h-full grid-cols-1 md:grid-cols-[190px_1fr]">
          <div className="hidden border-r border-[#f2f4f7] bg-[#fcfcfd] px-2.5 py-4 md:block">
            {side.map(([Icon, label]) => (
              <div key={label} className={cx("mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] font-medium",
                label === "Goals" ? "bg-brand-50 text-brand-700" : "text-stone-600")}>
                <Icon size={15} className={label === "Goals" ? "text-brand-600" : ""} />{label}
                {label === "Needs you" && <span className="ml-auto rounded-full bg-brand-600 px-1.5 text-[11px] font-semibold text-white">3</span>}
              </div>
            ))}
          </div>
          <div className="min-w-0 px-4 py-5 text-left sm:px-6">
            <div className="mb-4 flex items-end justify-between">
              <div>
                <div className="text-[20px] font-semibold tracking-[-0.02em]">Goals</div>
                <div className="mt-0.5 text-[13px] text-muted">9 of 10 on track this week</div>
              </div>
              <div className="hidden rounded-[9px] bg-[#f2f4f7] p-[3px] text-[12.5px] font-medium text-muted sm:flex">
                <span className="rounded-[7px] bg-white px-2.5 py-1 text-ink shadow-[0_1px_2px_rgba(16,24,40,0.08)]">This week</span>
                <span className="px-2.5 py-1">Month</span><span className="px-2.5 py-1">Quarter</span>
              </div>
            </div>
            <div className="grid grid-cols-[2fr_1fr] gap-4 border-b border-[#f2f4f7] px-1 pb-2.5 text-[11.5px] font-semibold uppercase tracking-[0.05em] text-stone-400 lg:grid-cols-[2.1fr_1fr_1.5fr_1.4fr_96px_90px]">
              <div>Goal</div><div className="hidden lg:block">Team</div><div className="hidden lg:block">AI employee</div><div>Progress</div>
              <div className="hidden lg:block">Trend</div><div className="hidden lg:block">Status</div>
            </div>
            {ROWS.map(([goal, team, agent, prog, pct, pts, ok]) => (
              <div key={goal} className="grid grid-cols-[2fr_1fr] items-center gap-4 border-b border-[#f2f4f7] px-1 py-3 text-[13.5px] lg:grid-cols-[2.1fr_1fr_1.5fr_1.4fr_96px_90px]">
                <div className="font-medium">{goal}</div>
                <div className="hidden lg:block"><Chip team={team} /></div>
                <div className="hidden items-center gap-2 text-stone-700 lg:flex"><Avatar name={agent} team={team} />{agent}</div>
                <div>
                  <div className="mb-1.5 text-[12px] text-muted">{prog}</div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#f2f4f7]"><div className="h-full rounded-full bg-brand-600" style={{ width: `${pct}%` }} /></div>
                </div>
                <div className="hidden lg:block"><Spark pts={pts} /></div>
                <div className="hidden lg:block">
                  <span className={cx("inline-flex items-center gap-1.5 text-[12.5px] font-medium", ok ? "text-emerald-700" : "text-signal-700")}>
                    <span className={cx("h-[7px] w-[7px] rounded-full", ok ? "bg-emerald-600 ring-[3px] ring-emerald-100" : "bg-signal-500 ring-[3px] ring-signal-100")} />
                    {ok ? "On track" : "Watch"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-white" />
      </div>

      <div className="absolute right-[-64px] top-[136px] hidden w-[312px] rounded-2xl border border-[#e4e7ec] bg-white px-[18px] py-4 text-left shadow-[0_30px_60px_-20px_rgba(16,24,40,0.28),0_2px_6px_rgba(16,24,40,0.05)] xl:block">
        <div className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-[0.05em] text-muted">
          <span className="h-[7px] w-[7px] rounded-full bg-signal-500 ring-[3px] ring-signal-100" />Needs you · Sales
        </div>
        <div className="mb-1.5 mt-2 text-[15px] font-semibold tracking-[-0.01em]">Send 12 intro emails to fleet managers</div>
        <div className="flex items-center gap-2 text-[12.5px] text-muted"><Avatar name="Outbound" team="Sales" size={22} />Outbound Agent · drafted and checked</div>
        <div className="mt-3.5 flex gap-2">
          <span className="inline-flex h-8 items-center rounded-[9px] bg-brand-600 px-3 text-[13px] font-semibold text-white">Approve</span>
          <span className="inline-flex h-8 items-center rounded-[9px] border border-line px-3 text-[13px] font-semibold">Review</span>
        </div>
      </div>
      <div className="absolute left-[-64px] top-[330px] hidden w-[262px] rounded-2xl border border-[#e4e7ec] bg-white px-[18px] py-4 text-left shadow-[0_30px_60px_-20px_rgba(16,24,40,0.28),0_2px_6px_rgba(16,24,40,0.05)] xl:block">
        <div className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.05em] text-brand-700"><Sparkles size={13} />Marketing team lead</div>
        <div className="mb-1.5 mt-2 text-[15px] font-semibold tracking-[-0.01em]">Raise the signup target 40 → 60 a week</div>
        <div className="text-[12.5px] leading-snug text-muted">Beat it 3 weeks in a row. Posts on dispatch overtime are driving it.</div>
      </div>
    </div>
  );
}

/** "yourcompany.com → Build my AI team": the website goes with them into setup. */
function WebsiteStart({ signedIn, onDark }: { signedIn: boolean; onDark?: boolean }) {
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
    <form onSubmit={go} className={cx("flex flex-col gap-1.5 rounded-2xl border bg-white p-1.5 sm:flex-row sm:items-center",
      onDark ? "border-white/20 shadow-[0_20px_50px_-20px_rgba(0,0,0,0.5)]" : "border-line shadow-[0_1px_2px_rgba(16,24,40,0.05),0_12px_32px_-12px_rgba(16,24,40,0.14)]")}>
      <label className="flex min-w-0 flex-1 items-center px-3 text-left">
        <span className="text-[16px] text-stone-300">https://</span>
        <input value={site} onChange={(e) => setSite(e.target.value)} placeholder="yourcompany.com" aria-label="Your website"
          className="h-11 w-full bg-transparent text-[16px] text-ink outline-none placeholder:text-stone-400" />
      </label>
      <button className={cx("inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl px-5 text-[15px] font-semibold text-white transition",
        onDark ? "bg-ink hover:bg-black" : "bg-brand-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_8px_20px_-8px_rgba(30,64,175,0.8)] hover:bg-brand-700")}>
        Build my AI team <ArrowRight size={16} />
      </button>
    </form>
  );
}

/** A looping product clip in a window frame. Plays like a GIF; only while on screen. */
function Clip({ name, label }: { name: string; label: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) v.play().catch(() => null); else v.pause(); }, { threshold: 0.25 });
    io.observe(v);
    return () => io.disconnect();
  }, []);
  return (
    <div className="overflow-hidden rounded-2xl border border-[#e4e7ec] bg-white text-left shadow-[0_0_0_6px_rgba(255,255,255,0.7),0_0_0_7px_#eef0f3,0_40px_80px_-32px_rgba(16,24,40,0.3)]">
      <div className="flex items-center gap-[7px] border-b border-[#f2f4f7] bg-[#fcfcfd] px-4 py-2.5">
        <i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" />
        <span className="ml-3 truncate text-[12px] text-stone-400">{label}</span>
      </div>
      <video ref={ref} src={`/clips/${name}.mp4`} poster={`/clips/${name}.jpg`} autoPlay muted loop playsInline
        preload="metadata" className="block aspect-[8/5] w-full bg-canvas" aria-label={label} />
    </div>
  );
}

function Title({ kicker, title, sub }: { kicker: string; title: ReactNode; sub?: string }) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <div className="text-[13px] font-semibold uppercase tracking-[0.08em] text-brand-600">{kicker}</div>
      <h2 className="display mt-3 text-balance text-[36px] leading-[1.06] sm:text-[52px]">{title}</h2>
      {sub && <p className="mt-4 text-[17px] text-stone-600">{sub}</p>}
    </div>
  );
}

function Step({ n, title, text, clip, label, flip }: { n: string; title: string; text: string; clip: string; label: string; flip?: boolean }) {
  return (
    <div className={cx("grid items-center gap-10", flip ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]" : "lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]")}>
      <div className={flip ? "lg:order-2" : ""}>
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-50 text-[14px] font-bold text-brand-700 ring-1 ring-inset ring-brand-100">{n}</span>
        <h3 className="display mt-4 text-[30px] leading-[1.1] sm:text-[36px]">{title}</h3>
        <p className="mt-3 max-w-sm text-[17px] leading-relaxed text-stone-600">{text}</p>
      </div>
      <div className={flip ? "lg:order-1" : ""}><Clip name={clip} label={label} /></div>
    </div>
  );
}

function Missing({ team, title, evidence, estimate, steps, fix, agent }: {
  team: string; title: string; evidence: string; estimate?: string; steps?: [string, string][]; fix: string; agent: string;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-line bg-white p-6 text-left shadow-[var(--shadow-card)]">
      <div><Chip team={team} /></div>
      <p className="mt-4 text-[18px] font-semibold leading-snug tracking-[-0.02em]">{title}</p>
      <p className="mt-2 text-[14px] leading-relaxed text-stone-600">{evidence}</p>
      {estimate && <p className="mt-3 rounded-lg bg-brand-50 px-3 py-1.5 text-[13.5px] font-semibold text-brand-700 ring-1 ring-inset ring-brand-100">{estimate}</p>}
      {steps && (
        <ul className="mt-3 space-y-1 rounded-lg bg-brand-50 px-3 py-2 text-[13px] ring-1 ring-inset ring-brand-100">
          {steps.map(([what, cost]) => (
            <li key={what} className="flex justify-between gap-3"><span className="text-brand-700">{what}</span><b className="font-semibold text-brand-700">{cost}</b></li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex items-center gap-2 border-t border-line pt-4 text-[13px]">
        <Avatar name={agent} team={team} size={22} />
        <span className="min-w-0 flex-1 truncate"><span className="text-muted">{agent}:</span> <b className="font-semibold">{fix}</b></span>
        <span className="rounded-md bg-brand-600 px-2 py-1 text-[12px] font-semibold text-white">Turn on</span>
      </div>
    </div>
  );
}

function Result({ team, text }: { team: string; text: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-6 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pop)]">
      <Chip team={team} />
      <p className="mt-4 text-[20px] font-semibold leading-[1.3] tracking-[-0.02em]">{text}</p>
    </div>
  );
}

function Trust({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-line bg-canvas p-6">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-white text-brand-600 shadow-[0_1px_2px_rgba(16,24,40,0.06)] ring-1 ring-inset ring-line">{icon}</span>
      <div className="mt-4 text-[17px] font-semibold tracking-[-0.01em]">{title}</div>
      <p className="mt-1 text-[15px] leading-relaxed text-stone-600">{text}</p>
    </div>
  );
}
