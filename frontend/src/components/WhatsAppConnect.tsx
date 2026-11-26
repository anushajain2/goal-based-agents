"use client";

import { Check, ExternalLink, MessageCircle, Smartphone, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, useApi } from "@/lib/api";
import { Button, Card, CardHeader, cx, ErrorNote } from "./ui";

type Prefs = { approvals: boolean; heads_ups: boolean; questions: boolean };
type Me = {
  available: boolean; connected: boolean; number: string | null; connected_at: string | null; prefs: Prefs;
  business_number: string | null;
};
type LinkInfo = Me & { code: string; url: string; text: string; expires_at: string };

const PREF_WORDS: [keyof Prefs, string, string][] = [
  ["approvals", "Approvals", "Posts, messages, articles, hand-ins and suggestions waiting for your OK"],
  ["heads_ups", "Heads-ups", "Things that go out on their own in 30 minutes unless you stop them"],
  ["questions", "Questions", "When an AI employee needs something only your team knows"],
];

/**
 * Connect WhatsApp so approvals, heads-ups and questions come to your phone with everything
 * needed to decide. Connecting means sending our number a one-time code from your own phone:
 * that proves the number is yours and is how WhatsApp wants people to opt in.
 */
export function WhatsAppConnect() {
  const [link, setLink] = useState<LinkInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // While a code is out, check every few seconds so the card flips to "connected" by itself.
  const { data: me, setData } = useApi<Me>("/api/whatsapp/me", { live: false, pollMs: link ? 3000 : 60000 });
  const connected = me?.connected;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setLink(await api<LinkInfo>("/api/whatsapp/link", { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function setPref(key: keyof Prefs, value: boolean) {
    try {
      setData(await api<Me>("/api/whatsapp/me", { method: "PUT", json: { [key]: value } }));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function disconnect() {
    if (!confirm("Disconnect WhatsApp? You'll stop getting approvals there.")) return;
    setData(await api<Me>("/api/whatsapp/me", { method: "DELETE" }));
    setLink(null);
  }

  if (!me) return null;
  return (
    <Card>
      <div id="whatsapp" />
      <CardHeader
        title={<span className="flex items-center gap-2"><MessageCircle size={16} /> WhatsApp</span>}
        subtitle="Approve, edit, stop and answer from your phone. Each message has everything you need to decide, so you rarely need to open Autopilot."
      />
      <div className="space-y-3 p-4 text-sm">
        {error && <ErrorNote>{error}</ErrorNote>}
        {!me.available ? (
          <p className="text-muted">
            WhatsApp isn&apos;t set up on this Autopilot yet. Whoever runs it adds the platform&apos;s WhatsApp Business number once
            (see docs/WHATSAPP.md), then everyone can connect their own phone here.
          </p>
        ) : connected ? (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-emerald-50 text-emerald-700"><Check size={17} /></span>
              <span className="min-w-0 flex-1">
                <b className="block">Connected: {me.number}</b>
                <span className="text-xs text-muted">Send &quot;list&quot; in the chat to see what&apos;s waiting, or &quot;stop&quot; to disconnect.</span>
              </span>
              <Button size="sm" variant="ghost" onClick={disconnect}><X size={14} /> Disconnect</Button>
            </div>
            <div className="divide-y divide-line rounded-lg border border-line">
              {PREF_WORDS.map(([key, title, hint]) => (
                <label key={key} className="flex cursor-pointer items-center gap-3 px-3 py-2.5">
                  <input type="checkbox" className="h-4 w-4 accent-brand-500" checked={me.prefs[key]} onChange={(e) => setPref(key, e.target.checked)} />
                  <span className="min-w-0 flex-1"><b className="block text-[13px]">{title}</b><span className="text-xs text-muted">{hint}</span></span>
                </label>
              ))}
            </div>
            <p className="text-xs text-muted">
              Spending money, merging code and deleting things come with the details and a link to decide them in Autopilot: a tap on
              a phone shouldn&apos;t do those.
            </p>
          </>
        ) : link ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3 rounded-lg bg-emerald-50 px-3 py-3">
              <Smartphone size={18} className="text-emerald-700" />
              <span className="min-w-0 flex-1 text-emerald-950">
                Open WhatsApp and send the message it fills in. That&apos;s it: this page updates when it arrives.
              </span>
              <a href={link.url} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-[13px] font-semibold text-white hover:bg-emerald-700">
                Open WhatsApp <ExternalLink size={13} />
              </a>
            </div>
            <p className="text-xs text-muted">
              On a computer without WhatsApp? On your phone, send <b className="font-mono text-ink">{link.text}</b> to{" "}
              <b className="text-ink">{me.business_number}</b>. The code works once, for 15 minutes.{" "}
              <button onClick={start} className="font-semibold text-brand-600 hover:underline">New code</button>
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <p className="min-w-0 flex-1 text-muted">
              You&apos;ll send one message from your phone to connect. That&apos;s also how WhatsApp knows you asked for these messages;
              send &quot;stop&quot; any time to end them.
            </p>
            <Button variant="primary" disabled={busy} onClick={start}><MessageCircle size={15} /> Connect WhatsApp</Button>
          </div>
        )}
      </div>
    </Card>
  );
}

/** A one-line nudge in Needs you, until someone connects (and only where WhatsApp is set up). */
export function WhatsAppNudge() {
  const { data: me } = useApi<Me>("/api/whatsapp/me", { live: false, pollMs: 300000 });
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem("wa-nudge-hidden") === "1"; } catch { return false; }
  });
  if (!me?.available || me.connected || hidden) return null;
  return (
    <div className={cx("flex flex-wrap items-center gap-2 rounded-xl bg-emerald-50 px-4 py-2.5 text-[13px] text-emerald-950 ring-1 ring-inset ring-emerald-200")}>
      <MessageCircle size={15} className="text-emerald-700" />
      <span className="min-w-0 flex-1">Decide from your phone: get these on WhatsApp, with everything you need to approve, edit or stop them.</span>
      <Link href="/settings#whatsapp" className="font-semibold text-emerald-800 hover:underline">Connect WhatsApp</Link>
      <button aria-label="Hide" onClick={() => { setHidden(true); try { localStorage.setItem("wa-nudge-hidden", "1"); } catch { /* fine */ } }}
        className="rounded p-0.5 text-emerald-700 hover:bg-emerald-100"><X size={14} /></button>
    </div>
  );
}
