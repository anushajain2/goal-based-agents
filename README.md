# Autopilot

Goal-based AI agents, with an interface like an ads manager. You set a **goal** (sell more of my product, grow my followers on X) and a **budget**. Agents then work toward the goal using any connected app or your own Chrome, and log every key action. They ask before anything important unless you have told them not to.

- **Campaigns** have a goal, a primary metric, a hard budget cap and a check-in rhythm. The agent works in *optimization cycles*: measure → review → adjust strategy → act → record results.
- **Activity log**: one line per key action (posted, declined, blocked, cycle summary, cost), with details on click.
- **Approvals**: "I'm going to post this: can I go ahead?" Your options are **Go ahead**, **Approve & don't ask again** (for this campaign or all campaigns, on this app or site or anywhere, with a per-action limit for spending), **Edit then approve**, or **Don't do this** (with a reason the agent learns from). Without a standing permission, it asks every time.
- **Guardrails**: per action type, choose *Never* / *Ask me* / *Don't ask*. You can also block apps and websites, and add rules in your own words. Never-rules and blocks are enforced in code. Free-text rules are checked by a separate AI reviewer before every outgoing action, which is a strong check but not a guarantee. A set of built-in rules always applies: no fake engagement, no spam, no impersonation, never handle passwords. Changes reach a running agent immediately.
- **Budget** includes everything, mostly the agent's own Claude usage. Before each model call, its worst-case cost is reserved; after the call, the real cost is settled. When the money runs out the campaign pauses, so overspending is impossible.
- **Agent Chrome**: your installed Chrome with its own profile. You sign in to each site once and stay signed in. The agent reads pages as text with numbered elements and acts on them. Final "commit" clicks (Post, Send, Buy, Delete...) are blocked unless an approved action covers them, and it never types passwords.
- **App connectors** (optional): 1,000+ apps through [Composio](https://composio.dev) with one-time OAuth. These are cheaper, more reliable and safer for your accounts than the browser. The agent prefers them when they're available and falls back to Agent Chrome.

## Run it locally

You need Python 3.11+, Node.js 18+ and Google Chrome. There is nothing else to install: the database is a local file (`data/autopilot.db`).

```bash
./scripts/dev.sh
```

The first run creates `.env` and installs everything, which takes a few minutes. Put your `ANTHROPIC_API_KEY` in `.env` (and optionally `COMPOSIO_API_KEY`), then run the script again. Open http://localhost:3000, create a campaign and launch it. A Chrome window ("Agent Chrome") opens when the agent first uses the browser; sign in to sites there when it asks.

To scale up later (many workers, hosting), set `DATABASE_URL` to a Postgres database. The code supports both.

<details><summary>Running the pieces by hand</summary>

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/alembic upgrade head
```

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload
```

```bash
cd backend && .venv/bin/python -m app.worker
```

```bash
cd frontend && npm install && npm run dev
```
</details>

### Tests

```bash
cd backend && .venv/bin/pytest
```

The tests use a temporary SQLite database; set `TEST_DATABASE_URL` to run them against Postgres. They drive the real agent loop against a scripted stand-in for Claude, and drive real Chrome (headless) against a local test page.

## Architecture

```
frontend/  Next.js + TypeScript + Tailwind        campaigns table, wizard, campaign dashboard, approvals, settings
backend/   FastAPI + SQLAlchemy (async); SQLite file locally, Postgres when you scale
  app/api/         REST API + Server-Sent Events for live updates
  app/worker.py    agent workers: schedule cycles, claim runs, recover stale runs
  app/agent/       runner (persisted, resumable Claude tool loop), executor (guardrail pipeline), tools, prompts
  app/services/    ledger (budget), policy (action types, blocks, grants), rule_check (AI reviewer), activity log
  app/connectors/  Composio hub (find / run actions, OAuth connect links)
  app/browser/     Agent Chrome (launch + CDP via Playwright, snapshots, click guard, manual sign-in mode)
```

Every outward action goes through one pipeline:

```
classify -> hard blocks -> AI rule check -> standing permission or approval request -> budget reservation -> execute -> log
```

A call that needs you **parks the run**: its state is saved in the database, and the run can wait hours or days and survive restarts. When you decide, a worker resumes it. Workers are stateless; on Postgres you scale by running more of them.

See [docs/PLAN.md](docs/PLAN.md) for the product and technical decisions and their reasons.

## Notes

- **Model:** Claude Opus 5.5 (`claude-opus-5-5`) with adaptive thinking. The main loop runs at `high` effort and the guardrail reviewer at `low`; both can be configured in `.env`. The request opts in to server-side refusal fallback, clearing of old tool results (to keep costs down), and lenient thinking-block replay. If the API ever rejects one of those options, the call is retried once without them.
- **Not yet exercised against the live Claude and Composio APIs.** The build environment had no keys. The agent loop, approvals, budget and browser guard are covered by tests using a scripted model and real Chrome. Expect small adjustments on the first real run.
- Composio usage fees are not counted in campaign budgets (they are an account-level subscription). Ad spend and purchases are counted at the maximum amount the agent declares, which you approve.
