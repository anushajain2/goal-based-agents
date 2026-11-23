"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, Hand, Mail, Send, Terminal, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

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
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Link href="/" className="flex items-center gap-2.5">
          <EmployeeAvatar size={32} />
          <span className="text-[17px] font-bold tracking-tight">Autopilot</span>
        </Link>

        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          {step === "email" && (
            <>
              <h1 className="text-2xl font-bold tracking-tight">{signup ? "Create your account" : "Welcome back"}</h1>
              <p className="mt-1 text-sm text-muted">
                {signup ? "No password needed. Set up your first goal in a couple of minutes." : "Sign in to see what Autopilot has been working on."}
              </p>

              {options?.google && (
                <>
                  <a
                    href={`/api/auth/google/start?next=${encodeURIComponent(next)}`}
                    className="mt-6 flex h-11 w-full items-center justify-center gap-3 rounded-lg border border-line bg-white text-sm font-semibold shadow-sm transition hover:bg-gray-50"
                  >
                    <GoogleLogo /> Continue with Google
                  </a>
                  <div className="my-5 flex items-center gap-3 text-xs text-muted">
                    <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
                  </div>
                </>
              )}

              <form onSubmit={sendCode} className={options?.google ? "space-y-4" : "mt-6 space-y-4"}>
                <Field label="Work email">
                  <Input type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
                </Field>
                {error && <ErrorNote>{error}</ErrorNote>}
                <Button variant="primary" className="h-11 w-full" disabled={busy || !email}>
                  <Mail size={15} /> {busy ? "Sending…" : "Email me a sign-in code"}
                </Button>
              </form>
              <p className="mt-6 text-center text-sm text-muted">
                {signup ? "Already have an account?" : "New to Autopilot?"}{" "}
                <Link href={`/${signup ? "login" : "signup"}${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-semibold text-brand-600 hover:underline">
                  {signup ? "Sign in" : "Create an account"}
                </Link>
              </p>
            </>
          )}

          {step === "code" && (
            <>
              <button onClick={() => { setStep("email"); setError(null); }} className="mb-6 flex items-center gap-1 self-start text-sm text-muted hover:text-ink">
                <ArrowLeft size={15} /> Use a different email
              </button>
              <h1 className="text-2xl font-bold tracking-tight">Check your email</h1>
              {delivery === "email" ? (
                <p className="mt-1 text-sm text-muted">
                  We sent a 6-digit code to <b className="text-ink">{email}</b>. It expires in 10 minutes.
                </p>
              ) : (
                <div className="mt-3 flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <Terminal size={16} className="mt-0.5 shrink-0" />
                  <span>
                    Email sending isn&apos;t set up yet, so your code is shown in the <b>terminal where Autopilot is running</b>. It expires in 10
                    minutes.
                  </span>
                </div>
              )}
              <form onSubmit={(e) => { e.preventDefault(); verify(); }} className="mt-6 space-y-4">
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
              <h1 className="text-2xl font-bold tracking-tight">Welcome to Autopilot</h1>
              <p className="mt-1 text-sm text-muted">One last thing: what should we call you?</p>
              <form onSubmit={saveName} className="mt-6 space-y-4">
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

      <div className="relative hidden overflow-hidden bg-zinc-900 lg:block">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.18),transparent_45%)]" />
        <div className="relative flex h-full flex-col justify-center px-14 text-white">
          <p className="text-sm font-semibold uppercase tracking-widest text-white/70">Your AI employee</p>
          <h2 className="mt-3 max-w-md text-4xl font-bold leading-tight tracking-tight">Set a goal and a budget. Autopilot gets it done.</h2>
          <ul className="mt-8 max-w-md space-y-3 text-[15px]">
            <Point icon={<Send size={16} />}>It plans and does the work: research, outreach, posting, follow-ups.</Point>
            <Point icon={<Hand size={16} />}>It asks before anything important, until you say it doesn&apos;t need to.</Point>
            <Point icon={<Wallet size={16} />}>It never spends more than the budget you set.</Point>
            <Point icon={<CheckCircle2 size={16} />}>Every step is in the work log, so you always know what it did.</Point>
          </ul>
        </div>
      </div>
    </div>
  );
}

function Point({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/15">{icon}</span>
      <span className="text-white/90">{children}</span>
    </li>
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
