"use client";

import {
  ArrowRight,
  Ban,
  Building2,
  CheckCircle2,
  Flag,
  Globe,
  Hand,
  ListChecks,
  MessageCircle,
  Rocket,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  ThumbsUp,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { CATEGORY_ICON } from "@/components/UseCaseLibrary";
import { CATEGORIES, USE_CASES } from "@/lib/useCases";

const SHOWCASE = ["sales", "research", "fundraising", "marketing", "product", "agency"];

export default function Landing() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => setSignedIn(r.ok)).catch(() => null);
  }, []);

  return (
    <div className="min-h-screen bg-white text-ink">
      {/* Nav */}
      <header className="sticky top-0 z-30 border-b border-line/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <EmployeeAvatar size={30} />
            <span className="text-[17px] font-bold tracking-tight">Autopilot</span>
          </Link>
          <nav className="hidden gap-6 text-sm font-medium text-gray-600 md:flex">
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href="#what" className="hover:text-ink">What it can do</a>
            <a href="#control" className="hover:text-ink">You stay in control</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {signedIn ? (
              <Link href="/home" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
                Open dashboard <ArrowRight size={15} />
              </Link>
            ) : (
              <>
                <Link href="/login" className="hidden h-9 items-center rounded-lg px-3 text-sm font-semibold text-gray-700 hover:bg-gray-100 sm:inline-flex">Log in</Link>
                <Link href="/signup" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-black">
                  Get started <ArrowRight size={15} />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(60%_60%_at_70%_0%,rgba(99,102,241,0.14),transparent),radial-gradient(50%_50%_at_10%_10%,rgba(37,99,235,0.10),transparent)]" />
        <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-5 pb-20 pt-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:pt-24">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1 text-xs font-semibold text-gray-600">
              <Sparkles size={13} className="text-violet-500" /> An AI employee for founders and agencies
            </span>
            <h1 className="mt-5 text-[38px] font-bold leading-[1.06] tracking-tight sm:text-[50px] xl:text-[54px]">
              <span className="block text-balance">Set a goal and a budget.</span>
              <span className="block bg-gradient-to-r from-brand-600 to-violet-600 bg-clip-text text-transparent">Autopilot gets it done.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-gray-600">
              Tell it what you want, like 20 qualified meetings, 500 waitlist signups or 150 investors who fund your stage, and what it may spend.
              Then get back to building. It plans, does the work, checks with you on what matters, and shows you every step.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href={signedIn ? "/goals/new" : "/signup"} className="inline-flex h-12 items-center gap-2 rounded-xl bg-brand-500 px-6 text-[15px] font-semibold text-white shadow-lg shadow-brand-500/25 hover:bg-brand-600">
                Give it your first goal <ArrowRight size={17} />
              </Link>
              <a href="#what" className="inline-flex h-12 items-center rounded-xl px-5 text-[15px] font-semibold text-gray-700 hover:bg-gray-100">
                See what it can do
              </a>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600">
              <li className="flex items-center gap-1.5"><Wallet size={15} className="text-emerald-600" /> Never spends past your budget</li>
              <li className="flex items-center gap-1.5"><Hand size={15} className="text-emerald-600" /> Asks before anything important</li>
              <li className="flex items-center gap-1.5"><ListChecks size={15} className="text-emerald-600" /> Logs every step</li>
            </ul>
          </div>
          <HeroPreview />
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-t border-line bg-canvas/60 py-20">
        <div className="mx-auto max-w-6xl px-5">
          <SectionTitle eyebrow="How it works" title="Like hiring someone great, minus the hiring" />
          <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
            <Step n={1} icon={<Flag size={20} />} title="Set the goal and the finish line">
              Pick from 200+ ready-made goals or write your own. Say exactly when a result counts, e.g. &quot;meeting held on the calendar with a
              matching attendee&quot;.
            </Step>
            <Step n={2} icon={<Wallet size={20} />} title="Set the budget and the rules">
              A hard spending limit, a check-in rhythm, and what it may never do, must ask about first, or can just do.
            </Step>
            <Step n={3} icon={<Rocket size={20} />} title="Forget about it">
              Autopilot works in sessions on its own: it plans, researches, reaches out and follows up. It only pings you when it needs a yes, and
              you can check progress any time.
            </Step>
          </div>
        </div>
      </section>

      {/* What it can do */}
      <section id="what" className="scroll-mt-20 py-20">
        <div className="mx-auto max-w-6xl px-5">
          <SectionTitle
            eyebrow="What it can do"
            title={`${USE_CASES.length} goals across ${CATEGORIES.length} areas of your business`}
            sub="It works best on goals with a countable finish line: meetings, signups, replies, listings, applications, money recovered."
          />
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {SHOWCASE.map((key) => {
              const cat = CATEGORIES.find((c) => c.key === key)!;
              const examples = cat.rows.filter((r) => r[3] === "H").slice(0, 3);
              return (
                <div key={key} className="rounded-2xl border border-line bg-white p-5 transition hover:shadow-md">
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 text-brand-600">{CATEGORY_ICON[key]}</span>
                    <h3 className="text-[15px] font-bold">{cat.name}</h3>
                  </div>
                  <ul className="mt-4 space-y-2.5">
                    {examples.map((r) => (
                      <li key={r[1]} className="flex items-start gap-2 text-[13.5px] leading-snug text-gray-700">
                        <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" /> {r[1]}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {CATEGORIES.filter((c) => !SHOWCASE.includes(c.key)).map((c) => (
              <span key={c.key} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-xs font-medium text-gray-600">
                <span className="text-gray-400">{CATEGORY_ICON[c.key]}</span> {c.name}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Control */}
      <section id="control" className="scroll-mt-20 border-y border-line bg-ink py-20 text-white">
        <div className="mx-auto max-w-6xl px-5">
          <SectionTitle dark eyebrow="You stay in control" title="Autonomous, not unsupervised" sub="Hand over the work without handing over the keys." />
          <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Control icon={<Wallet size={20} />} title="A hard budget">
              Every cost, including its own AI usage, is counted before it&apos;s spent. When the budget runs out, it stops.
            </Control>
            <Control icon={<Hand size={20} />} title="It asks first">
              &quot;I&apos;m going to send this email: can I go ahead?&quot; Approve, edit, decline, or say &quot;don&apos;t ask me next time&quot;.
            </Control>
            <Control icon={<ShieldCheck size={20} />} title="Your rules">
              Switch off whole kinds of action, block apps and sites, or write rules in your own words. They apply instantly.
            </Control>
            <Control icon={<ListChecks size={20} />} title="A full work log">
              Every plan, page visited, message sent, approval and dollar spent, in plain language.
            </Control>
          </div>
        </div>
      </section>

      {/* Audiences */}
      <section className="py-20">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-5 px-5 md:grid-cols-2">
          <Audience
            icon={<Rocket size={20} />}
            title="For early-stage founders"
            points={["Book customer interviews and sales meetings", "Build investor lists and book first meetings", "Recruit beta users and get your first paying customers"]}
            text="The growth work you know matters but never gets to, done in the background."
          />
          <Audience
            icon={<Building2 size={20} />}
            title="For agency owners"
            points={["Run lead gen, outreach and placements for every client", "Track spend and results per client", "Take on more clients without hiring"]}
            text="The same goal across many clients, each with its own budget and work log."
          />
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 pb-20">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 to-violet-600 px-8 py-14 text-center text-white">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_0%,rgba(255,255,255,0.2),transparent_40%)]" />
          <div className="relative">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">What would you hand off today?</h2>
            <p className="mx-auto mt-3 max-w-xl text-white/85">Pick a goal, set a budget, and see the first work session&apos;s plan in minutes.</p>
            <Link href={signedIn ? "/goals/new" : "/signup"} className="mt-7 inline-flex h-12 items-center gap-2 rounded-xl bg-white px-6 text-[15px] font-semibold text-brand-700 hover:bg-white/90">
              Get started <ArrowRight size={17} />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-5 text-sm text-muted">
          <span className="flex items-center gap-2 font-semibold text-ink"><EmployeeAvatar size={22} /> Autopilot</span>
          <span>Set a goal and a budget. It gets it done.</span>
          <span className="ml-auto flex gap-4">
            <Link href="/login" className="hover:text-ink">Log in</Link>
            <Link href="/signup" className="hover:text-ink">Sign up</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}

function SectionTitle({ eyebrow, title, sub, dark }: { eyebrow: string; title: string; sub?: string; dark?: boolean }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className={dark ? "text-sm font-semibold uppercase tracking-widest text-violet-300" : "text-sm font-semibold uppercase tracking-widest text-brand-600"}>{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h2>
      {sub && <p className={dark ? "mt-3 text-white/70" : "mt-3 text-gray-600"}>{sub}</p>}
    </div>
  );
}

function Step({ n, icon, title, children }: { n: number; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-6">
      <div className="flex items-center justify-between">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600">{icon}</span>
        <span className="text-4xl font-bold text-gray-100">{n}</span>
      </div>
      <h3 className="mt-4 text-lg font-bold">{title}</h3>
      <p className="mt-2 text-[14px] leading-relaxed text-gray-600">{children}</p>
    </div>
  );
}

function Control({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
      <span className="text-violet-300">{icon}</span>
      <h3 className="mt-3 font-bold">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-white/70">{children}</p>
    </div>
  );
}

function Audience({ icon, title, text, points }: { icon: ReactNode; title: string; text: string; points: string[] }) {
  return (
    <div className="rounded-2xl border border-line p-7">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-50 text-violet-600">{icon}</span>
      <h3 className="mt-4 text-xl font-bold">{title}</h3>
      <p className="mt-1.5 text-gray-600">{text}</p>
      <ul className="mt-4 space-y-2">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2 text-[14px] text-gray-700"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" /> {p}</li>
        ))}
      </ul>
    </div>
  );
}

/** An illustrative product preview: a goal with progress, spend and a live work log. */
function HeroPreview() {
  const log: { icon: ReactNode; tone: string; text: string; meta: string }[] = [
    { icon: <ListChecks size={14} />, tone: "bg-violet-50 text-violet-600", text: "Planned today's session: follow up with 8 warm replies, then contact 12 new prospects", meta: "Plan" },
    { icon: <Search size={14} />, tone: "bg-gray-100 text-gray-500", text: "Found 12 logistics companies that just hired a head of marketing", meta: "Research" },
    { icon: <ThumbsUp size={14} />, tone: "bg-emerald-50 text-emerald-600", text: "Sent a follow-up to the head of marketing at a freight startup (you approved)", meta: "Did" },
    { icon: <Ban size={14} />, tone: "bg-red-50 text-red-600", text: "Skipped a contact who is already a customer (your rule)", meta: "Blocked" },
    { icon: <CheckCircle2 size={14} />, tone: "bg-emerald-50 text-emerald-600", text: "Meeting booked for Thursday, 3:00 PM", meta: "Result" },
  ];
  return (
    <div className="relative">
      <div className="absolute -inset-4 rounded-[28px] bg-gradient-to-br from-brand-500/15 to-violet-500/15 blur-2xl" />
      <div className="relative overflow-hidden rounded-2xl border border-line bg-white shadow-2xl shadow-brand-900/10">
        <div className="flex items-center gap-1.5 border-b border-line bg-gray-50 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-300" /><span className="h-2.5 w-2.5 rounded-full bg-amber-300" /><span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
          <span className="ml-3 text-xs text-muted">Autopilot · Goal</span>
        </div>
        <div className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted"><Target size={12} /> Sales · Cold outbound</div>
              <div className="mt-1 text-[17px] font-bold leading-snug">Book 20 meetings with heads of marketing</div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" /> Working now
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-gray-50 p-3">
              <div className="text-[11px] font-semibold text-muted">Progress</div>
              <div className="mt-0.5 text-xl font-bold">12 <span className="text-sm font-semibold text-muted">/ 20 meetings</span></div>
              <div className="mt-2 h-1.5 rounded-full bg-gray-200"><div className="h-full w-[60%] rounded-full bg-brand-500" /></div>
            </div>
            <div className="rounded-xl bg-gray-50 p-3">
              <div className="text-[11px] font-semibold text-muted">Spent</div>
              <div className="mt-0.5 text-xl font-bold">$18.40 <span className="text-sm font-semibold text-muted">/ $40</span></div>
              <div className="mt-2 h-1.5 rounded-full bg-gray-200"><div className="h-full w-[46%] rounded-full bg-gray-500" /></div>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-brand-50/70 px-3 py-2 text-[13px] text-brand-700">
            <MessageCircle size={14} className="shrink-0" />
            <span className="truncate">Checking which subject lines got the most replies this week…</span>
          </div>
          <ul className="mt-3 space-y-2.5">
            {log.map((l) => (
              <li key={l.text} className="flex items-start gap-2.5">
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${l.tone}`}>{l.icon}</span>
                <span className="min-w-0">
                  <span className="block text-[10.5px] font-semibold uppercase tracking-wide text-muted">{l.meta}</span>
                  <span className="block text-[13px] leading-snug text-gray-800">{l.text}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
            <span className="flex min-w-0 items-center gap-2 text-[13px]"><Hand size={15} className="shrink-0 text-amber-600" /><span className="truncate">Send a first email to 12 new prospects?</span></span>
            <span className="shrink-0 rounded-md bg-brand-500 px-2.5 py-1 text-xs font-semibold text-white">Approve</span>
          </div>
        </div>
      </div>
      <div className="absolute -bottom-5 -left-4 hidden items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-xs font-semibold shadow-lg sm:flex">
        <Globe size={14} className="text-brand-600" /> Uses your apps and browser, with your OK
      </div>
    </div>
  );
}
