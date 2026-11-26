"use client";

import { ArrowLeft, ArrowRight, Check, Globe, Mail, Terminal } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CSSProperties, FormEvent, useEffect, useRef, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useLiteMotion, useStory } from "@/lib/motion";
import { cx } from "@/components/ui";

const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });

/** A short delay for content that rises in one after another. */
const delay = (ms: number): CSSProperties => ({ animationDelay: `${ms}ms` });

/** Only allow redirects back into the app, never to another site. */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/home";
}

type Step = "email" | "code" | "name";
type Options = { google: boolean; email_delivery: "email" | "console" };

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [options, setOptions] = useState<Options | null>(null);
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [delivery, setDelivery] = useState<"email" | "console">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(params.get("error"));
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Already signed in? Go straight to the app.
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => r.ok && router.replace(next));
    fetch("/api/auth/options", { cache: "no-store" }).then((r) => r.json()).then(setOptions).catch(() => setOptions({ google: false, email_delivery: "email" }));
  }, [router, next]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function sendCode(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ delivery: "email" | "console" }>("/api/auth/email/start", { method: "POST", json: { email } });
      setDelivery(r.delivery);
      setStep("code");
      setCode("");
      setCooldown(30);
      setTimeout(() => codeRef.current?.focus(), 50);
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg.includes("pattern") ? "Enter a valid email address." : msg);
    } finally {
      setBusy(false);
    }
  }

  async function verify(value = code) {
    if (value.length !== 6 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const user = await api<{ name: string; new: boolean }>("/api/auth/email/verify", { method: "POST", json: { email, code: value } });
      if (!user.name) {
        setStep("name");
        setBusy(false);
      } else {
        router.replace(next);
      }
    } catch (err) {
      setError((err as Error).message);
      setCode("");
      setBusy(false);
      codeRef.current?.focus();
    }
  }

  async function saveName(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (name.trim()) await api("/api/auth/me", { method: "PATCH", json: { name } });
    } finally {
      router.replace(next);
    }
  }

  const signup = mode === "signup";
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative flex flex-col overflow-hidden px-6 py-8 sm:px-12">
        <div aria-hidden className="pointer-events-none absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-[radial-gradient(closest-side,rgba(140,154,75,0.16),transparent)]" />
        <Link href="/" className="rise relative flex items-center gap-2.5">
          <EmployeeAvatar size={32} />
          <span className="text-[17px] font-bold tracking-tight">Oton</span>
        </Link>

        <div key={step} className="relative mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          {step === "email" && (
            <>
              <h1 className="rise text-[28px] font-bold tracking-[-0.025em]" style={delay(80)}>{signup ? "Create your account" : "Welcome back"}</h1>
              <p className="rise mt-1.5 text-[15px] text-muted" style={delay(160)}>
                {signup ? "No password needed. Set up your first goal in a couple of minutes." : "Sign in to see what Oton has been working on."}
              </p>

              {options?.google && (
                <div className="rise" style={delay(240)}>
                  <a
                    href={`/api/auth/google/start?next=${encodeURIComponent(next)}`}
                    className="mt-6 flex h-11 w-full items-center justify-center gap-3 rounded-lg border border-line bg-white text-sm font-semibold shadow-sm transition hover:bg-stone-50"
                  >
                    <GoogleLogo /> Continue with Google
                  </a>
                  <div className="my-5 flex items-center gap-3 text-xs text-muted">
                    <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
                  </div>
                </div>
              )}

              <form onSubmit={sendCode} className={cx("rise", options?.google ? "space-y-4" : "mt-7 space-y-4")} style={delay(280)}>
                <Field label="Work email">
                  <Input type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
                </Field>
                {error && <ErrorNote>{error}</ErrorNote>}
                <Button variant="primary" className="h-11 w-full" disabled={busy || !email}>
                  <Mail size={15} /> {busy ? "Sending…" : "Email me a sign-in code"}
                </Button>
              </form>
              <p className="rise mt-6 text-center text-sm text-muted" style={delay(380)}>
                {signup ? "Already have an account?" : "New to Oton?"}{" "}
                <Link href={`/${signup ? "login" : "signup"}${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-semibold text-brand-600 hover:underline">
                  {signup ? "Sign in" : "Create an account"}
                </Link>
              </p>
            </>
          )}

          {step === "code" && (
            <>
              <button onClick={() => { setStep("email"); setError(null); }} className="rise mb-6 flex items-center gap-1 self-start text-sm text-muted hover:text-ink">
                <ArrowLeft size={15} /> Use a different email
              </button>
              <h1 className="rise text-[28px] font-bold tracking-[-0.025em]" style={delay(60)}>Check your email</h1>
              {delivery === "email" ? (
                <p className="mt-1 text-sm text-muted">
                  We sent a 6-digit code to <b className="text-ink">{email}</b>. It expires in 10 minutes.
                </p>
              ) : (
                <div className="mt-3 flex gap-2.5 rounded-lg border border-signal-200 bg-signal-50 p-3 text-sm text-signal-900">
                  <Terminal size={16} className="mt-0.5 shrink-0" />
                  <span>
                    Email sending isn&apos;t set up yet, so your code is shown in the <b>terminal where Oton is running</b>. It expires in 10
                    minutes.
                  </span>
                </div>
              )}
              <form onSubmit={(e) => { e.preventDefault(); verify(); }} className="rise mt-6 space-y-4" style={delay(160)}>
                <Field label="Sign-in code">
                  <Input
                    ref={codeRef}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={code}
                    onChange={(e) => {
                      const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                      setCode(v);
                      if (v.length === 6) verify(v);
                    }}
                    placeholder="123456"
                    className="h-12 text-center font-mono text-2xl tracking-[0.5em]"
                  />
                </Field>
                {error && <ErrorNote>{error}</ErrorNote>}
                <Button variant="primary" className="h-11 w-full" disabled={busy || code.length !== 6}>
                  {busy ? "Checking…" : "Sign in"} {!busy && <ArrowRight size={15} />}
                </Button>
              </form>
              <p className="mt-5 text-center text-sm text-muted">
                Didn&apos;t get it? Check spam, or{" "}
                <button disabled={cooldown > 0 || busy} onClick={() => sendCode()} className="font-semibold text-brand-600 hover:underline disabled:text-muted disabled:no-underline">
                  {cooldown > 0 ? `send a new code in ${cooldown}s` : "send a new code"}
                </button>
              </p>
            </>
          )}

          {step === "name" && (
            <>
              <h1 className="rise text-[28px] font-bold tracking-[-0.025em]">Welcome to Oton</h1>
              <p className="rise mt-1.5 text-[15px] text-muted" style={delay(80)}>One last thing: what should we call you?</p>
              <form onSubmit={saveName} className="rise mt-6 space-y-4" style={delay(160)}>
                <Field label="Your name">
                  <Input autoFocus autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Asha Rao" />
                </Field>
                <Button variant="primary" className="h-11 w-full" disabled={busy}>
                  Continue <ArrowRight size={15} />
                </Button>
              </form>
            </>
          )}
        </div>
      </div>

      <AuthShowcase signup={signup} />
    </div>
  );
}

/** The right half: the homepage's aurora, one line on what Oton does, and a scan playing out on a website. */
function AuthShowcase({ signup }: { signup: boolean }) {
  const lite = useLiteMotion();
  return (
    <div className="relative hidden overflow-hidden bg-ink lg:block">
      <div aria-hidden className="absolute inset-0">
        {lite
          ? <div className="h-full w-full bg-[radial-gradient(70%_40%_at_50%_55%,rgba(16,185,129,0.4),transparent)]" />
          : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={1} bandHeight={0.45} />}
        <div className="absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_30%,rgba(0,0,0,0.45),transparent)]" />
      </div>
      <div className="relative flex h-full flex-col justify-center px-14 py-16 text-white">
        <p className="rise text-[13px] font-semibold uppercase tracking-[0.12em] text-lime-300/90" style={delay(200)}>
          {signup ? "Your first scan" : "Welcome back"}
        </p>
        <h2 className="rise mt-3 max-w-md text-[44px] font-bold leading-[1.04] tracking-[-0.035em]" style={delay(300)}>
          {signup ? <>See what you&apos;re <span className="text-lime-300">missing</span>, in minutes.</> : <>Your gaps, and the goals <span className="text-lime-300">closing</span> them.</>}
        </h2>
        <p className="rise mt-4 max-w-md text-[16px] leading-relaxed text-white/70" style={delay(400)}>
          {signup
            ? "Next, enter your website. We check you against your competitors and show the few gaps worth fixing."
            : "Pick up where you left off. Nothing goes out without a person saying yes."}
        </p>
        <div className="rise mt-10" style={delay(550)}><ScanStory /></div>
      </div>
    </div>
  );
}

const SCAN: [string, string, string][] = [
  ["Google", "#6 for your main search", "text-rose-300"],
  ["AI assistants", "Not mentioned", "text-rose-300"],
  ["Reviews", "12 vs 240", "text-amber-300"],
  ["Your website", "6.8s to load", "text-amber-300"],
];

/** A website being checked: each check runs, then shows what it found; then the gaps, then it starts over. */
function ScanStory() {
  const [ref, step] = useStory([500, 1200, 1900, 2600, 3300], 4500);
  const done = step >= SCAN.length;
  return (
    <div ref={ref} className="w-[400px] max-w-full rounded-2xl bg-white/[0.07] p-5 ring-1 ring-inset ring-white/15 backdrop-blur-md">
      <div className="flex items-center justify-between text-[13px]">
        <span className="flex items-center gap-2 text-white/80"><Globe size={14} />yourcompany.com</span>
        <span className={cx("flex items-center gap-1.5 font-medium transition-colors duration-300", done ? "text-lime-300" : "text-white/50")}>
          {done ? <><Check size={13} strokeWidth={3} />Checked</> : <><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-lime-300" />Checking</>}
        </span>
      </div>
      <div className="mt-4 space-y-1">
        {SCAN.map(([check, found, tone], i) => {
          const finished = step > i, running = step === i;
          return (
            <div key={check} className="flex items-center gap-3 rounded-lg px-2 py-2 text-[14px]">
              <span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full transition-colors duration-300",
                finished ? "bg-lime-300 text-ink" : "ring-1 ring-inset ring-white/25")}>
                {finished ? <Check size={11} strokeWidth={3.5} /> : running ? <span className="h-1.5 w-1.5 animate-ping rounded-full bg-lime-300" /> : null}
              </span>
              <span className={cx("flex-1 transition-colors duration-300", finished || running ? "text-white" : "text-white/45")}>{check}</span>
              <span className={cx("font-semibold transition-all duration-500", tone, finished ? "translate-x-0 opacity-100" : "translate-x-2 opacity-0")}>{found}</span>
            </div>
          );
        })}
      </div>
      <div className={cx("mt-3 flex items-center justify-between rounded-xl bg-lime-300 px-4 py-3 text-ink transition-all duration-500 ease-out",
        step >= SCAN.length + 1 ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0")}>
        <span className="text-[15px] font-semibold">4 gaps worth fixing</span>
        <span className="flex items-center gap-1 text-[13px] font-semibold">First fix from $30 <ArrowRight size={14} /></span>
      </div>
    </div>
  );
}

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
