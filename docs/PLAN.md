# Plan and decisions

## Product

| Decision | Why |
|---|---|
| **The campaign is the core object**: goal, primary metric, budget, daily cap, end date, check-in rhythm. | Mirrors ads-manager mental models; one number to optimize keeps the agent focused and the dashboard honest. |
| **Optimization cycles** (measure → review → strategy → act → record) on a schedule the agent can adjust. | It gives the agent a learning loop and the user a natural unit to read ("Cycle 3: threads get 4x engagement, shifting effort"). It also keeps each Claude conversation short, so costs stay low. |
| **Action types** with defaults: research and reading run freely, drafts are allowed, and engaging, publishing, messaging, account changes, deletes and spending **ask first**. | The user's requirement: ask before important actions until told otherwise. |
| **Approve & don't ask again** creates a standing permission. It covers one action type, for this campaign or all campaigns, on this app or site or anywhere. Spending permissions always carry a per-action limit. All of these can be revoked in Settings. | Trust is built gradually; spending is the riskiest category, so it never becomes unlimited. |
| **Edit then approve**: the user can change the exact content, and the agent must use the edited version verbatim. Declines carry an optional reason that goes back to the agent. | Approvals are about specific content, not just categories. |
| **Two layers of exclusions.** Hard blocks (action types, apps, sites) are enforced in code. Free-text rules are checked by a separate AI reviewer before each action, and the UI says that this is not a guarantee. | Honest about what can and cannot be guaranteed. |
| **Built-in rules** (no fake engagement, spam, impersonation or false claims; follow platform terms; never handle credentials). | "Grow followers at any cost" otherwise invites shortcuts that hit the number but get accounts banned. |
| **The activity log shows key actions only by default**, with "Everything" one click away. Details expand inline. | Readable at a glance, auditable in depth. |

## Technical

| Decision | Why |
|---|---|
| **Python backend (FastAPI, async SQLAlchemy) and a Next.js/TypeScript UI.** | As requested. The async Python stack handles many long-running agent runs well. |
| **SQLite by default, Postgres when scaling.** Same code; set `DATABASE_URL` to switch. | Running locally needs nothing installed (no Docker). Postgres adds parallel workers and instant live updates when hosting. |
| **Our own Claude tool loop** on the Messages API, not a hosted agent product. | An approval can take days, so each run must park and resume from the database across restarts. Every tool call must pass through our own guardrail, budget and logging pipeline. |
| **Append-only conversation history.** Guardrail changes mid-run are *appended* as system messages, and the tool list is fixed for a whole run. | Keeps the prompt cache warm (cheaper) and keeps Claude's earlier reasoning valid. |
| **Budget ledger with reservations.** Each model call reserves its worst-case cost first (in a short transaction holding a row lock), then settles at the real cost from `usage`. | It makes overspending impossible rather than unlikely, even with several workers. |
| **App connectors through two generic tools** (`app_find_actions`, `app_run_action`), not thousands of app-specific tools. | Keeps the prompt small and stable. Every call goes through our pipeline because we call Composio from our backend; letting the model reach app servers directly would bypass approvals. |
| **Autopilot Chrome = the user's Chrome with a dedicated profile, controlled over CDP** (Playwright `connect_over_cdp`). Chrome is started detached, so it survives worker restarts. | Chrome 136+ refuses remote control of the default profile, and a separate profile is safer anyway. Sign-ins persist, so each site needs only one login. |
| **Pages read as text with numbered elements**; screenshots only on demand and for approval previews. | Cheaper and more reliable than vision-only browsing, which matters because most of the budget is AI usage. |
| **The click guard runs in code**: commit buttons and submit keys need an authorization from an approved `browser_declare_action` (3 uses, 20 minutes). Password and card fields are never typed into. | Approving an *intent* is practical; approving every click is not. The guard stops the agent drifting from the approved intent, and stops prompt injection on a web page from getting past approvals. |
| **Manual sign-in mode** relaunches the profile without remote control. | Some sites (e.g. Google) refuse sign-ins in a remote-controlled browser. |
| **Job claiming that is safe with many workers** (`FOR UPDATE SKIP LOCKED` on Postgres), **live UI updates** via LISTEN/NOTIFY on Postgres or a light poll on SQLite. | Horizontal scaling (run more workers) and real-time updates without adding Redis or another queue. |

## Build order (done)

1. Data model, migrations, API
2. Budget ledger with AI cost metering
3. Policy engine, AI rule reviewer, approvals, standing permissions
4. Agent loop (persisted, resumable) and workers
5. Composio connector layer
6. Autopilot Chrome, browser tools, click guard, sign-in requests
7. UI: campaigns table, wizard, dashboard, activity log, approvals, guardrails, settings
8. Tests: ledger, policy, end-to-end cycles with a scripted model, real-Chrome browser tests

## Next

- First live run with real keys, then tune prompts and effort levels against real cycles.
- An extension mode, so the agent can use the user's everyday Chrome as well as the dedicated profile.
- Per-action outcome tracking (which posts drove followers or sales) to feed the strategy.
- A hosted deployment (organizations, departments, roles and routed approvals are in place).
