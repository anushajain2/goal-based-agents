"use strict";
const $ = (id) => document.getElementById(id);
let current = null;

const PILL = {
  unpaired: ["Not connected", ""], connecting: ["Connecting…", "busy"], connected: ["Ready", "ok"],
  offline: ["Offline", "warn"], removed: ["Removed", "warn"], stopped: ["Not connected", ""],
};

function render(s) {
  current = s;
  const paired = s.paired && s.state !== "removed";
  $("unpaired").hidden = paired;
  $("paired").hidden = !paired;
  let [text, tone] = PILL[paired ? s.state : "unpaired"] || ["", ""];
  if (paired && s.paused) [text, tone] = ["Paused", "warn"];
  else if (paired && s.state === "connected" && s.channels) [text, tone] = ["Working", "busy"];
  $("pill").textContent = text;
  $("pill").className = "pill " + tone;
  if (!$("name").value) $("name").value = s.name || "";
  $("confirm").hidden = !s.pendingLink;
  if (paired) {
    $("headline").textContent = s.paused ? "Paused" : s.state === "connected"
      ? (s.channels ? "An AI employee is using Chrome" : "Ready for website work") : "Reconnecting to Autopilot…";
    $("sub").textContent = `${s.name}${s.orgName ? " · " + s.orgName : ""}`;
    $("pause").checked = !!s.paused;
    $("login").checked = !!s.openAtLogin;
    $("signing").hidden = s.chrome !== "signing-in";
    $("open-app").hidden = !s.appUrl;
  }
  $("error").hidden = !s.error;
  $("error").textContent = s.error || "";
  $("version").textContent = `Version ${s.version}`;
}

async function act(fn, btn) {
  if (btn) btn.disabled = true;
  try { render(await fn()); } finally { if (btn) btn.disabled = false; }
}

$("pair-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(() => window.helper.pair($("key").value.trim(), $("name").value.trim()), $("pair-btn"));
});
$("confirm-yes").addEventListener("click", () => act(() => window.helper.pair(current.pendingLink, $("name").value.trim()), $("confirm-yes")));
$("confirm-no").addEventListener("click", () => act(() => window.helper.dismissLink()));
$("pause").addEventListener("change", (e) => act(() => window.helper.pause(e.target.checked)));
$("login").addEventListener("change", (e) => act(() => window.helper.openAtLogin(e.target.checked)));
$("signin-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const site = $("site").value.trim();
  if (site) act(() => window.helper.signin(site));
});
$("signin-done").addEventListener("click", () => act(() => window.helper.signinDone()));
$("open-app").addEventListener("click", () => window.helper.openApp());
$("disconnect").addEventListener("click", () => {
  if (confirm("Disconnect this computer? AI employees won't be able to use websites here until you connect it again.")) {
    act(() => window.helper.disconnect());
  }
});

window.helper.onState(render);
window.helper.state().then(render);
