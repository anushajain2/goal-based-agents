#!/usr/bin/env node
// The helper without a window, for testing and Linux machines:
//   node src/cli.js pair "<pairing link from Oton>" [--name "Office iMac"]
//   node src/cli.js run [--window hidden|background] [--chrome /path/to/chrome]
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { HelperCore, pair } = require("./core");
const { version } = require("../package.json");

const home = process.env.AUTOPILOT_HELPER_HOME || path.join(os.homedir(), ".autopilot-helper");
const configFile = path.join(home, "config.json");
const args = process.argv.slice(2);
const flag = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };

async function main() {
  const cmd = args[0];
  if (cmd === "pair") {
    const res = await pair(args[1], { name: flag("--name") || os.hostname(), platform: process.platform, version });
    fs.mkdirSync(home, { recursive: true });
    fs.writeFileSync(configFile, JSON.stringify({ server: res.server, token: res.token, name: res.name,
                                                  orgName: res.orgName }, null, 2), { mode: 0o600 });
    console.log(`Paired "${res.name}" with ${res.orgName || "your organization"}. Now run: node src/cli.js run`);
    return;
  }
  if (cmd === "run") {
    const cfg = JSON.parse(fs.readFileSync(configFile, "utf8"));
    const core = new HelperCore({ ...cfg, version, profileDir: path.join(home, "chrome-profile"),
                                  chromePath: flag("--chrome"), windowMode: flag("--window") || "hidden" });
    core.on("status", (s) => console.log(`[helper] ${s.state}${s.paused ? " (paused)" : ""} · chrome ${s.chrome}` +
                                         ` · ${s.channels} open · window ${s.windowMode}${s.error ? " · " + s.error : ""}`));
    core.on("log", (m) => console.log(`[helper] ${m}`));
    core.on("removed", async () => { await core.stop(); process.exit(2); });
    const quit = async () => { await core.stop(); process.exit(0); };
    process.on("SIGINT", quit);
    process.on("SIGTERM", quit);
    core.start();
    return;
  }
  console.log("Usage:\n  node src/cli.js pair \"<pairing link>\" [--name NAME]\n  node src/cli.js run [--window hidden|background] [--chrome PATH]");
  process.exit(1);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
