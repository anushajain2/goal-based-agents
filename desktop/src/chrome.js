// Finding and starting Chrome for the helper.
//
// The helper uses its own Chrome profile (a separate folder), never the person's everyday one:
// AI employees only reach sites someone signed in to in *this* window. Chrome 136+ also refuses
// remote control of the default profile, so a separate profile is required anyway.
//
// "--remote-debugging-port=0" lets Chrome pick a free port and write it to DevToolsActivePort in
// the profile folder; it only listens on 127.0.0.1.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

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

function baseArgs(profileDir, { headless } = {}) {
  const args = [`--user-data-dir=${profileDir}`, "--no-first-run", "--no-default-browser-check",
                "--window-size=1280,900"];
  if (headless) args.push("--headless=new");
  if (process.platform === "linux" && process.getuid && process.getuid() === 0) args.push("--no-sandbox");
  return args;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Start Chrome with remote control on; resolves with { proc, port, wsUrl }. */
async function launchControlled(chromePath, profileDir, opts = {}) {
  fs.mkdirSync(profileDir, { recursive: true });
  const portFile = path.join(profileDir, "DevToolsActivePort");
  try { fs.unlinkSync(portFile); } catch {}
  const proc = spawn(chromePath, [...baseArgs(profileDir, opts), "--remote-debugging-port=0", "about:blank"],
                     { stdio: "ignore", detached: false });
  let exited = false;
  proc.once("exit", () => { exited = true; });
  for (let i = 0; i < 150; i++) {
    if (exited) throw new Error("Chrome closed right away. Is another window already using the Autopilot profile?");
    try {
      const [port, wsPath] = fs.readFileSync(portFile, "utf8").trim().split(/\r?\n/);
      if (port && wsPath) return { proc, port: Number(port), wsUrl: `ws://127.0.0.1:${port}${wsPath}` };
    } catch {}
    await sleep(100);
  }
  try { proc.kill(); } catch {}
  throw new Error("Chrome didn't start in time.");
}

/** Start Chrome normally (no remote control), for sites like Google that refuse sign-in otherwise. */
function launchPlain(chromePath, profileDir, url, opts = {}) {
  fs.mkdirSync(profileDir, { recursive: true });
  return spawn(chromePath, [...baseArgs(profileDir, opts), url], { stdio: "ignore", detached: false });
}

/** Ask Chrome to close (so cookies and sign-ins are saved), then make sure it's gone. */
async function stop(proc) {
  if (!proc || proc.exitCode !== null) return;
  const gone = new Promise((r) => proc.once("exit", r));
  try { proc.kill(process.platform === "win32" ? undefined : "SIGTERM"); } catch {}
  await Promise.race([gone, sleep(5000)]);
  if (proc.exitCode === null) { try { proc.kill("SIGKILL"); } catch {} }
}

module.exports = { findChrome, launchControlled, launchPlain, stop };
