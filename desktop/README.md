# Autopilot Helper (desktop app)

Lets AI employees use websites in a separate Chrome window on your computer, when Autopilot runs
in the cloud. Install it, connect it once from Autopilot (Connections → Desktop helper), and it
sits in the menu bar / system tray.

- **Your own browser is never touched.** The helper starts Chrome with its own profile. AI employees
  only reach sites someone signed in to in that window.
- **The rules stay on the server.** Reading pages, clicking, and the guard that makes "Post", "Send",
  "Buy" and similar wait for a person's approval all run in Autopilot. The helper only carries
  messages between Autopilot and Chrome.
- **It connects out; nothing listens.** One outgoing secure WebSocket to Autopilot. Chrome's control
  port only listens on 127.0.0.1.
- **Laptop closed?** Website steps wait and run when it's back; everything else keeps going.
- **Pause** any time from the tray or window. **Disconnect** here or in Autopilot; removing it in
  Autopilot revokes its token at once.

## How it fits together

```
 Autopilot worker ──(private network)── Autopilot API ◀──wss── Helper ──localhost── Chrome (own profile)
   browser tools,                         relay per                  starts Chrome,
   click guard, approvals                 session channel            passes DevTools messages
```

Files:
- `src/core.js`: pairing, the connection, channels to Chrome, Pause, reconnecting (plain Node)
- `src/chrome.js`: finding and starting Chrome with the helper's own profile
- `src/main.js`, `src/preload.js`, `src/ui/`: the Electron app (tray, window, `autopilot://` links)
- `src/cli.js`: the same helper without a window, for testing and Linux machines

## Develop

```bash
cd desktop
npm install
npm test          # core tests against a fake Autopilot and a fake Chrome
npm start         # the app (Electron)
```

Without Electron, for example on a server:

```bash
node src/cli.js pair "<pairing link from Autopilot>" --name "Office iMac"
node src/cli.js run            # add --headless on a machine without a screen
```

Running Autopilot locally on port 8000 with `AGENT_CHROME=false` lets you try the helper against
your own backend (the pairing link points at http://localhost:8000).

## Release installers

Push a tag and GitHub Actions builds macOS (Apple silicon and Intel), Windows and Linux installers
and attaches them to a GitHub release. The **Download** button in Autopilot points to that release.

```bash
git tag helper-v0.1.0 && git push origin helper-v0.1.0
```

Bump `version` in `package.json` first for later releases. Without signing certificates, macOS asks
people to right-click → Open the first time, and Windows shows "More info → Run anyway". Add the
secrets listed in `.github/workflows/desktop.yml` to sign builds: an Apple Developer ID for Mac and a
code-signing certificate for Windows.
