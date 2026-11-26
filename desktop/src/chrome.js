// Finding and starting Chrome for the helper.
//
// The helper uses its own Chrome profile (a separate folder), never the person's everyday one:
// AI employees only reach sites someone signed in to in *this* window. Chrome 136+ also refuses
// remote control of the default profile, so a separate profile is required anyway.
//
// The AI's Chrome never takes over the screen:
//   "hidden"      no window at all (default). It presents itself as normal Chrome to websites.
//   "background"  a real window you can watch, opened behind your other windows (on a Mac it
//                 never becomes the active app). New tabs open in the background too.
// Signing in to a site is different: that's a normal, visible window, because you asked for it.
//
// "--remote-debugging-port=0" lets Chrome pick a free port and write it to DevToolsActivePort in
// the profile folder; it only listens on 127.0.0.1.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const WebSocket = require("ws");

const MODES = ["hidden", "background"];

const CANDIDATES = {
  darwin: [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    path.join(os.homedir(), "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ],
  win32: [
    path.join(process.env["PROGRAMFILES"] || "C:\\Program Files", "Google\\Chrome\\Application\\chrome.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)", "Google\\Chrome\\Application\\chrome.exe"),
    path.join(process.env["LOCALAPPDATA"] || "", "Google\\Chrome\\Application\\chrome.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)", "Microsoft\\Edge\\Application\\msedge.exe"),
  ],
  linux: ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
          "/snap/bin/chromium"],
};

function findChrome(explicit) {
  if (explicit) return fs.existsSync(explicit) ? explicit : null;
  for (const p of CANDIDATES[process.platform] || CANDIDATES.linux) {
    if (p && fs.existsSync(p)) return p;
  }
  return null;
}

function baseArgs(profileDir) {
  const args = [`--user-data-dir=${profileDir}`, "--no-first-run", "--no-default-browser-check",
                "--window-size=1280,900",
                // Don't announce "controlled by automation" to websites (navigator.webdriver).
                "--disable-blink-features=AutomationControlled"];
  if (process.platform === "linux" && process.getuid && process.getuid() === 0) args.push("--no-sandbox");
  return args;
}

// Keep pages working normally while the window is hidden or behind other windows.
const KEEP_RUNNING = ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                      "--disable-background-timer-throttling"];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** One DevTools call over a short-lived connection. */
function cdpCall(wsUrl, method, params = {}, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl, { perMessageDeflate: false });
    const timer = setTimeout(() => { try { ws.terminate(); } catch {} reject(new Error(`${method} timed out`)); }, timeoutMs);
    ws.on("open", () => ws.send(JSON.stringify({ id: 1, method, params })));
    ws.on("message", (m) => {
      const msg = JSON.parse(m.toString());
      if (msg.id !== 1) return;
      clearTimeout(timer);
      try { ws.close(); } catch {}
      if (msg.error) reject(new Error(msg.error.message)); else resolve(msg.result);
    });
    ws.on("error", (e) => { clearTimeout(timer); reject(e); });
    ws.on("close", () => clearTimeout(timer));
  });
}

async function waitForPort(profileDir, proc) {
  const portFile = path.join(profileDir, "DevToolsActivePort");
  let exited = false;
  proc.once("exit", () => { exited = true; });
  for (let i = 0; i < 150; i++) {
    if (exited) throw new Error("Chrome closed right away. Is another window already using the Oton profile?");
    try {
      const [port, wsPath] = fs.readFileSync(portFile, "utf8").trim().split(/\r?\n/);
      if (port && wsPath) return { port: Number(port), wsUrl: `ws://127.0.0.1:${port}${wsPath}` };
    } catch {}
    await sleep(100);
  }
  throw new Error("Chrome didn't start in time.");
}

function appBundle(chromePath) {
  const i = chromePath.indexOf(".app/");
  return i >= 0 ? chromePath.slice(0, i + 4) : null;
}

function start(chromePath, args, { background } = {}) {
  const bundle = process.platform === "darwin" && background ? appBundle(chromePath) : null;
  if (bundle) {
    // macOS: "open -g" starts it without bringing it to the front; -n = its own instance (even if
    // your Chrome is open); -W = this process lives as long as that Chrome does.
    return spawn("open", ["-g", "-n", "-W", "-a", bundle, "--args", ...args], { stdio: "ignore" });
  }
  return spawn(chromePath, args, { stdio: "ignore", detached: false });
}

// Invisible Chrome calls itself "HeadlessChrome"; learn the real name once and use that instead.
const userAgents = new Map();
async function realUserAgent(chromePath, profileDir) {
  if (userAgents.has(chromePath)) return userAgents.get(chromePath);
  const probeDir = path.join(path.dirname(profileDir), "chrome-probe");
  fs.mkdirSync(probeDir, { recursive: true });
  try { fs.unlinkSync(path.join(probeDir, "DevToolsActivePort")); } catch {}
  const proc = start(chromePath, [...baseArgs(probeDir), "--headless=new", "--remote-debugging-port=0", "about:blank"]);
  let ua = null;
  try {
    const { wsUrl } = await waitForPort(probeDir, proc);
    const v = await cdpCall(wsUrl, "Browser.getVersion");
    ua = (v.userAgent || "").replace("HeadlessChrome", "Chrome") || null;
    await cdpCall(wsUrl, "Browser.close").catch(() => {});
  } finally {
    await waitExit(proc, 3000);
    try { proc.kill("SIGKILL"); } catch {}
  }
  if (ua) userAgents.set(chromePath, ua);
  return ua;
}

/** Start the AI's Chrome with remote control on; resolves with { proc, pid, port, wsUrl, mode }. */
async function launchControlled(chromePath, profileDir, { mode = "hidden" } = {}) {
  if (!MODES.includes(mode)) mode = "hidden";
  fs.mkdirSync(profileDir, { recursive: true });
  try { fs.unlinkSync(path.join(profileDir, "DevToolsActivePort")); } catch {}
  const args = [...baseArgs(profileDir), ...KEEP_RUNNING, "--remote-debugging-port=0"];
  if (mode === "hidden") {
    const ua = await realUserAgent(chromePath, profileDir).catch(() => null);
    args.push("--headless=new");
    if (ua) args.push(`--user-agent=${ua}`);
  }
  args.push("about:blank");
  const proc = start(chromePath, args, { background: mode === "background" });
  let port, wsUrl;
  try {
    ({ port, wsUrl } = await waitForPort(profileDir, proc));
  } catch (e) {
    try { proc.kill(); } catch {}
    throw e;
  }
  let pid = null;
  try {
    const info = await cdpCall(wsUrl, "SystemInfo.getProcessInfo");
    pid = (info.processInfo || []).find((p) => p.type === "browser")?.id || null;
  } catch {}
  return { proc, pid, port, wsUrl, mode };
}

/** Start Chrome normally (no remote control, visible) for someone to sign in to a site. */
function launchPlain(chromePath, profileDir, url) {
  fs.mkdirSync(profileDir, { recursive: true });
  return spawn(chromePath, [...baseArgs(profileDir), url], { stdio: "ignore", detached: false });
}

function waitExit(proc, ms) {
  if (!proc || proc.exitCode !== null || proc.signalCode) return Promise.resolve();
  return Promise.race([new Promise((r) => proc.once("exit", r)), sleep(ms)]);
}

/** Close Chrome cleanly (so cookies and sign-ins are saved), then make sure it's gone. */
async function stop(c) {
  if (!c) return;
  const proc = c.proc || c; // a launchControlled() result, or a plain process
  if (c.wsUrl) await cdpCall(c.wsUrl, "Browser.close", {}, 3000).catch(() => {});
  else { try { proc.kill(process.platform === "win32" ? undefined : "SIGTERM"); } catch {} }
  await waitExit(proc, 5000);
  if (proc.exitCode === null && !proc.signalCode) {
    if (c.pid) { try { process.kill(c.pid, "SIGKILL"); } catch {} }
    try { proc.kill("SIGKILL"); } catch {}
  }
}

module.exports = { MODES, findChrome, launchControlled, launchPlain, stop, cdpCall };
