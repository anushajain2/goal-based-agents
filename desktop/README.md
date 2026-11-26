# Oton Helper (desktop app)

Lets AI employees use websites in a separate Chrome window on your computer, when Oton runs
in the cloud. Install it, connect it once from Oton (Connections → Desktop helper), and it
sits in the menu bar / system tray.

- **Your own browser is never touched.** The helper starts Chrome with its own profile. AI employees
  only reach sites someone signed in to in that window.
- **It never takes over your screen.** By default the AI's Chrome is invisible (no window at all). Or
  choose "In the background" to watch it: it opens behind your windows and never comes to the front by
  itself. Each work session gets its own window, opened without coming forward. Only "Sign in to a site" opens a normal window,
  because you asked for it. Website steps wait while it's open, and closing it ends signing in.
- **The rules stay on the server.** Reading pages, clicking, and the guard that makes "Post", "Send",
  "Buy" and similar wait for a person's approval all run in Oton. The helper only carries
  messages between Oton and Chrome.
- **It connects out; nothing listens.** One outgoing secure WebSocket to Oton. Chrome's control
  port only listens on 127.0.0.1.
- **Laptop closed?** Website steps wait and run when it's back; everything else keeps going.
- **Pause** any time from the tray or window. **Disconnect** here or in Oton; removing it in
  Oton revokes its token at once.

## How it fits together

```
 Oton worker ──(private network)── Oton API ◀──wss── Helper ──localhost── Chrome (own profile)
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
npm test          # core tests against a fake Oton and a fake Chrome
npm start         # the app (Electron)
```

Without Electron, for example on a server:

```bash
node src/cli.js pair "<pairing link from Oton>" --name "Office iMac"
node src/cli.js run            # add --headless on a machine without a screen
```

Running Oton locally on port 8000 with `AGENT_CHROME=false` lets you try the helper against
your own backend (the pairing link points at http://localhost:8000).

## Release installers

When `version` in `desktop/package.json` hasn't been released yet, pushing to `main` makes GitHub Actions
build macOS (Apple silicon and Intel), Windows and Linux installers and publish them as release
`helper-v<version>`. The **Download** button in Oton points to the latest release. Other changes
under `desktop/` only build (to check they still work).

For the next release, bump `version` in `package.json` and push. Without signing certificates, macOS asks
people to right-click → Open the first time, and Windows shows "More info → Run anyway". Add the
secrets listed in `.github/workflows/desktop.yml` to sign builds: an Apple Developer ID for Mac and a
code-signing certificate for Windows.
