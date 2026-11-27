"use client";

import { Check, Download, Loader2, Plug, RefreshCw } from "lucide-react";
import { useState } from "react";

import { api, BrowserInfo, ConnectMethod } from "@/lib/api";
import { Button } from "./ui";

type Tool = { label: string; app: string | null; site: string | null; login_url: string | null; method?: ConnectMethod | null };

/** How a tool connects, in a few words (shown before anyone clicks). */
export function connectHint(t: Tool, browser?: BrowserInfo | null): string {
  const name = t.label.replace(/\s*\(.*\)$/, "");
  if (t.method === "app") return `Sign in on ${name}'s own page`;
  if (t.method === "site") {
    return browser?.where === "helper" ? `Through the ${name} website, on your computer` : `Through the ${name} website, in Oton Chrome`;
  }
  return "";
}

/** One Connect button per tool. What it does depends on how Oton uses the tool:
 *  - app: opens the app's own sign-in page (Composio) in a new tab;
 *  - site: opens the website's sign-in page in Oton's browser window (Oton Chrome, or the desktop
 *    helper's window on your computer), or first explains how to set up the desktop helper.
 *  Returns the button and the guidance to show under the tool. */
export function useConnect(t: Tool, browser: BrowserInfo | null | undefined, onChanged: () => void, back = "/connections") {
  const [phase, setPhase] = useState<"idle" | "app" | "site" | "needs_helper" | "offline">("idle");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const connect = () => run(async () => {
    if (t.method === "app" && t.app) {
      const r = await api<{ redirect_url: string }>(`/api/connections/${encodeURIComponent(t.app)}/connect?back=${encodeURIComponent(back)}`, { method: "POST" });
      window.open(r.redirect_url, "_blank", "noopener");
      setPhase("app");
      return;
    }
    if (browser?.where === "helper" && !browser.paired) return setPhase("needs_helper");
    if (browser?.where === "helper" && !browser.online) return setPhase("offline");
    await api("/api/browser/open", { method: "POST", json: { url: t.login_url || t.site } });
    setPhase("site");
  });
  const signedIn = () => run(async () => {
    await api("/api/sites/signed-in", { method: "POST", json: { site: t.site } });
    onChanged();
  });

  const device = browser?.device?.name || "your computer";
  const name = t.label.replace(/\s*\(.*\)$/, "");  // "X (Twitter)" -> "X"
  const window_ = browser?.where === "helper" ? `the Oton window on ${device}` : "the Oton Chrome window";

  const button = phase === "site"
    ? <Button size="sm" variant="primary" disabled={busy} onClick={signedIn}><Check size={13} /> I&apos;ve signed in</Button>
    : <Button size="sm" variant="primary" disabled={busy || !t.method} onClick={connect}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />} Connect
      </Button>;

  const help = phase === "app" ? (
    <span className="flex flex-wrap items-center gap-2">
      A new tab opened with {name}&apos;s own sign-in page. Sign in and allow access there; it shows as connected when you come back.
      <Button size="sm" variant="ghost" onClick={onChanged}><RefreshCw size={13} /> Check again</Button>
    </span>
  ) : phase === "site" ? (
    <>{name}&apos;s sign-in page opened in {window_}. Sign in there as you normally would (Oton never sees your password), then click &quot;I&apos;ve signed in&quot;.</>
  ) : phase === "needs_helper" ? (
    <span className="block space-y-1.5">
      <span className="block">Oton uses {name} through its website, from your own computer, so it posts from your account without {name}&apos;s paid API. Each post still waits for your OK. To set it up:</span>
      <span className="block">1. Install the Oton desktop helper{browser?.download_url && <> (<a href={browser.download_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-brand-700 hover:underline"><Download size={11} /> download</a>)</>}.</span>
      <span className="block">2. Connect your computer: <a href="/connections#desktop-helper" target="_blank" className="font-semibold text-brand-700 hover:underline">Connections → Desktop helper → Connect a computer</a>.</span>
      <span className="block">3. Click Connect here again: {name}&apos;s sign-in page opens in the helper&apos;s window.</span>
    </span>
  ) : phase === "offline" ? (
    <>{device === "your computer" ? "Your computer" : device} isn&apos;t connected right now. Open the Oton desktop helper on it, then click Connect again.</>
  ) : null;

  return { button, help, error: err };
}
