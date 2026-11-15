"use client";

import { ArrowRight, CheckCircle2, Hand, Send, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { EmployeeAvatar } from "@/components/Shell";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

/** Only allow redirects back into the app, never to another site. */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/home";
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in? Go straight to the app.
  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" }).then((r) => r.ok && router.replace(next));
  }, [router, next]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/api/auth/${mode}`, { method: "POST", json: mode === "signup" ? { name, email, password } : { email, password } });
      router.replace(next);
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg.includes("string_too_short") || msg.includes("at least 8") ? "Use a password of at least 8 characters." : msg.includes("pattern") ? "Enter a valid email address." : msg);
      setBusy(false);
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
          <h1 className="text-2xl font-bold tracking-tight">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-1 text-sm text-muted">
            {signup ? "Set up your first goal in a couple of minutes." : "Log in to see what Autopilot has been working on."}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            {signup && (
              <Field label="Your name">
                <Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Asha Rao" />
              </Field>
            )}
            <Field label="Work email">
              <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
            </Field>
            <Field label="Password" hint={signup ? "At least 8 characters." : undefined}>
              <Input type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 8 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            {error && <ErrorNote>{error}</ErrorNote>}
            <Button variant="primary" className="h-10 w-full" disabled={busy}>
              {busy ? "One moment…" : signup ? "Create account" : "Log in"} {!busy && <ArrowRight size={15} />}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-muted">
            {signup ? "Already have an account?" : "New to Autopilot?"}{" "}
            <Link href={`/${signup ? "login" : "signup"}${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-semibold text-brand-600 hover:underline">
              {signup ? "Log in" : "Create an account"}
            </Link>
          </p>
        </div>
      </div>

      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-600 via-brand-500 to-violet-600 lg:block">
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
