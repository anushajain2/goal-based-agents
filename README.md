# Autopilot

An AI employee for early-stage founders and agency owners. You hire it for a **goal** with a clear finish line (book 20 qualified meetings, get 500 waitlist signups, find 150 investors who fund my stage) and give it a **budget**. It plans, does the work through connected apps or your own Chrome, asks before anything important, and logs every step so you can track its spend and performance like any employee's.

- **What it can do**: a library of 200+ goals across 15 areas (sales, marketing, customer research, product launch, fundraising, hiring, partnerships, customer success, finance, operations, PR, intel, agency work, founder leverage, admin). Each goal has a "counts as done when" finish line and a fit rating. Pick one and it pre-fills the setup, or describe your own.
- **Goals** have a finish line, a target, a hard budget and a check-in rhythm, and can be run for a client (for agencies). Autopilot works on them in **work sessions**: the planner reviews the results and writes a plan, the worker carries it out, then progress is recorded.
- **Work log, front and centre**: every session shows its plan, what it did, what it asked you, what was blocked, the outcome, how long it took and what it cost. "Highlights" shows the key actions; "Every step" also shows each page it opened, search it ran and note it made. There's a work log for each goal and one across all goals, with filters and search.
- **Approvals**: "I'm going to post this: can I go ahead?" Your options are **Go ahead**, **Approve & don't ask again** (for this goal or all goals, on this app or site or anywhere, with a per-action limit for spending), **Edit then approve**, or **Don't do this** (with a reason the agent learns from). Without a standing permission, it asks every time.
- **Guardrails**: per action type, choose *Never* / *Ask me* / *Don't ask*. You can also block apps and websites, and add rules in your own words. Never-rules and blocks are enforced in code. Free-text rules are checked by a separate AI reviewer before every outgoing action, which is a strong check but not a guarantee. A set of built-in rules always applies: no fake engagement, no spam, no impersonation, never handle passwords. Changes reach a running agent immediately.
- **Budget** includes everything, mostly the agent's own Claude usage. Before each model call, its worst-case cost is reserved; after the call, the real cost is settled. When the money runs out the goal pauses, so overspending is impossible.
- **Agent Chrome**: your installed Chrome with its own profile. You sign in to each site once and stay signed in. The agent reads pages as text with numbered elements and acts on them. Final "commit" clicks (Post, Send, Buy, Delete...) are blocked unless an approved action covers them, and it never types passwords.
- **App connectors** (optional): 1,000+ apps through [Composio](https://composio.dev) with one-time OAuth. These are cheaper, more reliable and safer for your accounts than the browser. The agent prefers them when they're available and falls back to Agent Chrome.

## Run it locally

You need Python 3.11+, Node.js 18+ and Google Chrome. There is nothing else to install: the database is a local file (`data/autopilot.db`).

```bash
./scripts/dev.sh
```

The first run creates `.env` and installs everything, which takes a few minutes. Put your `ANTHROPIC_API_KEY` in `.env` (and optionally `COMPOSIO_API_KEY`), then run the script again. Open http://localhost:3000, sign in, pick a goal from "What it can do" and start it. If you used Autopilot before accounts existed, the first account you create takes over your existing goals. A Chrome window ("Agent Chrome") opens when the agent first uses the browser; sign in to sites there when it asks.

To scale up later (many workers, hosting), set `DATABASE_URL` to a Postgres database. The code supports both.

### Signing in

There are no passwords. People sign in with **Google** or with a **6-digit code sent to their email**; the first sign-in with a new email creates the account.

- **Email codes** work out of the box. Until you set up email sending, the code is printed in the terminal running `./scripts/dev.sh`. To email codes, fill in the `SMTP_*` settings in `.env`. Any SMTP service works, e.g. Gmail with an app password, Resend, Postmark or Amazon SES.
- **Google** is optional. In Google Cloud Console, go to APIs & Services → Credentials → Create OAuth client ID → Web application. Add the authorised redirect URI `http://localhost:3000/api/auth/google/callback` (your real address once hosted), then put the client ID and secret in `.env`. The "Continue with Google" button appears once they're set.

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
frontend/  Next.js + TypeScript + Tailwind        public landing page and login; signed-in app: home, goals, goal pages with work sessions,
                                                 work log, needs-you inbox, use-case library, settings
backend/   FastAPI + SQLAlchemy (async); SQLite file locally, Postgres when you scale
  app/auth.py      passwordless sign-in: Google (OAuth + PKCE) and emailed one-time codes; httpOnly session cookies
  app/api/         REST API + Server-Sent Events for live updates; every endpoint scoped to the signed-in user
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

- **Models:** each job uses the cheapest Claude model that does it well. **Claude Opus 5.5** plans each work session (one call per session). **Claude Sonnet 5.5** carries out the steps (most calls). **Claude Haiku 5.5** checks each outgoing action against your guardrails. Every model, and each one's effort level, can be changed in `.env`. Requests opt in to refusal fallback, clearing of old tool results (to keep costs down) and short progress notes for the work log. If the API rejects one of those options, the call is retried once without them.
- **Not yet exercised against the live Claude and Composio APIs.** The build environment had no keys. The agent loop, approvals, budget and browser guard are covered by tests using a scripted model and real Chrome. Expect small adjustments on the first real run.
- Composio usage fees are not counted in goal budgets (they are an account-level subscription). Ad spend and purchases are counted at the maximum amount the agent declares, which you approve.
