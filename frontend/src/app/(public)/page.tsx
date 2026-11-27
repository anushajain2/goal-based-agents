"use client";

import { ArrowRight, Check, ChevronDown, Eye, Gauge, Globe, Hand, MessageSquare, Plug, Search, ShieldCheck, Sparkles, Star, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { FormEvent, PointerEvent, ReactNode, useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/Shell";
import PixelCard from "@/components/reactbits/PixelCard";
import { useInView, useLiteMotion, useStory } from "@/lib/motion";
import { cx } from "@/components/ui";

// The moving backgrounds are WebGL: loaded in the browser only, after the page itself.
const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });
const PixelBlast = dynamic(() => import("@/components/reactbits/PixelBlast"), { ssr: false });

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
  const lite = useLiteMotion();
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-5 py-3.5">
          <Logo />
          <nav className="hidden gap-7 text-[14.5px] font-medium text-stone-600 md:flex">
            <a href="#checks" className="hover:text-ink">What we check</a>
            <a href="#why" className="hover:text-ink">Why Oton</a>
            <a href="#how" className="hover:text-ink">How it works</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!signedIn && <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-[14.5px] font-semibold text-stone-700 hover:bg-stone-100 sm:inline-flex">Log in</Link>}
            <Link href={signedIn ? "/home" : "/signup"} className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
              {signedIn ? "Open dashboard" : "Check my site"}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative">
        {/* The first screen is only the hero: headline, the aurora, the website box. The example scan waits below. */}
        <div className="relative flex min-h-[calc(100svh-65px)] flex-col">
        <HeroBackdrop lite={lite} />
        <div className="relative mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center px-5 py-14 text-center">
          <a href="#checks" className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 py-1 pl-1 pr-3 text-[13.5px] font-medium text-white/85 backdrop-blur hover:border-white/30">
            <span className="rounded-full bg-white px-2.5 py-0.5 text-[12px] font-semibold text-ink">New</span>
            See if ChatGPT recommends you, or your competitors <ArrowRight size={13} />
          </a>
          <h1 className="display mx-auto mt-7 max-w-5xl text-balance text-[44px] leading-[1.02] tracking-[-0.05em] text-white sm:text-[64px] lg:text-[80px]">
            What are your competitors
            <br />
            doing that you <Underlined className="text-lime-300">aren&apos;t?</Underlined>
          </h1>
          <div className="mx-auto mt-24 w-full max-w-[560px] sm:mt-32 [@media(max-height:760px)]:mt-20"><WebsiteStart signedIn={signedIn} onDark /></div>
          <div className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13.5px] text-white/70">
            {["Just your website", "Compared with your competitors", "Sources for every finding"].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check size={14} strokeWidth={2.5} className="text-lime-300" />{t}</span>
            ))}
          </div>
        </div>
        <a href="#example" className="relative mx-auto mb-6 flex flex-col items-center gap-1 text-[12.5px] font-medium text-white/45 transition hover:text-white/80">
          See an example scan <ChevronDown size={16} className="animate-bounce" />
        </a>
        </div>
        <div id="example" className="relative scroll-mt-16 pt-16">
          <div aria-hidden className="absolute inset-x-0 top-0 h-[320px] bg-ink" />
          <ScanPreview />
        </div>
      </section>

      {/* What we check */}
      <section id="checks" className="scroll-mt-20 pt-28">
        <div className="mx-auto max-w-5xl px-5">
          <Title kicker="What we check" title="We look at you the way your customers do." />
          <div className="mt-12 grid gap-5 md:grid-cols-2">
            <Tile icon={<Search size={17} />} title="Google" text="Where you rank for what buyers search."><SerpMock /></Tile>
            <Tile icon={<MessageSquare size={17} />} title="AI assistants" text="Whether ChatGPT and others recommend you."><ChatMock /></Tile>
            <Tile icon={<Star size={17} />} title="Reviews" text="How you compare where buyers read them.">
              <Bars rows={[["Routeco", 100, <><CountUp to={240} /> reviews</>], ["OptiDrive", 75, <><CountUp to={180} /> reviews</>], ["You", 5, <><CountUp to={12} /> reviews</>, true]]} />
            </Tile>
            <Tile icon={<Gauge size={17} />} title="Your website" text="How fast it loads on a phone.">
              <Bars rows={[["Routeco", 31, <><CountUp to={2.1} decimals={1} />s</>], ["Fleetbase", 50, <><CountUp to={3.4} decimals={1} />s</>], ["You", 100, <><CountUp to={6.8} decimals={1} />s</>, true]]} />
            </Tile>
          </div>
          <p className="mx-auto mt-8 flex max-w-2xl items-center justify-center gap-2 text-center text-[14.5px] text-muted">
            <Plug size={15} className="shrink-0 text-brand-600" />Connect your tools and we find gaps inside them too.
          </p>
        </div>
      </section>

      {/* Example gaps */}
      <section id="gaps" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="What you get" title="The gaps, the proof, and what fixing them takes."
            sub="Not a long list of everything that could be better. The few things worth fixing now, ranked, each with the evidence and a first step you can start today." />
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            <Missing team="Marketing" title="Competitors own the searches buyers make" evidence="Rank 6 for “route planning software”. Asked the same question, AI assistants recommend three competitors and not you."
              steps={[["Start: page 1 for 3 searches", "$30"], ["Full: top 3 for the main search", "~$1,750"]]} fix="Win the searches" agent="Goal" />
            <Missing team="Support" title="Few reviews where buyers look" evidence="12 G2 reviews at 4.1 stars. Your two main competitors have 180 and 240."
              fix="Collect reviews from happy customers" agent="Goal" />
            <Missing team="Sales" title="Visitors leave before the page loads" evidence="Mobile speed 41/100, 6.8 seconds to load. Your closest competitor loads in 2.1."
              fix="Speed up the pages buyers land on" agent="Goal" />
          </div>
          <p className="mx-auto mt-6 max-w-2xl text-center text-[13.5px] text-muted">
            Examples. Yours are based on your company and its competitors, with sources. If you&apos;re already doing well on something, we say so.
          </p>
        </div>
      </section>

      {/* Why */}
      <section id="why" className="scroll-mt-20 px-3 pt-32 sm:px-5">
        <div className="relative mx-auto max-w-[1240px] overflow-hidden rounded-[32px] bg-ink px-5 py-20 text-white sm:py-24">
          <div className="absolute inset-0 opacity-70 [mask-image:radial-gradient(ellipse_58%_60%_at_50%_48%,transparent_35%,black_85%)]" aria-hidden>
            {lite
              ? <div className="h-full w-full bg-[radial-gradient(rgba(163,176,97,0.45)_1px,transparent_1.6px)] bg-[size:10px_10px] [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)]" />
              : <PixelBlast color="#a3b061" pixelSize={4} patternScale={2.5} edgeFade={0.35} speed={0.35} />}
          </div>
          <div className="pointer-events-none absolute left-1/2 top-[-200px] h-[500px] w-[900px] max-w-full -translate-x-1/2 bg-[radial-gradient(closest-side,rgba(140,154,75,0.32),transparent)]" />
          <div className="relative mx-auto max-w-5xl">
            <div className="text-center">
              <div className="text-[13px] font-semibold text-brand-300">Why Oton</div>
              <h2 className="display mt-3 text-balance text-[38px] leading-[1.04] sm:text-[60px]">
                <span className="text-white/40">Others tell you what&apos;s wrong.</span>
                <br />
                We fix it.
              </h2>
            </div>
            <div className="mt-14 grid gap-4 md:grid-cols-3">
              <Way who="An SEO tool" gives="A score." then="You do the work." />
              <Way who="An agency" gives="A deck." then="You wait and pay." />
              <Way us who="Oton" gives="The fix." then="You just approve it." />
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="How it works" title="You type your website. We do the rest." />
          <ol className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            <HowStep who="you" effort="10 seconds" title="Enter your website" text="That's all we need to start."><TypeMock /></HowStep>
            <HowStep who="us" effort="The research" title="We find your gaps" text="Next to your competitors, ranked by what matters."><ScanMock /></HowStep>
            <HowStep who="you" effort="One click" title="Say yes to a fix" text="Start small, with the price up front."><ApproveMock /></HowStep>
            <HowStep who="us" effort="The work" title="We close the gap" text="And measure it every week, so you see it working."><GrowMock /></HowStep>
          </ol>
          <p className="mt-8 text-center text-[14.5px] text-muted">
            Connect Gmail, HubSpot or Stripe any time to find more and do more. Or don&apos;t: it works either way.
          </p>
        </div>
      </section>

      {/* Results */}
      <section id="results" className="scroll-mt-20 pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="Results" title="What closing the gaps looks like in week one" />
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Result team="Marketing" text="Pages written for the 3 searches competitors were winning" />
            <Result team="Support" text="Review requests sent to your 50 happiest customers" />
            <Result team="Sales" text="40 qualified leads, each with a personal email ready to send" />
            <Result team="Product" text="Why signups dropped, with the numbers behind it" />
            <Result team="Finance" text="Every overdue invoice chased, politely" />
            <Result team="Hiring" text="20 ranked candidates for your open role" />
          </div>
          <p className="mt-10 text-center text-[14px] text-muted">
            Built for B2B startups, agencies, e-commerce brands, local businesses, expert firms and solo founders.
          </p>
        </div>
      </section>

      {/* Trust */}
      <section className="pt-32">
        <div className="mx-auto max-w-6xl px-5">
          <Title kicker="You stay in charge" title="We find it. You decide." sub="Nothing changes without a person saying yes." />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Trust icon={<Eye size={18} />} title="Shows its sources" text="Every finding links to the search, page or measurement behind it." />
            <Trust icon={<Hand size={18} />} title="Final yes is yours" text="Sends, posts, payments and changes wait for a person." />
            <Trust icon={<Wallet size={18} />} title="Hard budgets" text="A few dollars a week to start. Never a cent over." />
            <Trust icon={<ShieldCheck size={18} />} title="No passwords" text="Oton never sees or types your passwords." />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 pb-20 pt-32">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-[28px] bg-brand-600 px-6 py-20 text-center text-white">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.07)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.07)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_70%)]" />
          <h2 className="display relative mx-auto max-w-3xl text-balance text-[40px] leading-[1.04] sm:text-[60px]">See where you stand.</h2>
          <p className="relative mt-4 text-[17px] text-white/75">All it takes is your website.</p>
          <div className="relative mx-auto mt-9 max-w-[560px]"><WebsiteStart signedIn={signedIn} onDark /></div>
        </div>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 text-[13px] text-muted">
          <Logo small />
          <span>See the gaps. Close them.</span>
        </div>
      </footer>
    </div>
  );
}

function Logo({ small }: { small?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <BrandMark size={small ? 22 : 28} />
      <span className={cx("font-bold tracking-[-0.02em]", small ? "text-[15px] text-ink" : "text-[18px]")}>Oton</span>
    </Link>
  );
}

function Underlined({ children, className = "text-brand-600" }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("relative whitespace-nowrap", className)}>
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

type Level = "big" | "gap" | "good";
const LEVEL: Record<Level, [string, string, string]> = {
  big: ["Big gap", "text-rose-700", "bg-rose-500 ring-rose-100"],
  gap: ["Gap", "text-signal-700", "bg-signal-500 ring-signal-100"],
  good: ["Doing well", "text-emerald-700", "bg-emerald-600 ring-emerald-100"],
};

const SCAN: [string, string, string, string, Level][] = [
  ["Google: “route planning software”", "Not in top 5", "Routeco #1", "Ranked by Google, in your market", "big"],
  ["ChatGPT, Perplexity, Gemini", "Not named", "Routeco, OptiDrive", "Asked what they'd recommend", "big"],
  ["Reviews on G2", "12 · 4.1★", "240 · 4.6★", "Where buyers compare", "gap"],
  ["Mobile speed", "41/100 · 6.8s", "88/100 · 2.1s", "Google PageSpeed", "gap"],
  ["Email authentication", "SPF, DKIM, DMARC", "", "Your email lands in inboxes", "good"],
];

/** A still of the scan result: where the company stands next to its competitors, with the biggest gap floating over it. */
function ScanPreview() {
  return (
    <div className="relative mx-auto max-w-[1160px] px-5" aria-hidden>
      <div className="relative overflow-hidden rounded-[18px] border border-[#e4e7ec] bg-white shadow-[0_0_0_8px_rgba(255,255,255,0.7),0_0_0_9px_#eef0f3,0_50px_100px_-40px_rgba(16,24,40,0.35)]">
        <div className="flex h-10 items-center gap-[7px] border-b border-[#f2f4f7] bg-[#fcfcfd] px-4">
          <i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" /><i className="h-2.5 w-2.5 rounded-full bg-[#e4e7ec]" />
          <span className="mx-auto -translate-x-6 rounded-md bg-[#f2f4f7] px-3.5 py-1 text-[12px] text-stone-400">app.oton.ai/gaps</span>
        </div>
        <div className="px-4 pb-8 pt-6 text-left sm:px-8">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[13px] text-muted"><Globe size={14} />fleetwise.com</div>
              <div className="mt-1 text-[22px] font-semibold tracking-[-0.02em]"><CountUp to={5} duration={900} /> gaps worth fixing</div>
              <div className="mt-0.5 text-[13px] text-muted">Checked live, next to Routeco, Fleetbase and OptiDrive</div>
            </div>
            <div className="hidden gap-2 sm:flex xl:hidden">
              <span className="rounded-full bg-rose-50 px-2.5 py-1 text-[12px] font-semibold text-rose-700">2 big</span>
              <span className="rounded-full bg-signal-50 px-2.5 py-1 text-[12px] font-semibold text-signal-700">3 more</span>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[12px] font-semibold text-emerald-700">9 doing well</span>
            </div>
          </div>
          <div className="mt-6 grid grid-cols-[1.6fr_1fr_100px] gap-4 border-b border-[#f2f4f7] px-1 pb-2.5 text-[12px] font-semibold text-stone-400 lg:grid-cols-[2fr_1.1fr_1.2fr_110px]">
            <div>Check</div><div>You</div><div className="hidden lg:block">Best competitor</div><div>Status</div>
          </div>
          {SCAN.map(([check, you, them, how, level]) => {
            const [label, text, dot] = LEVEL[level];
            return (
              <div key={check} className="grid grid-cols-[1.6fr_1fr_100px] items-center gap-4 border-b border-[#f2f4f7] px-1 py-3 text-[13.5px] lg:grid-cols-[2fr_1.1fr_1.2fr_110px]">
                <div className="min-w-0">
                  <div className="truncate font-medium">{check}</div>
                  <div className="truncate text-[12px] text-muted">{how}</div>
                </div>
                <div className={cx("font-medium", text)}>{you}</div>
                <div className="hidden text-stone-600 lg:block">{them}</div>
                <span className={cx("inline-flex items-center gap-1.5 text-[12.5px] font-medium", text)}>
                  <span className={cx("h-[7px] w-[7px] rounded-full ring-[3px]", dot)} />{label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="absolute right-[-64px] top-[-44px] hidden w-[312px] rounded-2xl border border-[#e4e7ec] bg-white px-[18px] py-4 text-left shadow-[0_30px_60px_-20px_rgba(16,24,40,0.28),0_2px_6px_rgba(16,24,40,0.05)] xl:block">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-brand-700"><Sparkles size={13} />Biggest opportunity</div>
        <div className="mb-1.5 mt-2 text-[15px] font-semibold tracking-[-0.01em]">Show up when buyers search for route planning</div>
        <div className="text-[12.5px] leading-snug text-muted">About 590 searches a month go to competitors. First step: page 1 for 3 searches.</div>
        <div className="mt-3.5 flex items-center gap-2">
          <span className="inline-flex h-8 items-center rounded-[9px] bg-brand-600 px-3 text-[13px] font-semibold text-white">Fix this for $30</span>
          <span className="inline-flex h-8 items-center rounded-[9px] border border-line px-3 text-[13px] font-semibold">See sources</span>
        </div>
      </div>
      <div className="absolute bottom-[-88px] left-[-48px] hidden w-[262px] rounded-2xl border border-[#e4e7ec] bg-white px-[18px] py-4 text-left shadow-[0_30px_60px_-20px_rgba(16,24,40,0.28),0_2px_6px_rgba(16,24,40,0.05)] xl:block">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-rose-700"><MessageSquare size={13} />Asked ChatGPT</div>
        <div className="mt-2 text-[13.5px] leading-snug text-stone-700">“Best route planning software for a small fleet?”</div>
        <div className="mt-1.5 text-[12.5px] leading-snug text-muted">Recommends Routeco, OptiDrive and Fleetbase. Not you.</div>
      </div>
    </div>
  );
}

/** One kind of check: a simple picture on top, one line below. */
function Tile({ icon, title, text, children }: { icon: ReactNode; title: string; text: string; children: ReactNode }) {
  return (
    <Tilt>
      <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-line bg-white text-left shadow-[var(--shadow-card)] transition-shadow duration-300 hover:shadow-[var(--shadow-pop)]">
        <div className="flex h-[230px] flex-col justify-center border-b border-line bg-canvas px-7 py-6" aria-hidden>{children}</div>
        <div className="px-7 py-5">
          <div className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.01em]"><span className="text-brand-600">{icon}</span>{title}</div>
          <p className="mt-1 text-[15px] text-stone-600">{text}</p>
        </div>
      </div>
    </Tilt>
  );
}

/** The moving background behind the hero: green northern lights on near-black. It ends behind the scan preview. */
function HeroBackdrop({ lite }: { lite: boolean }) {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden bg-ink">
      {lite
        ? <div className="h-full w-full bg-[radial-gradient(70%_40%_at_50%_45%,rgba(16,185,129,0.45),transparent)]" />
        : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={1.15} bandHeight={0.45} noiseAmplitude={0.7} />}
      {/* Shade behind the headline only, so the aurora band below it stays bright. */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(42%_22%_at_50%_33%,rgba(0,0,0,0.5),transparent)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-ink" />
    </div>
  );
}

/** Tilts a card toward the pointer in 3D, with a soft glare where the pointer is. */
function Tilt({ children, max = 6 }: { children: ReactNode; max?: number }) {
  const lite = useLiteMotion();
  const [t, setT] = useState({ x: 0, y: 0, gx: 50, gy: 50, on: false });
  function move(e: PointerEvent<HTMLDivElement>) {
    if (lite) return;
    const r = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    setT({ x: (0.5 - py) * max * 2, y: (px - 0.5) * max * 2, gx: px * 100, gy: py * 100, on: true });
  }
  return (
    <div className="h-full [perspective:1100px]" onPointerMove={move} onPointerLeave={() => setT((p) => ({ ...p, x: 0, y: 0, on: false }))}>
      <div className="relative h-full transition-transform duration-300 ease-out [transform-style:preserve-3d]"
        style={{ transform: `rotateX(${t.x}deg) rotateY(${t.y}deg) scale(${t.on ? 1.015 : 1})` }}>
        {children}
        <div className="pointer-events-none absolute inset-0 rounded-3xl transition-opacity duration-300" aria-hidden
          style={{ opacity: t.on ? 1 : 0, background: `radial-gradient(circle at ${t.gx}% ${t.gy}%, rgba(255,255,255,0.45), transparent 45%)` }} />
      </div>
    </div>
  );
}

/** Counts from `from` to `to` once it's on screen; people who asked for less motion see the final number. */
function CountUp({ to, from = 0, decimals = 0, duration = 1300 }: { to: number; from?: number; decimals?: number; duration?: number }) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const [v, setV] = useState(from);
  useEffect(() => {
    if (!seen) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setV(to);
    let raf = 0;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      setV(from + (to - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [seen, from, to, duration]);
  return <span ref={ref} className="tabular-nums">{v.toFixed(decimals)}</span>;
}

const QUERY = "route planning software";

/** A buyer's search: the query types itself, competitors fill the top, and you turn up at #6. */
function SerpMock() {
  const [ref, step] = useStory([150, 1300, 1550, 1800, 2200]);
  const row = (n: number, domain: string, show: boolean, you?: boolean) => (
    <div className={cx("flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition-all duration-500 ease-out",
      show ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
      you && (show ? "scale-100 bg-white ring-2 ring-rose-300" : "scale-95"))}>
      <span className={cx("w-4 font-semibold", you ? "text-rose-600" : "text-stone-400")}>{n}</span>
      <span className={cx("flex-1", you ? "font-semibold text-ink" : "text-stone-600")}>{domain}</span>
      {you && <span className={cx("rounded-full bg-rose-50 px-2 py-0.5 text-[12px] font-semibold text-rose-700 transition-transform delay-300 duration-300", show ? "scale-100" : "scale-0")}>You</span>}
    </div>
  );
  return (
    <div ref={ref}>
      <div className="mb-2 flex h-9 items-center gap-2 rounded-full bg-white px-3.5 text-[13.5px] text-stone-700 ring-1 ring-line">
        <Search size={14} className="shrink-0 text-stone-400" />
        <span className="overflow-hidden whitespace-nowrap transition-[max-width] ease-linear"
          style={{ maxWidth: step >= 1 ? "14em" : "0em", transitionDuration: step >= 1 ? "1000ms" : "0ms", transitionTimingFunction: `steps(${QUERY.length})` }}>
          {QUERY}
        </span>
        <span className={cx("-ml-1.5 h-4 w-px bg-stone-500", step >= 2 ? "opacity-0" : "animate-pulse")} />
      </div>
      {row(1, "routeco.com", step >= 2)}
      {row(2, "optidrive.io", step >= 3)}
      <div className={cx("pl-10 text-[12px] leading-3 tracking-[0.3em] text-stone-300 transition-opacity duration-300", step >= 4 ? "opacity-100" : "opacity-0")}>···</div>
      {row(6, "fleetwise.com", step >= 5, true)}
    </div>
  );
}

/** Asking an AI assistant: the question goes in, it thinks, it recommends your competitors, and you're not in it. */
function ChatMock() {
  const [ref, step] = useStory([200, 800, 2100, 2800]);
  return (
    <div ref={ref} className="flex flex-col gap-2.5">
      <div className={cx("ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2 text-[13.5px] leading-snug text-white transition-all duration-500 ease-out",
        step >= 1 ? "translate-x-0 opacity-100" : "translate-x-4 opacity-0")}>
        Best route planning software?
      </div>
      <div className={cx("grid max-w-[85%] transition-all duration-500 ease-out [&>*]:[grid-area:1/1]", step >= 2 ? "translate-x-0 opacity-100" : "-translate-x-4 opacity-0")}>
        <div className={cx("flex h-[38px] w-16 items-center justify-center gap-1 rounded-2xl rounded-bl-md bg-white ring-1 ring-line transition-opacity duration-300", step === 2 ? "opacity-100" : "opacity-0")}>
          {[0, 150, 300].map((d) => <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-stone-400" style={{ animationDelay: `${d}ms` }} />)}
        </div>
        <div className={cx("rounded-2xl rounded-bl-md bg-white px-3.5 py-2.5 text-[13.5px] leading-snug text-stone-700 ring-1 ring-line transition-opacity duration-300", step >= 3 ? "opacity-100" : "opacity-0")}>
          Try <b className="font-semibold text-ink">Routeco</b> or <b className="font-semibold text-ink">OptiDrive</b>.
        </div>
      </div>
      <span className={cx("mt-1 inline-flex items-center gap-1.5 self-start rounded-full bg-rose-50 px-2.5 py-1 text-[12.5px] font-semibold text-rose-700 ring-1 ring-inset ring-rose-200 transition-all duration-300 ease-out",
        step >= 4 ? "scale-100 opacity-100" : "scale-75 opacity-0")}>
        <X size={12} strokeWidth={3} />You&apos;re not mentioned
      </span>
    </div>
  );
}

/** You next to competitors, as bars that grow in when seen. Width is a percentage; "you" is in red. */
function Bars({ rows }: { rows: [string, number, ReactNode, boolean?][] }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className="flex flex-col gap-4">
      {rows.map(([name, pct, value, you], i) => (
        <div key={name}>
          <div className="mb-1.5 flex justify-between text-[13.5px]">
            <span className={cx("font-medium", you ? "text-rose-700" : "text-stone-600")}>{name}</span>
            <span className={cx("font-semibold", you ? "text-rose-700" : "text-stone-700")}>{value}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white ring-1 ring-line">
            <div className={cx("h-full rounded-full transition-[width] duration-1000 ease-out", you ? "bg-rose-500" : "bg-stone-300")}
              style={{ width: seen ? `${Math.max(pct, 3)}%` : "0%", transitionDelay: `${i * 120}ms` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** One way of dealing with gaps, in two words: what you get, and what's left for you. Ours sparkles on hover. */
function Way({ who, gives, then, us }: { who: string; gives: string; then: string; us?: boolean }) {
  const body = (
    <div className="px-7 py-8">
      <div className={cx("flex items-center justify-center gap-2 text-[14px] font-semibold", us ? "text-white/80" : "text-white/45")}>
        {us && <BrandMark size={18} />}{who}
      </div>
      <p className={cx("display mt-3 text-[44px] leading-none", us ? "text-white" : "text-white/70")}>{gives}</p>
      <p className={cx("mt-4 inline-flex items-center gap-2 text-[15px]", us ? "text-white" : "text-white/50")}>
        <span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full", us ? "bg-white text-brand-600" : "bg-white/10 text-white/50")}>
          {us ? <Check size={12} strokeWidth={3} /> : <X size={12} strokeWidth={3} />}
        </span>
        {then}
      </p>
    </div>
  );
  if (!us) return <div className="rounded-3xl bg-[#1d2314] text-center ring-1 ring-inset ring-white/10">{body}</div>;
  return (
    <PixelCard bare noFocus theme="dark" colors={["#ffffff", "#e9ecd5", "#bcc685"]} gap={8} speed={35} opacity={0.55} radius={24}
      className="rounded-3xl bg-brand-600 text-center shadow-[0_30px_80px_-20px_rgba(140,154,75,0.55)] ring-1 ring-white/20">
      {body}
    </PixelCard>
  );
}

/** "yourcompany.com → Show me my gaps": the website goes with them into setup, which ends with the scan. */
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
        onDark ? "bg-ink hover:bg-black" : "bg-brand-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_8px_20px_-8px_rgba(85,107,47,0.7)] hover:bg-brand-700")}>
        Show me my gaps <ArrowRight size={16} />
      </button>
    </form>
  );
}

function Title({ kicker, title, sub }: { kicker: string; title: ReactNode; sub?: string }) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <div className="text-[13px] font-semibold text-brand-600">{kicker}</div>
      <h2 className="display mt-3 text-balance text-[36px] leading-[1.06] sm:text-[52px]">{title}</h2>
      {sub && <p className="mt-4 text-[17px] text-stone-600">{sub}</p>}
    </div>
  );
}

/** A step of "how it works": who does it, how much effort it is, and a small moving picture of it. */
function HowStep({ who, effort, title, text, children }: { who: "you" | "us"; effort: string; title: string; text: string; children: ReactNode }) {
  return (
    <li className="flex flex-col overflow-hidden rounded-3xl border border-line bg-white text-left shadow-[var(--shadow-card)]">
      <div className="flex h-[190px] flex-col justify-center border-b border-line bg-canvas px-5" aria-hidden>{children}</div>
      <div className="px-6 py-5">
        <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold",
          who === "you" ? "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100" : "bg-ink text-white")}>
          {who === "you" ? "You" : <><BrandMark size={13} />Oton</>}<span className="opacity-60">·</span>{effort}
        </span>
        <div className="mt-3 text-[18px] font-semibold tracking-[-0.01em]">{title}</div>
        <p className="mt-1 text-[14.5px] text-stone-600">{text}</p>
      </div>
    </li>
  );
}

/** The website being typed in, once the step is on screen. */
function TypeMock() {
  const [ref, seen] = useInView<HTMLDivElement>();
  const site = "fleetwise.com";
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!seen) return;
    const t = setInterval(() => setN((x) => (x >= site.length ? x : x + 1)), 110);
    return () => clearInterval(t);
  }, [seen]);
  const done = n >= site.length;
  return (
    <div ref={ref} className="space-y-2.5">
      <div className="flex h-10 items-center rounded-xl bg-white px-3 text-[14px] ring-1 ring-line">
        <span className="text-stone-300">https://</span>
        <span className="text-ink">{site.slice(0, n)}</span>
        <span className={cx("ml-px h-4 w-[1.5px] bg-brand-600", done ? "animate-pulse" : "")} />
      </div>
      <div className={cx("flex h-10 items-center justify-center gap-1.5 rounded-xl text-[13.5px] font-semibold text-white transition-colors duration-300",
        done ? "bg-brand-600" : "bg-brand-300")}>
        Show me my gaps <ArrowRight size={14} />
      </div>
    </div>
  );
}

/** The checks ticking off one by one, then the result. */
function ScanMock() {
  const [ref, seen] = useInView<HTMLDivElement>();
  const checks = ["Google", "AI assistants", "Reviews", "Your website"];
  const [done, setDone] = useState(0);
  useEffect(() => {
    if (!seen) return;
    const t = setInterval(() => setDone((x) => (x > checks.length ? x : x + 1)), 550);
    return () => clearInterval(t);
  }, [seen, checks.length]);
  return (
    <div ref={ref} className="space-y-1.5">
      {checks.map((c, i) => (
        <div key={c} className="flex items-center gap-2.5 text-[13.5px]">
          <span className={cx("grid h-[18px] w-[18px] place-items-center rounded-full transition-colors duration-300",
            i < done ? "bg-emerald-500 text-white" : "bg-white ring-1 ring-line")}>
            {i < done ? <Check size={11} strokeWidth={3.5} /> : <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-stone-300" />}
          </span>
          <span className={i < done ? "text-ink" : "text-stone-400"}>{c}</span>
        </div>
      ))}
      <div className={cx("mt-2.5 inline-flex rounded-full bg-rose-50 px-2.5 py-1 text-[12.5px] font-semibold text-rose-700 ring-1 ring-inset ring-rose-200 transition duration-500",
        done > checks.length ? "opacity-100" : "translate-y-1 opacity-0")}>5 gaps found</div>
    </div>
  );
}

/** A fix waiting for a yes, which gets approved once the step is on screen. */
function ApproveMock() {
  const [ref, seen] = useInView<HTMLDivElement>();
  const [ok, setOk] = useState(false);
  useEffect(() => {
    if (!seen) return;
    const t = setTimeout(() => setOk(true), 1600);
    return () => clearTimeout(t);
  }, [seen]);
  return (
    <div ref={ref} className="rounded-2xl bg-white p-4 ring-1 ring-line">
      <div className="text-[13.5px] font-semibold leading-snug">Win 3 searches competitors own</div>
      <div className="mt-0.5 text-[12.5px] text-muted">First step: $30</div>
      <div className={cx("mt-3 flex h-9 items-center justify-center gap-1.5 rounded-[10px] text-[13px] font-semibold transition-colors duration-300",
        ok ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200" : "bg-brand-600 text-white")}>
        {ok ? <><Check size={14} strokeWidth={3} />Approved</> : "Approve"}
      </div>
    </div>
  );
}

/** The gap closing: a rank line that draws itself in. */
function GrowMock() {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref}>
      <div className="flex items-baseline justify-between">
        <span className="text-[12.5px] text-muted">Google rank</span>
        <span className="text-[13.5px] font-semibold"><span className="text-rose-600">#6</span> <span className="text-stone-400">→</span> <span className="text-emerald-600">#<CountUp from={6} to={3} duration={1800} /></span></span>
      </div>
      <svg viewBox="0 0 200 80" className="mt-3 w-full overflow-visible text-emerald-500">
        <path d="M4 70 C 40 66, 60 60, 90 48 S 150 22, 196 10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
          pathLength={1} strokeDasharray="1" strokeDashoffset={seen ? 0 : 1} style={{ transition: "stroke-dashoffset 1.6s ease-out 0.2s" }} />
        <circle cx="196" cy="10" r="5" fill="currentColor" className="transition-opacity duration-300" style={{ opacity: seen ? 1 : 0, transitionDelay: "1.7s" }} />
      </svg>
      <div className="mt-2 flex justify-between text-[12px] text-stone-400"><span>Week 1</span><span>Week 4</span></div>
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
        <Avatar name={team} team={team} size={22} />
        <span className="min-w-0 flex-1 truncate"><span className="text-muted">{agent}:</span> <b className="font-semibold">{fix}</b></span>
        <span className="rounded-md bg-brand-600 px-2 py-1 text-[12px] font-semibold text-white">Fix this</span>
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
