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

BROWSER_TOOLS = [
    _tool(
        "browser_open",
        "Open a URL in Agent Chrome (the user's dedicated Chrome profile, where they are signed in to the "
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
        "Ask the user to sign in to a site in Agent Chrome. Use when a page shows you are signed out. You "
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
        "record_metric",
        "Record a measurement of a campaign metric (e.g. follower count, sales, clicks) after reading it "
        "from an app or page. Always record the primary metric at least once per cycle.",
        {
            "metric": {"type": "string"},
            "value": {"type": "number"},
            "source": {"type": "string", "description": "Where you read it, e.g. 'X profile page'."},
            "note": {"type": "string"},
        },
        ["metric", "value", "source"],
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


def all_tools(include_apps: bool) -> list[dict]:
    """Deterministic order (the prompt cache is a prefix match)."""
    tools = list(SERVER_TOOLS)
    if include_apps:
        tools += APP_TOOLS
    tools += BROWSER_TOOLS + CAMPAIGN_TOOLS
    return tools
