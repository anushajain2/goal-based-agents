# Autopilot

**Become an AI-native company without teaching anyone to use AI.** Enter your website: Autopilot works out where AI helps each team and sets up **AI employees** for every function, each with real **goals** and a **budget**. Nobody has to learn prompting or figure out where AI fits; that bottleneck is gone. The AI does the work and shows it (every draft, step, source and reason), and **people keep the final say**: anything that goes out waits for a yes. Human accuracy at AI speed.

AI employees for early-stage founders, agencies and their teams. An **organization** has **departments** (Sales, Marketing, Customer Research...), each with one or more **AI employees**. You give an AI employee a **goal** with a clear finish line (book 20 qualified meetings, get 500 waitlist signups, find 150 investors who fund my stage) and give it a **budget**. It plans, does the work through connected apps or your own Chrome, asks before anything important, and logs every step so you can track its spend and performance like any employee's.

- **Set up in a minute**: a new organization only gives its name, website and a sentence about what it does. Autopilot reads the website (home page plus about, pricing, customers, careers...), researches the company on the web (funding, team, customers, news, competitors), then works out which functions matter most at its current stage. It sets up an AI employee for each one, with two or three suggested goals that fit what it found, and gives the reason for every suggestion. Suggested goals are drafts: you review, edit, start or remove them, and nothing is spent from a goal's budget until it starts. The research costs a few cents to about a dollar of Claude usage (shown on the setup page) and is paid by the organization, not any goal. It runs in the worker, so you can close the page. Admins can run it again from the Team page; it only adds what's missing. Without a Claude key, you start with a basic team instead.
- **What you're missing out on**: the last step of setup looks at what's public about the company (blog and social posting, reviews against competitors, search presence, comparison pages, careers page and how long roles stay open, press, visible website problems) and shows the biggest gaps with evidence and sources, e.g. "4 LinkedIn posts since June, most under 10 reactions; two competitors post weekly". Money estimates are ranges with the assumption stated, or left out. Each gap is tied to a goal: one setup already planned, or a new draft goal on the right team, with **Turn on** (or **Fix all**) right beside it; Home keeps a reminder until they're on. It also lists deeper checks that need a connected tool (HubSpot: leads nobody followed up; Stripe: failed payments never recovered; Search Console: searches you almost rank for). Company-level only: it never judges individual employees. It costs a few cents of Claude usage and its web searches (`backend/app/agent/opportunities.py`); if it fails, setup finishes anyway.
- **See exactly what each AI employee will do**: every goal has a short step-by-step plan, and each step is marked *On its own* or *Asks first* (or *Off*). That mark comes from the same rules the policy engine enforces, so what you see is what happens, and you can change any step with one click. Research, reading app data and drafts happen on their own; sending, posting, publishing, spending, deleting and changing accounts ask the AI employee's department first, with the exact content shown and editable. Final clicks like Send, Post and Pay are blocked in code unless an approval covers them.
- **Starting a goal** takes two short steps: connect the tools its plan uses (an app connection, or signing in to the site once in Agent Chrome; you can also skip and it will ask when it gets there), then check what it will do on its own and what it will ask about, and change anything.
- **Start the whole team in one click**: "Start my AI team" starts every suggested goal together, after one check of the tools to connect and what each will do on its own or ask about. Every suggested goal says what it delivers in its first week and starts with a one-week budget (usually $5-10, about $30 for a whole team). The estimate for the whole goal is kept alongside; add another week from the goal page once you've seen results.
- **Org chart**: the Team page shows who works with whom: you at the top, then for each function its team of people, its AI team lead, and its AI employees with their goals and this period's progress. Add or invite people to a team, choose who its AI employees ask, add departments and hire AI employees right on the chart. With nobody else on a team, its requests come to you. Click any goal to see, in one panel, what you get in the first week, each step marked automatic or waiting for an OK, and what it costs.
- **How budgets are worked out**: number of work sessions (how often it works × how long the goal runs) × cost of one session + any money it may spend on ads or purchases, rounded up. The cost of a session is your organization's own average once there are a few sessions, and about $0.30 until then (`EST_SESSION_COST_USD` in `.env`). Each goal shows this breakdown, and once it's running, what its sessions really cost and how far the rest of the budget goes. The budget is always a hard limit.
- **Your own tools (MCP)**: connect MCP servers (Streamable HTTP) in Settings, with an optional API key that's stored encrypted. Autopilot calls them itself rather than letting the model provider call them, so the same approvals apply: only tools the server marks read-only run on their own; everything else asks first. Servers on your own computer or network work by default; set `ALLOW_PRIVATE_MCP=false` when hosting Autopilot for others.
- **Organizations and departments**: the person who signs up creates the organization and picks its departments; each department starts with an AI employee (hire more any time). Invite people by email and put them in departments. Roles: **owner** and **admin** manage everything; **members** give goals to, and approve for, the AI employees in their own departments.
- **Ongoing goals with weekly, monthly or quarterly targets**: a goal is what a person on that team would own ("Grow newsletter signups from dispatchers"), with no number in its name. The number is the target for a period ("40 signups this week"). When a period ends it's marked hit or missed and the target carries on into the next one. The AI employee reviews its own results and proposes changes with its reasoning ("46 of 40 last week, so 80 next week, or 300 for the month"); you approve, edit the number, or keep things as they are.
- **AI team leads, always reviewing**: every team has an AI team lead that keeps reviewing how the team is doing (every week by default, or daily, every 3, 14 or 30 days, and whenever you click "Review the team now") and suggests what to change: updated targets, new goals, a new AI employee to take live with its first goal, pausing what isn't working, or restarting something paused. Before deciding it looks around with its own tools: web search and fetch (the market, competitors, the company's news), each goal's full history (targets, metrics, what sessions did and found, spending), and, when connected, the company's read-only database and GitHub issues. Each suggestion comes with its reasoning and goes to Needs you, routed to the person the team's AI employees ask; the lead's panel shows what it looked at and its sources. Nothing changes until a person approves. Its Claude usage (and web searches) is paid by the organization, a few cents per review, with a monthly limit per team ($5 by default).
- **Teams, not heads**: each function has a team of people. Its AI employees ask one person on it (the first person added, changeable on the org chart; until then, the owner), and any AI employee can be pointed at someone else. Requests never go to a random teammate.
- **Needs you is an inbox**: every approval, question, sign-in and app connection waiting on you, in a list with the full details beside it. Edit content before approving, leave a comment the AI employee reads ("go ahead, and mention our pricing page"), or answer a question. AI employees ask questions (with suggested answers) when they need something only your team knows; the work waits for the answer.
- **Routing follows the org chart**: an AI employee's requests go to one person: someone you pick for it, else the person its team's AI employees ask, else the owner. Add Maya to the Marketing team and Marketing's requests go to her, not you. Owners and admins can still step in from "Everyone". Heads (and anyone in a department) can hire AI employees into it and choose who they report to.
- **OKRs**: each AI employee has an objective, and each goal 2-3 measurable key results, from setup research or when the goal's plan is made. They show on the org chart, the AI employee's page and each goal.
- **Packs per type of company, and a catalog of AI employee roles**: 51 roles across 21 teams (Outbound SDR, Inbound, Deal desk, Proposals, Tenders, SEO, Paid ads, Lifecycle email, Creators, Events, PR, Community, Support, Help centre, CRM hygiene, Pricing, Data analyst, QA, Incident triage, Bookkeeping, Collections, Payables, FP&A, Procurement, Inventory, Merchandising, Recruiting, People ops, IT access, Compliance, Contracts, Executive assistant, Chief of staff, Investor relations, Fundraising, Grants, Client reporting, Client delivery and more). Each says what it does on its own, what it asks first, its tools and a starter goal (`backend/app/agent/packs.py`). Packs for B2B startups, solo/bootstrapped software, agencies, professional services and e-commerce/DTC brands (plus a general one) list the roles each type usually needs, by size. At setup, after reading the website and researching the company, Claude (the fast model, a fraction of a cent) decides which type of company it is and how big, with its reason. The planner gets that pack as a starting template plus the full catalog, and personalises it: which functions, which AI employees (up to three per team), their names, objectives and goals; it can also correct the type. If planning fails, "start with a basic team" builds the pack's starter team for the type Claude decided. Without a Claude key nothing can decide the type, so the starter team is the general one until the company is researched. The Goal ideas library also has Customer support, Revenue operations, Data & analytics, Engineering and E-commerce ideas. AI team leads suggest new hires from the same catalog.
- **A team that fits the company's size**: setup sizes the company from its headcount, revenue and funding (1-10, 11-50, 51-250 or 250+ people) and sets up at most 4, 6, 8 or 10 functions, saying why ("~24 people, EUR 9M Series A, 5 open roles"). A small startup gets mostly growth work; bigger companies also get back-office functions. Functions that will matter later are listed with when ("when enterprise customers send security reviews"); **Add now** adds one with its own goals, reusing the earlier research (no new web searches).
- **Back-office AI employees**: **Finance** (reconcile and categorise transactions, chase overdue invoices, burn and runway reports, find unused software; never pays or moves money without approval), **People & Hiring** (job posts, sourcing, screening against the role's stated requirements only, interview scheduling, onboarding plans; people make every hiring decision), **IT & Security** (app and access inventory, leftover accounts of people who left, security questionnaires, SOC 2 / ISO 27001 evidence; access changes need approval) and **Legal & Compliance** (contract summaries with risk flags, renewal tracking, compliance calendar; prepares work for a lawyer, never signs). Their tools (QuickBooks, Xero, Ramp, Greenhouse, Ashby, BambooHR, Gusto, Google Workspace, Okta, DocuSign...) connect as app connectors when you start them.
- **Product and Engineering AI employees**: setup suggests them too. The Product AI employee works like a PM: it watches your metrics and market (analytics apps, a read-only database, competitors on the web), explains sudden drops, and writes prioritised PRDs. You choose where PRDs go, on the org chart, the AI employee's page or when you start: to the product team for review first, or straight to the Engineering AI employee. Once a PRD is approved (or right away, if you turned review off), it becomes a "Build: ..." goal for the Engineering AI employee, which reads the code and opens a pull request on an `autopilot/...` branch. Merging always asks an engineer.
- **Code & data**: connect GitHub with "Sign in with GitHub" and pick a repository (when `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` are set), or with a fine-grained token for one repository (Contents and Pull requests read/write, Issues read), and a Postgres database (read-only: SELECT only, inside a read-only transaction with a time limit; use a read-only user or replica), on the Connections page or right from the Start screen. Secrets are stored encrypted. Analytics tools (Amplitude, Mixpanel, PostHog, Google Analytics...) connect as app connectors.
- **Connections, in one place**: the Connections page lists every tool your goals use (apps, websites, GitHub, your database), with which goals use it, what they do with it on their own and what needs your OK, and one button each: Connect (the app's own sign-in), Sign in (Agent Chrome), or Sign in with GitHub. Tools that live goals need but aren't connected come first, with a "3 of 10 ready" meter; Home and the setup page show the same checklist. App connections, MCP servers and Agent Chrome sign-ins live there too.
- **Connect when you start**: when you start goals (one or the whole team), Autopilot lists the tools their plans use (apps, sites, GitHub, database), each with what it does on its own and what needs your OK, and lets you connect each one in place. You can skip any; the AI employee asks when it gets there.
- **Goals by function**: the Goals page groups goals by department, with live goals kept apart from suggestions that haven't started.
- **What it can do**: a library of 200+ goals across 15 areas (sales, marketing, customer research, product launch, fundraising, hiring, partnerships, customer success, finance, operations, PR, intel, agency work, founder leverage, admin). Each goal has a "counts as done when" finish line and a fit rating. Pick one and it pre-fills the setup, or describe your own.
- **Goals** have a finish line, a target, a hard budget and a check-in rhythm, and can be run for a client (for agencies). Autopilot works on them in **work sessions**: the planner reviews the results and writes a plan, the worker carries it out, then progress is recorded.
- **Work log, front and centre**: every session shows its plan, what it did, what it asked you, what was blocked, the outcome, how long it took and what it cost. "Highlights" shows the key actions; "Every step" also shows each page it opened, search it ran and note it made. There's a work log for each goal and one across all goals, with filters and search.
- **Approvals**: "I'm going to post this: can I go ahead?" Your options are **Go ahead**, **Approve & don't ask again** (for this goal, every goal in the department, or, for admins, the whole organization, on this app or site or anywhere, with a per-action limit for spending), **Edit then approve**, or **Don't do this** (with a reason the agent learns from). Without a standing permission, it asks every time.
- **Guardrails**: per action type, choose *Never* / *Ask me* / *Don't ask*. You can also block apps and websites, and add rules in your own words. Never-rules and blocks are enforced in code. Free-text rules are checked by a separate AI reviewer before every outgoing action, which is a strong check but not a guarantee. A set of built-in rules always applies: no fake engagement, no spam, no impersonation, never handle passwords. Changes reach a running agent immediately.
- **Budget** includes everything, mostly the agent's own Claude usage. Before each model call, its worst-case cost is reserved; after the call, the real cost is settled. When the money runs out the goal pauses, so overspending is impossible.
- **Agent Chrome**: your installed Chrome with its own profile. You sign in to each site once and stay signed in. The agent reads pages as text with numbered elements and acts on them. Final "commit" clicks (Post, Send, Buy, Delete...) are blocked unless an approved action covers them, and it never types passwords.
- **App connectors**: 1,000+ apps through [Composio](https://composio.dev) with one-time OAuth. One Composio key (`COMPOSIO_API_KEY`, the platform's) serves every organization: each organization's connected accounts are kept separate. An organization can also paste its own Composio key on the Connections page (stored encrypted, no restart), e.g. when it hosts Autopilot itself or wants its own Composio account. These are cheaper, more reliable and safer for your accounts than the browser. The agent prefers them when they're available and falls back to Agent Chrome.

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
  app/connectors/  Composio hub (find / run actions, OAuth connect links), GitHub, read-only Postgres, MCP client
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
