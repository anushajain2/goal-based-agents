"use strict";
// The helper core against a fake Autopilot server and a fake Chrome (no real browser needed).
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("http");
const WebSocket = require("ws");
const { HelperCore, parsePairKey } = require("../src/core");

const once = (emitter, event) => new Promise((r) => emitter.once(event, r));
// Buffer messages per socket so none are missed when several arrive together.
const inboxes = new WeakMap();
function inbox(ws) {
  let box = inboxes.get(ws);
  if (!box) {
    box = { items: [], waiters: [] };
    inboxes.set(ws, box);
    ws.on("message", (m) => {
      const v = JSON.parse(m.toString());
      const w = box.waiters.shift();
      if (w) w(v); else box.items.push(v);
    });
  }
  return box;
}
function nextJson(ws) {
  const box = inbox(ws);
  if (box.items.length) return Promise.resolve(box.items.shift());
  return new Promise((r) => box.waiters.push(r));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function server(handler) {
  return new Promise((resolve) => {
    const srv = http.createServer();
    const wss = new WebSocket.Server({ server: srv });
    wss.on("connection", handler);
    srv.listen(0, "127.0.0.1", () => resolve({ srv, wss, url: `http://127.0.0.1:${srv.address().port}` }));
  });
}

test("pairing links: pasted or opened from the app", () => {
  assert.deepEqual(parsePairKey("https://autopilot-api-x.onrender.com/api/helper/pair/ABCD-EFGH"),
                   { server: "https://autopilot-api-x.onrender.com", code: "ABCD-EFGH" });
  const link = "autopilot://pair?key=" + encodeURIComponent("http://localhost:8000/api/helper/pair/ABCD-EFGH");
  assert.deepEqual(parsePairKey(link), { server: "http://localhost:8000", code: "ABCD-EFGH" });
  assert.equal(parsePairKey("hello"), null);
  assert.equal(parsePairKey("https://evil.example/somewhere/else"), null);
});

test("relays DevTools messages, even ones sent while Chrome is still starting", async () => {
  // Fake Chrome: answers every message with {id, result: {echo: method}}.
  const fakeChrome = await server((ws) => ws.on("message", (m) => {
    const msg = JSON.parse(m.toString());
    ws.send(JSON.stringify({ id: msg.id, result: { echo: msg.method } }));
  }));
  let autopilotSide;
  const api = await server((ws, req) => {
    assert.equal(req.headers.authorization, "Bearer aph_test");
    autopilotSide = ws;
    inbox(ws); // start buffering before anything can arrive
    ws.send(JSON.stringify({ t: "hello", device: { id: "d1", name: "Test" } }));
  });
  const core = new HelperCore({ server: api.url, token: "aph_test", profileDir: "/tmp/unused" });
  core.ensureChrome = async () => { await sleep(300); return { wsUrl: fakeChrome.url.replace("http", "ws"), port: 1 }; };
  core.start();
  await once(api.wss, "connection");
  const status = await nextJson(autopilotSide);
  assert.deepEqual(status, { t: "status", paused: false });

  autopilotSide.send(JSON.stringify({ t: "open", c: 1 }));
  // Sent right away, while "Chrome" takes 300 ms to start: must be queued, not dropped.
  autopilotSide.send(JSON.stringify({ t: "d", c: 1, d: JSON.stringify({ id: 1, method: "Browser.getVersion" }) }));
  const reply = await nextJson(autopilotSide);
  assert.equal(reply.t, "d");
  assert.equal(reply.c, 1);
  assert.deepEqual(JSON.parse(reply.d), { id: 1, result: { echo: "Browser.getVersion" } });

  // Pausing closes open channels and tells Autopilot.
  core.setPaused(true);
  const msgs = [await nextJson(autopilotSide), await nextJson(autopilotSide)];
  assert.ok(msgs.some((m) => m.t === "closed" && m.c === 1));
  assert.ok(msgs.some((m) => m.t === "status" && m.paused === true));
  autopilotSide.send(JSON.stringify({ t: "open", c: 2 }));
  assert.deepEqual(await nextJson(autopilotSide), { t: "closed", c: 2, error: "paused" });

  await core.stop();
  api.srv.close();
  fakeChrome.srv.close();
});

test("a computer removed in Autopilot stops trying to connect", async () => {
  const api = await server((ws) => ws.close(4401));
  const core = new HelperCore({ server: api.url, token: "aph_old", profileDir: "/tmp/unused" });
  core.start();
  await once(core, "removed");
  assert.equal(core.status().state, "removed");
  await sleep(200);
  assert.equal(api.wss.clients.size, 0);
  api.srv.close();
});

test("while someone signs in, website steps wait; closing the window resumes them", async () => {
  const chromeMod = require("../src/chrome");
  const { spawn } = require("child_process");
  const realPlain = chromeMod.launchPlain;
  const realFind = chromeMod.findChrome;
  chromeMod.findChrome = () => "/fake/chrome";
  // A stand-in for the visible sign-in window: a process that "closes" after 300 ms.
  chromeMod.launchPlain = () => spawn(process.execPath, ["-e", "setTimeout(() => {}, 300)"]);
  let autopilotSide;
  const api = await server((ws) => { autopilotSide = ws; inbox(ws); });
  const core = new HelperCore({ server: api.url, token: "aph_test", profileDir: "/tmp/unused" });
  core.start();
  await once(api.wss, "connection");
  assert.deepEqual(await nextJson(autopilotSide), { t: "status", paused: false });
  autopilotSide.send(JSON.stringify({ t: "open_url", url: "https://linkedin.com/login" }));
  assert.deepEqual(await nextJson(autopilotSide), { t: "status", paused: true }); // busy: steps wait
  assert.equal(core.status().chrome, "signing-in");
  assert.deepEqual(await nextJson(autopilotSide), { t: "status", paused: false }); // window closed
  assert.equal(core.status().chrome, "closed");
  await core.stop();
  chromeMod.launchPlain = realPlain;
  chromeMod.findChrome = realFind;
  api.srv.close();
});

test("changing the window setting never interrupts a step in progress", async () => {
  const chromeMod = require("../src/chrome");
  const realStop = chromeMod.stop;
  const stopped = [];
  chromeMod.stop = async (c) => { if (c) stopped.push(c.mode); };
  const core = new HelperCore({ server: "http://127.0.0.1:9", token: "x", profileDir: "/tmp/unused" });
  core.chrome = { mode: "hidden", proc: { exitCode: null } };
  core.channels.set(1, { ws: null, queue: [] }); // a step is running
  await core.setWindowMode("background");
  assert.deepEqual(stopped, []); // not now
  assert.equal(core.status().windowMode, "background");
  core.channels.delete(1);
  core._maybeRestart(); // the step finished
  await sleep(10);
  assert.deepEqual(stopped, ["hidden"]); // restarted; the next step opens Chrome the new way
  assert.equal(core.chrome, null);
  chromeMod.stop = realStop;
  await core.stop();
});
