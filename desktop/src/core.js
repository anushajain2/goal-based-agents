// The desktop helper's core: pairing, the connection to Autopilot, and the bridge to Chrome.
//
// It connects *out* to Autopilot (nothing listens for incoming connections on this computer),
// and Autopilot drives a separate Chrome window through that connection. Everything the AI
// employee does (reading pages, clicking, the rule that "Post"/"Send"/"Buy" needs a person's
// approval) is decided on the server; this file only carries messages and starts Chrome.
//
// Protocol (JSON text frames over one WebSocket):
//   server -> helper  {t:"hello"}, {t:"open",c}, {t:"d",c,d}, {t:"close",c}, {t:"pong"},
//                     {t:"open_url",url}, {t:"manual_signin",url}, {t:"manual_done"}
//   helper -> server  {t:"d",c,d}, {t:"closed",c,error?}, {t:"ping",paused}, {t:"status",paused}
"use strict";

const { EventEmitter } = require("events");
const WebSocket = require("ws");
const chrome = require("./chrome");

const PING_MS = 25000;

/** "https://host/api/helper/pair/ABCD-EFGH" or "autopilot://pair?key=<that>" -> {server, code}. */
function parsePairKey(input) {
  let text = String(input || "").trim();
  if (text.startsWith("autopilot://")) {
    const key = new URL(text).searchParams.get("key");
    if (key) text = key;
  }
  const m = text.match(/^(https?:\/\/[^/\s]+)\/api\/helper\/pair\/([A-Za-z0-9-]{8,12})\/?$/);
  if (!m) return null;
  return { server: m[1], code: m[2] };
}

/** Swap a pairing key for this computer's own token. */
async function pair(key, { name, platform, version } = {}) {
  const parsed = parsePairKey(key);
  if (!parsed) throw new Error("That doesn't look like a pairing link. Copy it again from Autopilot (Connections page).");
  let res;
  try {
    res = await fetch(`${parsed.server}/api/helper/pair`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code: parsed.code, name, platform, version }),
    });
  } catch (e) {
    throw new Error(`Couldn't reach Autopilot at ${parsed.server}. Check your internet connection.`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Pairing failed (${res.status}).`);
  return { server: body.server || parsed.server, token: body.token, deviceId: body.device_id, name: body.name,
           orgName: body.org_name, appUrl: body.app_url || null };
}

class HelperCore extends EventEmitter {
  /**
   * @param {object} o
   * @param {string} o.server      Autopilot API address, e.g. https://autopilot-api-xxxx.onrender.com
   * @param {string} o.token       this computer's token (from pair())
   * @param {string} o.profileDir  folder for the helper's own Chrome profile
   * @param {string} [o.chromePath] Chrome to use (found automatically otherwise)
   * @param {boolean} [o.headless] for tests and servers only
   * @param {string} [o.version]
   */
  constructor(o) {
    super();
    this.o = o;
    this.ws = null;
    this.paused = !!o.paused;
    this.channels = new Map(); // c -> { ws, queue }
    this.chrome = null; // { proc, wsUrl, port }
    this.manual = null; // a plain Chrome window open for signing in
    this.state = "stopped"; // stopped | connecting | connected | offline | removed
    this.info = null; // {device, org_name}
    this.error = null;
    this._stopped = true;
    this._retry = 1000;
    this._ping = null;
    this._starting = null;
  }

  status() {
    return { state: this.state, paused: this.paused, error: this.error, device: this.info?.device || null,
             chrome: this.manual ? "signing-in" : this.chrome ? "running" : "closed", channels: this.channels.size };
  }

  _set(patch) {
    Object.assign(this, patch);
    this.emit("status", this.status());
  }

  start() {
    this._stopped = false;
    this._connect();
  }

  async stop() {
    this._stopped = true;
    clearInterval(this._ping);
    clearTimeout(this._timer);
    this._closeChannels();
    if (this.ws) { try { this.ws.close(1000); } catch {} this.ws = null; }
    await chrome.stop(this.chrome?.proc);
    await chrome.stop(this.manual);
    this.chrome = null;
    this.manual = null;
    this._set({ state: "stopped" });
  }

  setPaused(paused) {
    this.paused = !!paused;
    if (this.paused) this._closeChannels();
    this._send({ t: "status", paused: this.paused });
    this._set({});
  }

  // --- connection to Autopilot ---------------------------------------------------------------

  _connect() {
    if (this._stopped) return;
    this._set({ state: this.state === "connected" ? "offline" : "connecting" });
    const url = this.o.server.replace(/^http/, "ws").replace(/\/$/, "") + "/api/helper/connect";
    const ws = new WebSocket(url, { headers: { authorization: `Bearer ${this.o.token}`,
                                               "x-helper-version": this.o.version || "dev" },
                                    handshakeTimeout: 15000 });
    this.ws = ws;
    ws.on("open", () => {
      this._retry = 1000;
      this._set({ state: "connected", error: null });
      this._send({ t: "status", paused: this.paused });
      clearInterval(this._ping);
      this._ping = setInterval(() => this._send({ t: "ping", paused: this.paused }), PING_MS);
    });
    ws.on("message", (raw) => {
      let msg;
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      this._handle(msg).catch((e) => this.emit("log", `error: ${e.message}`));
    });
    ws.on("unexpected-response", (req, res) => {
      // The handshake was refused. 401/403: this computer's token no longer works (removed in
      // Autopilot). Anything else (e.g. 502 while Autopilot deploys): try again shortly.
      try { req.destroy(); } catch {}
      if (this.ws !== ws) return;
      this.ws = null;
      if (res.statusCode === 403 || res.statusCode === 401) return this._removed();
      this._set({ state: "offline" });
      this._timer = setTimeout(() => this._connect(), this._retry);
      this._retry = Math.min(this._retry * 2, 30000);
    });
    ws.on("close", (code) => {
      clearInterval(this._ping);
      this._closeChannels();
      if (this.ws !== ws) return;
      this.ws = null;
      if (code === 4401) return this._removed();
      if (this._stopped) return;
      this._set({ state: "offline" });
      this._timer = setTimeout(() => this._connect(), this._retry);
      this._retry = Math.min(this._retry * 2, 30000);
    });
    ws.on("error", (e) => { this.emit("log", `connection: ${e.message}`); });
  }

  _removed() {
    this._stopped = true;
    this._set({ state: "removed", error: "This computer was removed in Autopilot. Pair it again to use it." });
    this.emit("removed");
  }

  _send(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  async _handle(msg) {
    switch (msg.t) {
      case "hello":
        this.info = { device: msg.device };
        this._set({});
        return;
      case "open":
        return this._openChannel(msg.c);
      case "d": {
        const ch = this.channels.get(msg.c);
        if (!ch) return;
        if (ch.ws && ch.ws.readyState === WebSocket.OPEN) ch.ws.send(msg.d);
        else ch.queue.push(msg.d);
        return;
      }
      case "close": {
        const ch = this.channels.get(msg.c);
        this.channels.delete(msg.c);
        if (ch && ch.ws) { try { ch.ws.close(); } catch {} }
        this._set({});
        return;
      }
      case "open_url":
        return this._openTab(msg.url);
      case "manual_signin":
        return this._manualSignin(msg.url);
      case "manual_done":
        return this.finishSignin();
      default:
        return;
    }
  }

  // --- Chrome ------------------------------------------------------------------------------------

  async ensureChrome() {
    if (this.manual) throw new Error("A sign-in window is open. Finish signing in first.");
    if (this.chrome && this.chrome.proc.exitCode === null) return this.chrome;
    if (this._starting) return this._starting;
    const path = chrome.findChrome(this.o.chromePath);
    if (!path) {
      this._set({ error: "Google Chrome isn't installed. Install it from google.com/chrome, then try again." });
      throw new Error("Chrome not found");
    }
    this._starting = chrome.launchControlled(path, this.o.profileDir, { headless: this.o.headless })
      .then((c) => {
        this.chrome = c;
        c.proc.once("exit", () => { if (this.chrome === c) { this.chrome = null; this._set({}); } });
        this._set({ error: null });
        return c;
      })
      .finally(() => { this._starting = null; });
    return this._starting;
  }

  async _openChannel(c) {
    if (this.paused) return this._send({ t: "closed", c, error: "paused" });
    // Register the channel at once: messages for it can arrive while Chrome is still starting,
    // and they're queued until Chrome's connection is open.
    const ch = { ws: null, queue: [] };
    this.channels.set(c, ch);
    this._set({});
    let target;
    try {
      target = await this.ensureChrome();
    } catch (e) {
      this.channels.delete(c);
      this._set({});
      return this._send({ t: "closed", c, error: e.message });
    }
    if (this.channels.get(c) !== ch) return; // closed by the server meanwhile
    const ws = new WebSocket(target.wsUrl, { perMessageDeflate: false, maxPayload: 256 * 1024 * 1024 });
    ch.ws = ws;
    ws.on("open", () => { for (const d of ch.queue.splice(0)) ws.send(d); });
    ws.on("message", (data) => this._send({ t: "d", c, d: data.toString() }));
    ws.on("close", () => {
      if (this.channels.get(c) === ch) {
        this.channels.delete(c);
        this._send({ t: "closed", c });
        this._set({});
      }
    });
    ws.on("error", (e) => this.emit("log", `chrome channel ${c}: ${e.message}`));
  }

  _closeChannels() {
    for (const [c, ch] of this.channels) {
      this.channels.delete(c);
      if (ch.ws) { try { ch.ws.close(); } catch {} }
      this._send({ t: "closed", c, error: "closed" });
    }
  }

  async _openTab(url) {
    const c = await this.ensureChrome();
    await fetch(`http://127.0.0.1:${c.port}/json/new?${encodeURI(url)}`, { method: "PUT" });
  }

  /** Close the remote-controlled window and open the same profile normally (for Google etc.). */
  async _manualSignin(url) {
    this._closeChannels();
    await chrome.stop(this.chrome?.proc);
    this.chrome = null;
    await chrome.stop(this.manual);
    const path = chrome.findChrome(this.o.chromePath);
    if (!path) return this._set({ error: "Google Chrome isn't installed." });
    this.manual = chrome.launchPlain(path, this.o.profileDir, url, { headless: this.o.headless });
    this.manual.once("exit", () => { this.manual = null; this._set({}); });
    this._set({});
  }

  async openSignin(url) {
    return this._manualSignin(/^https?:\/\//.test(url) ? url : `https://${url}`);
  }

  async finishSignin() {
    await chrome.stop(this.manual);
    this.manual = null;
    this._set({});
  }
}

module.exports = { HelperCore, pair, parsePairKey };
