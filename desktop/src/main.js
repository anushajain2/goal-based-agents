// Autopilot Helper: the desktop app (tray icon + a small window).
//
// It keeps one connection open to Autopilot and starts a separate Chrome window when an AI
// employee needs a website. Pairing: paste the link from Autopilot, or click "Open in the helper"
// there (autopilot://pair?key=...). The token is stored encrypted with the OS keychain.
"use strict";

const { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, safeStorage, shell } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { HelperCore, pair, parsePairKey } = require("./core");

const VERSION = app.getVersion();
const configFile = () => path.join(app.getPath("userData"), "config.json");
let core = null;
let tray = null;
let win = null;
let config = null; // { server, tokenEnc|token, name, orgName, appUrl, paused, openAtLogin }
let lastError = null;
let pendingLink = null;

// --- config ------------------------------------------------------------------------------------------

function loadConfig() {
  try {
    const c = JSON.parse(fs.readFileSync(configFile(), "utf8"));
    if (c.tokenEnc && safeStorage.isEncryptionAvailable()) {
      c.token = safeStorage.decryptString(Buffer.from(c.tokenEnc, "base64"));
    }
    return c.token && c.server ? c : null;
  } catch {
    return null;
  }
}

function saveConfig(c) {
  const out = { ...c };
  if (safeStorage.isEncryptionAvailable()) {
    out.tokenEnc = safeStorage.encryptString(c.token).toString("base64");
    delete out.token;
  }
  fs.mkdirSync(path.dirname(configFile()), { recursive: true });
  fs.writeFileSync(configFile(), JSON.stringify(out, null, 2), { mode: 0o600 });
}

function clearConfig() {
  try { fs.unlinkSync(configFile()); } catch {}
  config = null;
}

// --- state for the window and tray --------------------------------------------------------------------

function state() {
  const s = core ? core.status() : { state: "unpaired", paused: false, chrome: "closed", channels: 0 };
  return {
    ...s,
    paired: !!config,
    name: config?.name || os.hostname(),
    orgName: config?.orgName || "",
    server: config?.server || "",
    appUrl: config?.appUrl || "",
    openAtLogin: app.getLoginItemSettings().openAtLogin,
    error: lastError || s.error || null,
    version: VERSION,
    pendingLink,
  };
}

function label(s) {
  if (!s.paired) return "Not connected yet";
  if (s.state === "removed") return "Removed in Autopilot";
  if (s.paused) return "Paused";
  if (s.state === "connected") return s.channels ? "Working in Chrome" : "Ready";
  if (s.state === "connecting") return "Connecting…";
  return "Offline, reconnecting…";
}

function refresh() {
  const s = state();
  if (win && !win.isDestroyed()) win.webContents.send("state", s);
  if (tray) {
    tray.setToolTip(`Autopilot Helper: ${label(s)}`);
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: label(s), enabled: false },
      { type: "separator" },
      { label: "Open Autopilot Helper", click: showWindow },
      ...(s.paired && s.state !== "removed" ? [{ label: s.paused ? "Resume" : "Pause", click: () => setPaused(!s.paused) }] : []),
      ...(s.appUrl ? [{ label: "Open Autopilot", click: () => shell.openExternal(s.appUrl) }] : []),
      { type: "separator" },
      { label: "Quit", click: () => { app.isQuitting = true; app.quit(); } },
    ]));
  }
}

// --- helper core -------------------------------------------------------------------------------------------

function startCore() {
  if (core) core.removeAllListeners();
  core = new HelperCore({
    server: config.server,
    token: config.token,
    paused: !!config.paused,
    profileDir: path.join(app.getPath("userData"), "chrome-profile"),
    version: VERSION,
  });
  core.on("status", refresh);
  core.on("log", (m) => console.log("[helper]", m));
  core.on("removed", async () => {
    await core.stop();
    clearConfig();
    lastError = "This computer was removed in Autopilot. Pair it again to use it.";
    core = null;
    refresh();
  });
  core.start();
  refresh();
}

function setPaused(paused) {
  if (!core || !config) return;
  core.setPaused(paused);
  config.paused = paused;
  saveConfig(config);
  refresh();
}

async function doPair(key, name) {
  lastError = null;
  pendingLink = null;
  const res = await pair(key, { name: name || os.hostname(), platform: process.platform, version: VERSION });
  if (core) await core.stop();
  config = { server: res.server, token: res.token, name: res.name, orgName: res.orgName, appUrl: res.appUrl, paused: false };
  saveConfig(config);
  if (app.isPackaged) app.setLoginItemSettings({ openAtLogin: true, openAsHidden: true });
  startCore();
  return state();
}

async function disconnect() {
  if (core) await core.stop();
  core = null;
  clearConfig();
  refresh();
}

// --- window, tray, links -------------------------------------------------------------------------------------

function showWindow() {
  if (win && !win.isDestroyed()) {
    win.show();
    win.focus();
    return;
  }
  win = new BrowserWindow({
    width: 440, height: 600, resizable: false, maximizable: false, fullscreenable: false,
    title: "Autopilot Helper", backgroundColor: "#ffffff", show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  win.setMenuBarVisibility(false);
  win.loadFile(path.join(__dirname, "ui", "index.html"));
  win.once("ready-to-show", () => win.show());
  win.on("close", (e) => {
    if (!app.isQuitting) { e.preventDefault(); win.hide(); } // keep running in the tray
  });
}

function trayIcon() {
  const file = process.platform === "darwin" ? "trayTemplate.png" : "tray.png";
  const img = nativeImage.createFromPath(path.join(__dirname, "..", "assets", file));
  if (process.platform === "darwin") img.setTemplateImage(true);
  return img;
}

function handleLink(url) {
  if (!url || !url.startsWith("autopilot://")) return;
  if (!parsePairKey(url)) return;
  pendingLink = url; // the window asks before pairing
  showWindow();
  refresh();
}

ipcMain.handle("state", () => state());
ipcMain.handle("pair", async (_e, key, name) => {
  try {
    return await doPair(key, name);
  } catch (e) {
    lastError = e.message;
    refresh();
    return state();
  }
});
ipcMain.handle("pause", (_e, paused) => { setPaused(!!paused); return state(); });
ipcMain.handle("disconnect", async () => { await disconnect(); return state(); });
ipcMain.handle("signin", async (_e, url) => {
  try { await core?.openSignin(url); lastError = null; } catch (e) { lastError = e.message; }
  refresh();
  return state();
});
ipcMain.handle("signin-done", async () => { await core?.finishSignin(); refresh(); return state(); });
ipcMain.handle("open-login-at-start", (_e, on) => {
  app.setLoginItemSettings({ openAtLogin: !!on, openAsHidden: true });
  return state();
});
ipcMain.handle("open-app", () => { if (config?.appUrl) shell.openExternal(config.appUrl); });
ipcMain.handle("dismiss-link", () => { pendingLink = null; refresh(); return state(); });

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.setAsDefaultProtocolClient("autopilot");
  app.on("second-instance", (_e, argv) => {
    const link = argv.find((a) => a.startsWith("autopilot://"));
    if (link) handleLink(link);
    else showWindow();
  });
  app.on("open-url", (e, url) => { e.preventDefault(); app.whenReady().then(() => handleLink(url)); });

  app.whenReady().then(() => {
    tray = new Tray(trayIcon());
    tray.on("click", showWindow);
    config = loadConfig();
    if (config) startCore();
    refresh();
    const link = process.argv.find((a) => a.startsWith("autopilot://"));
    if (link) handleLink(link);
    const hidden = app.getLoginItemSettings().wasOpenedAsHidden || process.argv.includes("--hidden");
    if (!config || !hidden) showWindow();
  });

  app.on("window-all-closed", () => { /* stay in the tray */ });
  app.on("activate", showWindow);
  app.on("before-quit", async (e) => {
    if (core && !app.coreStopped) {
      e.preventDefault();
      app.isQuitting = true;
      app.coreStopped = true;
      await core.stop(); // closes Chrome cleanly so sign-ins are saved
      app.quit();
    }
  });
}
