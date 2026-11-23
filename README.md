# Autopilot

AI employees for early-stage founders, agencies and their teams. An **organization** has **departments** (Sales, Marketing, Customer Research...), each with one or more **AI employees**. You give an AI employee a **goal** with a clear finish line (book 20 qualified meetings, get 500 waitlist signups, find 150 investors who fund my stage) and give it a **budget**. It plans, does the work through connected apps or your own Chrome, asks before anything important, and logs every step so you can track its spend and performance like any employee's.

- **Set up in a minute**: a new organization only gives its name, website and a sentence about what it does. Autopilot reads the website (home page plus about, pricing, customers, careers...), researches the company on the web (funding, team, customers, news, competitors), then works out which functions matter most at its current stage. It sets up an AI employee for each one, with two or three suggested goals that fit what it found, and gives the reason for every suggestion. Suggested goals are drafts: you review, edit, start or remove them, and nothing is spent from a goal's budget until it starts. The research costs a few cents to about a dollar of Claude usage (shown on the setup page) and is paid by the organization, not any goal. It runs in the worker, so you can close the page. Admins can run it again from the Team page; it only adds what's missing. Without a Claude key, you start with a basic team instead.
- **See exactly what each AI employee will do**: every goal has a short step-by-step plan, and each step is marked *On its own* or *Asks first* (or *Off*). That mark comes from the same rules the policy engine enforces, so what you see is what happens, and you can change any step with one click. Research, reading app data and drafts happen on their own; sending, posting, publishing, spending, deleting and changing accounts ask the AI employee's department first, with the exact content shown and editable. Final clicks like Send, Post and Pay are blocked in code unless an approval covers them.
- **Starting a goal** takes two short steps: connect the tools its plan uses (an app connection, or signing in to the site once in Agent Chrome; you can also skip and it will ask when it gets there), then check what it will do on its own and what it will ask about, and change anything.
- **How budgets are worked out**: number of work sessions (how often it works × how long the goal runs) × cost of one session + any money it may spend on ads or purchases, rounded up. The cost of a session is your organization's own average once there are a few sessions, and about $0.30 until then (`EST_SESSION_COST_USD` in `.env`). Each goal shows this breakdown, and once it's running, what its sessions really cost and how far the rest of the budget goes. The budget is always a hard limit.
- **Your own tools (MCP)**: connect MCP servers (Streamable HTTP) in Settings, with an optional API key that's stored encrypted. Autopilot calls them itself rather than letting the model provider call them, so the same approvals apply: only tools the server marks read-only run on their own; everything else asks first. Servers on your own computer or network work by default; set `ALLOW_PRIVATE_MCP=false` when hosting Autopilot for others.
- **Organizations and departments**: the person who signs up creates the organization and picks its departments; each department starts with an AI employee (hire more any time). Invite people by email and put them in departments. Roles: **owner** and **admin** manage everything; **members** give goals to, and approve for, the AI employees in their own departments.
- **Approvals route to the right people**: when an AI employee needs a yes, the request goes to the people in its department (a Marketing agent asks the Marketing team) and they get an email. Anyone in that department can decide; if a department has nobody in it, admins decide. "Needs you" shows what's routed to you, and everything in the organization.
- **What it can do**: a library of 200+ goals across 15 areas (sales, marketing, customer research, product launch, fundraising, hiring, partnerships, customer success, finance, operations, PR, intel, agency work, founder leverage, admin). Each goal has a "counts as done when" finish line and a fit rating. Pick one and it pre-fills the setup, or describe your own.
- **Goals** have a finish line, a target, a hard budget and a check-in rhythm, and can be run for a client (for agencies). Autopilot works on them in **work sessions**: the planner reviews the results and writes a plan, the worker carries it out, then progress is recorded.
- **Work log, front and centre**: every session shows its plan, what it did, what it asked you, what was blocked, the outcome, how long it took and what it cost. "Highlights" shows the key actions; "Every step" also shows each page it opened, search it ran and note it made. There's a work log for each goal and one across all goals, with filters and search.
- **Approvals**: "I'm going to post this: can I go ahead?" Your options are **Go ahead**, **Approve & don't ask again** (for this goal, every goal in the department, or, for admins, the whole organization, on this app or site or anywhere, with a per-action limit for spending), **Edit then approve**, or **Don't do this** (with a reason the agent learns from). Without a standing permission, it asks every time.
- **Guardrails**: per action type, choose *Never* / *Ask me* / *Don't ask*. You can also block apps and websites, and add rules in your own words. Never-rules and blocks are enforced in code. Free-text rules are checked by a separate AI reviewer before every outgoing action, which is a strong check but not a guarantee. A set of built-in rules always applies: no fake engagement, no spam, no impersonation, never handle passwords. Changes reach a running agent immediately.
- **Budget** includes everything, mostly the agent's own Claude usage. Before each model call, its worst-case cost is reserved; after the call, the real cost is settled. When the money runs out the goal pauses, so overspending is impossible.
- **Agent Chrome**: your installed Chrome with its own profile. You sign in to each site once and stay signed in. The agent reads pages as text with numbered elements and acts on them. Final "commit" clicks (Post, Send, Buy, Delete...) are blocked unless an approved action covers them, and it never types passwords.
- **App connectors** (optional): 1,000+ apps through [Composio](https://composio.dev) with one-time OAuth. These are cheaper, more reliable and safer for your accounts than the browser. The agent prefers them when they're available and falls back to Agent Chrome.

## Run it locally

You need Python 3.11+, Node.js 18+ and Google Chrome. There is nothing else to install: the database is a local file (`data/autopilot.db`).

```bash
./scripts/dev.sh
```

The first run creates `.env` and installs everything, which takes a few minutes. Put your `ANTHROPIC_API_KEY` in `.env` (and optionally `COMPOSIO_API_KEY`), then run the script again. Open http://localhost:3000, sign in, and tell Autopilot your company's name, website and what it does. It researches the company and sets up your AI team with suggested goals; review them and start the ones you want. Invite teammates from Team or Settings → People. If you used Autopilot before organizations existed, your existing goals move into an organization for you on first sign-in. A Chrome window ("Agent Chrome") opens when the agent first uses the browser; sign in to sites there when it asks.

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

### Starting over with an email

To delete an account so the same email can sign up and go through onboarding again:

```bash
cd backend && .venv/bin/python -m app.cli delete-user someone@example.com
```

It shows what will be deleted and asks you to confirm. If that person was the only member of their organization, the organization and everything in it goes too; otherwise the team keeps its goals.

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
