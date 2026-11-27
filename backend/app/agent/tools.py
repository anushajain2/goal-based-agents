"""Tool definitions given to Claude.

The tool list is fixed for the whole session and declared on the first request: changing
it mid-conversation would invalidate the prompt cache and earlier thinking blocks. App
connectors are reached through two generic tools (find / run) instead of loading
thousands of app-specific tools, which keeps the list stable and the prompt small.
"""

from app.services.policy import ACTION_TYPES

WRITE_ACTION_TYPES = [k for k in ACTION_TYPES if k not in ("research", "read_data")]


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5},
]
MAX_WEB_SEARCHES_PER_CALL = 5

APP_TOOLS = [
    _tool(
        "app_find_actions",
        "Search the app-connector catalog (1,000+ apps such as X/Twitter, LinkedIn, Gmail, Slack, HubSpot, "
        "Shopify, Notion, Google Ads) for actions matching a plain-English query. Returns action slugs, "
        "what kind of action each is, and its parameters. Use before app_run_action.",
        {
            "query": {"type": "string", "description": "What you want to do, e.g. 'post a tweet'."},
            "app": {"type": "string", "description": "Optional app slug to search within, e.g. 'twitter'."},
        },
        ["query"],
    ),
    _tool(
        "app_run_action",
        "Run one app-connector action. Reading actions run immediately. Anything that changes something "
        "(posting, messaging, spending, editing, deleting) goes through the user's guardrails and may wait "
        "for their approval; you will be told if it is waiting, approved, declined or blocked.",
        {
            "slug": {"type": "string", "description": "Action slug from app_find_actions."},
            "arguments": {"type": "object", "description": "Arguments matching the action's parameters."},
            "summary": {
                "type": "string",
                "description": "One plain-English line for the user's activity log, e.g. "
                "'Post launch-discount thread on X'.",
            },
            "spend_usd": {
                "type": "number",
                "description": "Required if the action spends money: the maximum it will cost, in USD.",
            },
        },
        ["slug", "arguments", "summary"],
    ),
    _tool("app_list_connections", "List the apps the user has connected and their status.", {}),
    _tool(
        "app_request_connection",
        "Ask the user to connect an app (one-time sign-in through the app's official login page). Use when "
        "an action needs an app that is not connected yet.",
        {
            "app": {"type": "string", "description": "App slug, e.g. 'linkedin'."},
            "reason": {"type": "string", "description": "Why you need it, in one sentence."},
        },
        ["app", "reason"],
    ),
]

GITHUB_TOOLS = [
    _tool("github_list_files", "List the files in the connected GitHub repository.",
          {"prefix": {"type": "string", "description": "Optional folder, e.g. 'src/'."}}),
    _tool("github_read_file", "Read one file from the repository.",
          {"path": {"type": "string"}, "ref": {"type": "string", "description": "Optional branch."}}, ["path"]),
    _tool("github_search_code", "Search the repository's code.", {"query": {"type": "string"}}, ["query"]),
    _tool("github_list_issues", "List the repository's issues (bugs, requests).",
          {"state": {"type": "string", "enum": ["open", "closed", "all"]}}),
    _tool(
        "github_open_pull_request",
        "Propose a code change: creates a new branch, commits the files (full new contents), and opens a pull "
        "request. Nothing reaches the main code until an engineer approves the merge. Keep changes small and "
        "focused; explain what and why in the body, and how you checked it.",
        {
            "title": {"type": "string"},
            "body": {"type": "string", "description": "What changed and why; link the PRD or issue."},
            "branch": {"type": "string", "description": "Short branch name, e.g. 'csv-export'."},
            "files": {"type": "array", "items": {
                "type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"], "additionalProperties": False}},
        },
        ["title", "body", "files"],
    ),
    _tool("github_merge_pull_request",
          "Ask to merge a pull request you opened. An engineer reviews it and approves first.",
          {"number": {"type": "integer"}, "summary": {"type": "string", "description": "Why it's ready to merge."}},
          ["number", "summary"]),
]

DATABASE_TOOLS = [
    _tool("db_query",
          "Run one read-only SQL query (Postgres) on the organization's database, e.g. to find why a metric "
          "dropped. Returns up to 200 rows. Writes are refused.",
          {"sql": {"type": "string"}, "purpose": {"type": "string", "description": "What you're checking, in a few words."}},
          ["sql", "purpose"]),
]

MCP_TOOLS = [
    _tool(
        "mcp_list_tools",
        "List the tools on the organization's custom MCP servers, with their parameters and whether each one "
        "only reads data or changes something.",
        {"server": {"type": "string", "description": "Optional server name to list just that server."}},
    ),
    _tool(
        "mcp_call_tool",
        "Call a tool on one of the organization's MCP servers. Tools that only read data run immediately; "
        "anything that changes something goes through the guardrails and may wait for a person's approval. "
        "You will be told if it is waiting, approved, declined or blocked.",
        {
            "server": {"type": "string", "description": "Server name from mcp_list_tools."},
            "tool": {"type": "string", "description": "Tool name."},
            "arguments": {"type": "object", "description": "Arguments matching the tool's input schema."},
            "summary": {"type": "string", "description": "One plain-English line for the work log."},
        },
        ["server", "tool", "arguments", "summary"],
    ),
]

BROWSER_TOOLS = [
    _tool(
        "browser_open",
        "Open a URL in Oton Chrome (the user's dedicated Chrome profile, where they are signed in to the "
        "sites they chose). Returns a page snapshot.",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _tool(
        "browser_snapshot",
        "Read the current page: URL, title, visible text and a numbered list of interactive elements. "
        "Element numbers change after the page changes, so take a fresh snapshot before acting.",
        {},
    ),
    _tool("browser_screenshot", "Take a screenshot of the current page when layout or images matter.", {}),
    _tool(
        "browser_click",
        "Click element [ref] from the latest snapshot. Final 'commit' buttons (Post, Send, Publish, Reply, "
        "Follow, Like, Buy, Pay, Delete, Confirm...) are blocked unless you pass an authorization_id from "
        "an approved browser_declare_action.",
        {
            "ref": {"type": "integer"},
            "authorization_id": {"type": "string"},
        },
        ["ref"],
    ),
    _tool(
        "browser_type",
        "Type text into element [ref] (replacing what is there). Set submit=true to press Enter afterwards; "
        "submitting a form needs an authorization_id unless it is a search box. Never use this for passwords.",
        {
            "ref": {"type": "integer"},
            "text": {"type": "string"},
            "submit": {"type": "boolean"},
            "authorization_id": {"type": "string"},
        },
        ["ref", "text"],
    ),
    _tool(
        "browser_press",
        "Press a key or shortcut, e.g. 'Escape', 'Tab', 'Enter', 'ControlOrMeta+Enter'. Keys that submit "
        "content need an authorization_id.",
        {"key": {"type": "string"}, "authorization_id": {"type": "string"}},
        ["key"],
    ),
    _tool(
        "browser_scroll",
        "Scroll the page.",
        {"direction": {"type": "string", "enum": ["up", "down"]}},
        ["direction"],
    ),
    _tool("browser_back", "Go back to the previous page.", {}),
    _tool(
        "browser_declare_action",
        "Before doing anything consequential in the browser (posting, replying, messaging, following, "
        "publishing, editing a profile, buying, deleting), declare it here with the exact content. It goes "
        "through the user's guardrails and possibly their approval. If allowed you get an authorization_id "
        "to pass to the final click/submit. One declaration covers one action (up to 3 commit clicks, e.g. "
        "Post then Confirm) within 20 minutes. If the user edited the content, use their version exactly.",
        {
            "action_type": {"type": "string", "enum": WRITE_ACTION_TYPES},
            "title": {"type": "string", "description": "One line for the activity log."},
            "site": {"type": "string", "description": "Domain where it happens, e.g. x.com"},
            "content": {"type": "string", "description": "The exact text that will be posted/sent, if any."},
            "details": {"type": "string", "description": "Anything else the user should know (target, audience...)."},
            "spend_usd": {"type": "number", "description": "Required for spend_money: maximum cost in USD."},
        },
        ["action_type", "title", "site"],
    ),
    _tool(
        "browser_request_login",
        "Ask the user to sign in to a site in Oton Chrome. Use when a page shows you are signed out. You "
        "never type passwords yourself. The login page is opened for them; you will be told when they are done.",
        {
            "site": {"type": "string", "description": "Domain, e.g. x.com"},
            "login_url": {"type": "string"},
            "reason": {"type": "string"},
        },
        ["site", "login_url", "reason"],
    ),
]

CAMPAIGN_TOOLS = [
    _tool(
        "record_channel_results",
        "For outreach: record the totals so far (not just this session) for each channel and opener you've used, "
        "e.g. LinkedIn with 'their funding round' as the opener: 40 sent, 6 replies, 2 meetings. Later sessions see "
        "which channel and opener book calls, and do more of that.",
        {"rows": {"type": "array", "items": {"type": "object", "properties": {
            "channel": {"type": "string", "description": "e.g. LinkedIn, Email, X, Instagram"},
            "opener": {"type": "string", "description": "The angle the first message led with, a few words"},
            "sent": {"type": "integer"}, "replies": {"type": "integer"}, "meetings": {"type": "integer"}},
            "required": ["channel", "opener", "sent", "replies", "meetings"], "additionalProperties": False}}},
        ["rows"],
    ),
    _tool(
        "record_metric",
        "Record a measurement of a campaign metric (e.g. meetings booked, signups, sales). Always record the "
        "primary metric at least once per cycle, as a running total since the goal started (targets count "
        "progress from it). Read it from the source of truth whenever one is connected (the CRM, Stripe, "
        "analytics, the database) in this session, and say so with how='read_from_tool'; numbers you count "
        "yourself or estimate are shown to people as reported, not measured.",
        {
            "metric": {"type": "string"},
            "value": {"type": "number"},
            "how": {"type": "string", "enum": ["read_from_tool", "counted", "estimate"]},
            "tool": {"type": "string", "description": "For read_from_tool: the app or data you read it from, e.g. 'hubspot'."},
            "source": {"type": "string", "description": "Where exactly, e.g. 'HubSpot meetings report'."},
            "note": {"type": "string"},
        },
        ["metric", "value", "how", "source"],
    ),
    _tool(
        "update_strategy",
        "Replace the campaign's strategy: a short plain-English plan (markdown bullet points, under 250 "
        "words) the user sees on the dashboard. Update it when you learn something that changes the plan.",
        {"strategy": {"type": "string"}},
        ["strategy"],
    ),
    _tool(
        "notify_user",
        "Add an important note to the user's activity log (an insight, a problem, a recommendation). "
        "Use sparingly; routine steps are logged automatically.",
        {"message": {"type": "string"}},
        ["message"],
    ),
    _tool(
        "submit_work",
        "Hand in a finished piece of work: a PRD, an analysis (e.g. why a metric dropped, competitors, trends) "
        "or a report. It goes to the person you report to for review; an approved PRD may then go to another "
        "AI employee to build. Write it in Markdown, complete and self-contained.",
        {
            "kind": {"type": "string", "enum": ["prd", "analysis", "report"]},
            "title": {"type": "string"},
            "summary": {"type": "string", "description": "Two sentences: the finding or proposal, and why it matters."},
            "content": {"type": "string", "description": "The full document in Markdown."},
        },
        ["kind", "title", "summary", "content"],
    ),
    _tool(
        "propose_change",
        "Propose a change to your goal for the person you report to to approve: a new target (e.g. you "
        "hit this week's 15 signups early, so 30 next week, or 100 for the month) or pausing the goal "
        "when it isn't worth the budget. Explain your reasoning with the numbers. Nothing changes until "
        "they approve; only one proposal can wait at a time. Carry on with your work meanwhile.",
        {
            "change": {"type": "string", "enum": ["target", "pause"]},
            "target": {"type": "number", "description": "For a new target: the number to reach in the period."},
            "period": {"type": "string", "enum": ["week", "month", "quarter"],
                       "description": "For a new target: the period it covers."},
            "reasoning": {"type": "string", "description": "Two or three sentences: what happened and why this change is better."},
        },
        ["change", "reasoning"],
    ),
    _tool(
        "ask_user",
        "Ask the person you report to a question only they can answer (a fact, a preference, a choice "
        "between options), e.g. 'Which 5 customers are happiest?' Not for permission: actions already ask "
        "for approval by themselves. The session pauses until they answer, so ask everything you need at "
        "once, and only when it matters.",
        {
            "question": {"type": "string", "description": "One clear question."},
            "why": {"type": "string", "description": "One sentence: why you need it and how it helps the goal."},
            "options": {"type": "array", "items": {"type": "string"},
                        "description": "Optional short answers they can pick from."},
        },
        ["question", "why"],
    ),
    _tool(
        "finish_cycle",
        "End this optimization cycle. Give a 1-3 sentence summary of what you did and learned, and when to "
        "check in next.",
        {
            "summary": {"type": "string"},
            "next_check_in_hours": {"type": "number", "description": "Between 0.5 and 72."},
        },
        ["summary", "next_check_in_hours"],
    ),
]


VIDEO_TOOLS = [
    _tool(
        "make_launch_video",
        "Make a ~20-second launch video from a website (by default the company's own): it looks at the site, "
        "writes the story (a hook, what it is, 2-3 real screens zoomed in, the call to action), renders it with "
        "motion and music, and writes the copy to post it with. Takes about 10 minutes; the video then goes to "
        "the Reviewer to watch and approve, and you'll see it in the work log. It doesn't post anything: once "
        "approved, post it (with the approved copy) as a separate step. One at a time per goal.",
        {
            "url": {"type": "string", "description": "The site to make it from. Leave out for the company's website."},
            "format": {"type": "string", "enum": ["landscape", "vertical", "square"],
                       "description": "landscape (16:9) for the website, YouTube, LinkedIn and X; vertical (9:16) for "
                       "Reels, Shorts and TikTok; square for feeds. Default landscape."},
            "notes": {"type": "string", "description": "Optional: what to emphasise, who it's for, what to leave out."},
        },
    ),
]


def all_tools(include_apps: bool, include_mcp: bool = False, tool_sets: list[str] | tuple = (),
              browser: bool = True) -> list[dict]:
    """Deterministic order (the prompt cache is a prefix match)."""
    tools = list(SERVER_TOOLS)
    if include_apps:
        tools += APP_TOOLS
    if include_mcp:
        tools += MCP_TOOLS
    if "github" in tool_sets:
        tools += GITHUB_TOOLS
    if "database" in tool_sets:
        tools += DATABASE_TOOLS
    if "video" in tool_sets:
        tools += VIDEO_TOOLS
    if browser:
        tools += BROWSER_TOOLS
    tools += CAMPAIGN_TOOLS
    return tools
