// The window's only way to talk to the app: a few named actions, nothing else.
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("helper", {
  state: () => ipcRenderer.invoke("state"),
  pair: (key, name) => ipcRenderer.invoke("pair", key, name),
  pause: (paused) => ipcRenderer.invoke("pause", paused),
  disconnect: () => ipcRenderer.invoke("disconnect"),
  signin: (url) => ipcRenderer.invoke("signin", url),
  signinDone: () => ipcRenderer.invoke("signin-done"),
  openAtLogin: (on) => ipcRenderer.invoke("open-login-at-start", on),
  openApp: () => ipcRenderer.invoke("open-app"),
  dismissLink: () => ipcRenderer.invoke("dismiss-link"),
  onState: (cb) => ipcRenderer.on("state", (_e, s) => cb(s)),
});
