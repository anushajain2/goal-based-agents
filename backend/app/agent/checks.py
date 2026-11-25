"""The catalog of things Autopilot can check about a company, to show what it's missing out on.

Each check says which team would fix it, how it's checked, and which types of company it suits.
At setup the company's type (decided by Claude, see packs.py) narrows the catalog, then Claude
picks the checks most worth running for this particular company.

How a check is run:
  search  real web searches for what a customer would type (never the company's name), and
          where the company ranks against its competitors
  ai      what an AI assistant recommends when asked those same questions
  web     reading public pages: the company's site, reviews, job posts, directories, competitors
  tool    needs a connected tool (the company's own data); offered as a deeper check
  measure measured directly from data sources (app/services/presence), always run when available
"""

from __future__ import annotations

from dataclasses import dataclass

ALL = ("startup", "solo_saas", "agency", "services", "ecommerce", "general")
SOFTWARE = ("startup", "solo_saas")
B2B = ("startup", "solo_saas", "agency", "services", "general")


@dataclass(frozen=True)
class Check:
    key: str
    team: str  # department kind that fixes it
    title: str
    how: str  # what's looked at
    method: str = "web"  # search | ai | web | tool
    packs: tuple[str, ...] = ALL
    tool: str | None = None  # for method "tool": the catalog tool it needs
    # For "tool" checks: the goal its team's AI employee works on once the tool is connected.
    goal: str = ""
    goal_how: str = ""


CHECKS: list[Check] = [
    # --- Being found: search and AI answers --------------------------------------------------------
    Check("search_rank", "marketing", "Where you rank for what customers search",
          "Searches a customer would type (not your name) and where you rank against competitors", "search"),
    Check("ai_answers", "marketing", "Whether AI assistants recommend you",
          "Ask an AI assistant those same questions and see who it recommends", "ai"),
    Check("comparison_searches", "sales", "'Alternative to' and 'X vs Y' searches",
          "Searches for competitor alternatives and comparisons, and whether you have pages for them", "search", SOFTWARE),
    Check("local_listing", "marketing", "Maps and local listings",
          "Google Business-style listing, reviews and photos against nearby competitors", "web",
          ("services", "general", "ecommerce")),
    Check("directories", "marketing", "Directories buyers use",
          "G2, Capterra, Clutch, Thomasnet, Europages, Yelp and industry directories where competitors are listed"),
    Check("app_marketplaces", "partnerships", "App marketplaces",
          "HubSpot, Salesforce, Shopify, Slack and other marketplaces where competitors are listed", "web", SOFTWARE),
    Check("content_gaps", "marketing", "Topics competitors cover and you don't",
          "Guides, use cases and questions competitors have pages for"),
    Check("technical_seo", "engineering", "Website basics search engines need",
          "Page titles and descriptions, sitemap, robots.txt, broken or duplicate pages"),

    # --- Content and social ------------------------------------------------------------------------
    Check("social_cadence", "marketing", "How often you post, and the traction",
          "LinkedIn, X and Instagram posting frequency and engagement against competitors"),
    Check("blog_freshness", "marketing", "Blog and news going stale", "Date of the latest blog or news post"),
    Check("newsletter", "marketing", "No way to stay in touch", "Newsletter or email signup on the site"),
    Check("video", "marketing", "Video", "Demo, tutorial and customer videos against competitors",
          "web", ("startup", "solo_saas", "ecommerce", "general")),
    Check("leadership_voice", "marketing", "Company voice in the industry",
          "Talks, podcasts, guest articles and posts from the company's leaders (company-level)",
          "web", ("startup", "agency", "services")),
    Check("press", "pr", "Press and announcements",
          "Last press mention, and launches or milestones nobody announced"),
    Check("awards", "pr", "Industry awards", "Awards and rankings competitors won or entered",
          "web", ("agency", "services", "general")),
    Check("community", "community", "Where your customers gather",
          "Communities, groups and events your customers use where you're absent", "web", SOFTWARE + ("ecommerce",)),

    # --- Turning visitors into customers -----------------------------------------------------------
    Check("cta_clarity", "sales", "How easy it is to buy or book",
          "A clear buy, demo or quote action on the home page; steps and form fields to get there"),
    Check("pricing_clarity", "sales", "Pricing or quote clarity",
          "A pricing page or a clear way to get a quote, against competitors"),
    Check("trust_signals", "marketing", "Proof on the website",
          "Customer logos, testimonials, certifications and numbers shown on the site"),
    Check("case_studies", "marketing", "Customer stories", "Case studies against your number of customers and competitors",
          "web", B2B),
    Check("languages", "marketing", "Languages for the markets you sell in",
          "Website languages against the countries you serve or hire in"),
    Check("website_freshness", "engineering", "Visible website problems",
          "Broken pages, old copyright years, stale dates, missing basics like a status page"),

    # --- Reputation ---------------------------------------------------------------------------------
    Check("review_volume", "support", "Reviews where buyers look",
          "Review counts and ratings on the platforms buyers use, against competitors"),
    Check("unanswered_reviews", "support", "Reviews nobody answered", "Recent negative reviews without a reply"),
    Check("review_themes", "product", "What reviews keep complaining about", "Recurring themes across public reviews"),
    Check("employer_reviews", "hiring", "Employer reviews",
          "Glassdoor or Kununu rating and recurring themes (company-level, never about individuals)",
          "web", ("startup", "agency", "services", "ecommerce", "general")),

    # --- Selling -------------------------------------------------------------------------------------
    Check("trigger_events", "sales", "Prospects with a reason to buy now",
          "Companies in your market that just raised, hired for a relevant role or expanded", "web", B2B),
    Check("tenders", "sales", "Public tenders you could bid on",
          "Open public tenders and RFPs that match what you offer", "web", ("services", "agency", "general")),
    Check("trade_shows", "marketing", "Events competitors exhibit at",
          "Upcoming trade shows and conferences in your industry", "web", ("startup", "general", "services")),
    Check("partner_channels", "partnerships", "Partners and resellers",
          "Integrations, resellers and referral partners competitors work with", "web", B2B),
    Check("referral_program", "success", "Referral or affiliate program",
          "Whether customers are rewarded for referrals, against competitors", "web", ("ecommerce", "solo_saas", "startup")),

    # --- Product -------------------------------------------------------------------------------------
    Check("changelog", "product", "Showing what's new", "Release notes or changelog and how often it's updated", "web", SOFTWARE),
    Check("feature_gaps", "product", "Features competitors advertise",
          "Features on competitors' sites and pricing pages that you don't show", "web", SOFTWARE + ("ecommerce",)),
    Check("integrations", "product", "Integrations buyers expect", "Integrations competitors list that you don't", "web", SOFTWARE),
    Check("help_center", "support", "Help centre and docs", "Whether customers can help themselves, and how current it is",
          "web", SOFTWARE + ("ecommerce",)),
    Check("security_page", "it", "Security and compliance page",
          "SOC 2, ISO 27001 and GDPR information for buyers' security reviews", "web", SOFTWARE + ("services",)),

    # --- People --------------------------------------------------------------------------------------
    Check("open_roles", "hiring", "Roles open too long", "How long job posts have been up"),
    Check("job_ads", "hiring", "Job ads that put candidates off", "Pay, clarity about the role and the product, inclusive wording"),
    Check("missing_functions", "hiring", "Functions a company your size usually has",
          "From the careers and team pages: functions you're missing or hiring for late (never about individuals)"),
    Check("careers_page", "hiring", "Careers page", "Whether there is one, and what it says about working there"),

    # --- Money and compliance ------------------------------------------------------------------------
    Check("price_position", "finance", "Price against competitors", "Public prices compared, when both are public"),
    Check("payment_options", "finance", "How customers can pay", "Payment methods, financing and invoicing terms against competitors",
          "web", ("ecommerce", "services")),
    Check("grants", "finance", "Grants and incentives you may qualify for",
          "Public grants, subsidies and R&D tax credits for your industry and country", "web", ("startup", "general", "solo_saas")),
    Check("legal_basics", "legal", "Legal basics on the website",
          "Privacy policy, cookie consent, terms, imprint (EU) and accessibility statement"),
    Check("certifications", "operations", "Certifications competitors show",
          "ISO 9001 and industry certifications buyers ask for", "web", ("general", "services")),
    Check("b2b_platforms", "sales", "B2B buying platforms",
          "Procurement and sourcing platforms (Thomasnet, Europages, Alibaba) where buyers look for suppliers",
          "web", ("general",)),

    # --- Online stores -------------------------------------------------------------------------------
    Check("product_pages", "store", "Product pages that don't sell",
          "Photos, descriptions, sizing and reviews on product pages", "web", ("ecommerce",)),
    Check("shipping_returns", "store", "Shipping and returns", "Delivery speed, costs and return policy against competitors",
          "web", ("ecommerce",)),
    Check("marketplaces", "store", "Marketplaces you're not on", "Amazon, Etsy, Zalando and others where competitors sell",
          "web", ("ecommerce",)),
    Check("agency_portfolio", "marketing", "Portfolio going stale", "Date and relevance of the latest work shown", "web", ("agency",)),

    # --- Measured directly (app/services/presence) --------------------------------------------------
    Check("google_by_country", "marketing", "Google rank in each market",
          "Real Google results for customer searches in up to 3 countries, with competitors above you", "measure"),
    Check("search_volume", "marketing", "How many people search, and how hard it is to rank",
          "Monthly searches and keyword difficulty per country", "measure"),
    Check("ai_overview", "marketing", "Google's AI Overview", "Whether Google's AI answer cites you or competitors", "measure"),
    Check("assistants", "marketing", "ChatGPT, Perplexity and Gemini", "Who each AI assistant recommends for your customers' questions", "measure"),
    Check("page_speed", "engineering", "Mobile speed", "Google PageSpeed score and load time, against competitors", "measure"),
    Check("accessibility", "engineering", "Accessibility", "Google Lighthouse accessibility score", "measure"),
    Check("email_auth", "it", "Email authentication", "SPF, DKIM and DMARC records, so email lands in inboxes", "measure"),
    Check("site_security", "it", "Website security", "HTTPS, certificate and domain expiry, HSTS", "measure"),
    Check("tracking", "marketing", "Tracking basics", "Analytics, ad pixels and cookie consent on the home page", "measure"),
    Check("site_tools", "sales", "Chat and booking", "Live chat and online booking, against competitors", "measure"),
    Check("broken_links", "engineering", "Broken links", "A crawl of the site with every link checked", "measure"),
    Check("maps_rank", "marketing", "Google Maps results by city", "Where you show up in the map results in up to 3 cities",
          "measure", ("services", "general", "ecommerce", "agency")),
    Check("competitor_ads", "marketing", "Ads competitors run", "Google Ads Transparency and Meta Ad Library counts", "measure"),
    Check("app_ratings", "product", "App store ratings", "App Store and Google Play rating and number of ratings", "measure"),
    Check("youtube_channel", "marketing", "YouTube channel", "Subscribers and the latest video, against competitors", "measure"),
    Check("ai_knowledge", "pr", "What AI assistants learn from", "Wikipedia, Wikidata and Reddit mentions, against competitors", "measure"),
    Check("authority", "marketing", "Domain authority", "Open PageRank authority, against competitors", "measure"),
    Check("popularity", "marketing", "Site popularity", "Rank among the most visited sites (Tranco), against competitors", "measure"),

    # --- Connect to unlock: checks on the company's own data, by team ------------------------------
    Check("lead_followup", "sales", "Leads nobody followed up", "Leads and deals left without a reply", "tool", B2B, "hubspot",
          "Follow up every lead and stalled deal", "Find leads and deals in HubSpot with no reply or activity, and draft a follow-up for each"),
    Check("lead_followup_sf", "sales", "Stalled deals", "Deals with no activity for weeks", "tool", B2B, "salesforce",
          "Restart stalled deals", "Find deals in Salesforce with no activity for 3+ weeks and draft the next step for each"),
    Check("inbox_unanswered", "sales", "Inbound emails left unanswered", "Prospect and customer emails waiting for a reply",
          "tool", ALL, "gmail", "Answer every inbound email within a day",
          "Find prospect and customer emails waiting for a reply, and draft an answer for each"),
    Check("social_exact", "marketing", "Exact posting and engagement", "Your company page's real posting frequency and engagement",
          "tool", ALL, "linkedin", "Post on LinkedIn every week", "Measure what's worked on the company page and draft next week's posts"),
    Check("near_miss_searches", "marketing", "Searches you almost rank for", "Queries where you're on page 2", "tool", ALL,
          "searchconsole", "Win the searches you almost rank for",
          "Find searches where you're on page 2 in Search Console and improve or write the page for each"),
    Check("failed_payments", "finance", "Failed payments never recovered", "Failed charges and quiet churn", "tool",
          SOFTWARE + ("ecommerce",), "stripe", "Recover failed payments",
          "Find failed charges in Stripe that were never recovered and draft a friendly payment reminder for each"),
    Check("overdue_invoices", "finance", "Overdue invoices nobody chased", "Unpaid invoices by age", "tool", B2B, "quickbooks",
          "Collect overdue invoices", "List unpaid invoices by age in QuickBooks and draft a reminder for each, firmer as they get older"),
    Check("overdue_invoices_xero", "finance", "Overdue invoices nobody chased", "Unpaid invoices by age", "tool", B2B, "xero",
          "Collect overdue invoices", "List unpaid invoices by age in Xero and draft a reminder for each, firmer as they get older"),
    Check("unused_software", "finance", "Software you pay for and don't use", "Duplicate and unused subscriptions", "tool", ALL, "ramp",
          "Cut unused software spend", "Find duplicate and unused software subscriptions in Ramp and list what to cancel, with the savings"),
    Check("stale_access", "it", "Accounts that shouldn't exist", "Former employees with access, accounts without 2-step login, "
          "files shared with anyone", "tool", ALL, "googleworkspace", "Close access gaps",
          "Find former employees' accounts, accounts without 2-step login and files shared publicly in Google Workspace, and list fixes"),
    Check("stale_access_okta", "it", "Accounts that shouldn't exist", "Former employees with access and unused app licences", "tool",
          ALL, "okta", "Close access gaps", "Find accounts of people who left and unused app licences in Okta, and list fixes"),
    Check("hiring_funnel", "hiring", "Where hiring gets stuck", "Time to hire, candidates waiting and overdue interview feedback",
          "tool", ALL, "greenhouse", "Hire faster", "Find candidates waiting on a reply or feedback in Greenhouse and draft the nudges"),
    Check("hiring_funnel_ashby", "hiring", "Where hiring gets stuck", "Time to hire, candidates waiting and overdue interview feedback",
          "tool", ALL, "ashby", "Hire faster", "Find candidates waiting on a reply or feedback in Ashby and draft the nudges"),
    Check("onboarding", "hiring", "New hires with unfinished onboarding", "Onboarding tasks still open after the first weeks", "tool",
          ALL, "bamboohr", "Finish every onboarding", "Find open onboarding tasks in BambooHR and remind the right people"),
    Check("support_backlog", "support", "Slow replies to customers", "First reply times and tickets waiting", "tool", ALL, "zendesk",
          "Reply to every ticket within hours", "Measure reply times in Zendesk, find tickets waiting and draft answers"),
    Check("support_backlog_intercom", "support", "Slow replies to customers", "First reply times and conversations left open",
          "tool", ALL, "intercom", "Reply to every conversation within hours",
          "Measure reply times in Intercom, find conversations waiting and draft answers"),
    Check("code_backlog", "engineering", "Security alerts and work waiting for weeks", "Dependency alerts, old issues and pull requests",
          "tool", SOFTWARE, "github", "Clear security alerts and old pull requests",
          "List security alerts, issues and pull requests waiting for weeks in GitHub, and fix or close the top ones"),
    Check("error_spikes", "engineering", "Errors customers hit", "The errors happening most in production", "tool", SOFTWARE,
          "sentry", "Fix the top production errors", "Find the most frequent errors in Sentry and propose a fix for each"),
    Check("contract_renewals", "legal", "Contracts about to renew", "Contracts that auto-renew soon and unsigned ones", "tool",
          ALL, "docusign", "Review contracts before they renew",
          "List contracts in DocuSign that renew in the next 60 days or are still unsigned, with what to decide for each"),
    Check("abandoned_checkouts", "store", "Abandoned checkouts and slow stock", "Carts never completed, customers who never "
          "came back, products that don't sell", "tool", ("ecommerce",), "shopify", "Win back abandoned checkouts",
          "Find abandoned checkouts and slow-selling products in Shopify and draft win-back emails and offers"),
]

BY_KEY = {c.key: c for c in CHECKS}


def for_company(pack_key: str | None) -> list[Check]:
    """The checks that suit this type of company (all of them when the type isn't known)."""
    pack = pack_key if pack_key in ALL else None
    return [c for c in CHECKS if pack is None or pack in c.packs]


def runnable(pack_key: str | None) -> list[Check]:
    return [c for c in for_company(pack_key) if c.method not in ("tool", "measure")]


def deeper(pack_key: str | None) -> list[Check]:
    return [c for c in for_company(pack_key) if c.method == "tool"]


# --- What to run for a company: a budget, not everything -------------------------------------------

# Sales and marketing ("go to market"); everything else counts as another function.
GTM = {"sales", "marketing", "pr", "community", "partnerships", "store"}

# The checks that usually matter most for each type of company, most important first.
PRIORITY: dict[str, list[str]] = {
    "startup": ["search_rank", "ai_answers", "comparison_searches", "social_cadence", "case_studies", "review_volume",
                "cta_clarity", "trigger_events", "content_gaps", "integrations", "help_center", "security_page", "open_roles",
                "job_ads", "legal_basics", "grants"],
    "solo_saas": ["search_rank", "ai_answers", "comparison_searches", "content_gaps", "review_volume", "pricing_clarity",
                  "app_marketplaces", "changelog", "help_center", "referral_program", "legal_basics", "grants"],
    "agency": ["search_rank", "ai_answers", "case_studies", "agency_portfolio", "directories", "leadership_voice", "awards",
               "trust_signals", "tenders", "open_roles", "employer_reviews", "legal_basics"],
    "services": ["search_rank", "ai_answers", "local_listing", "review_volume", "directories", "case_studies", "trust_signals",
                 "tenders", "certifications", "unanswered_reviews", "legal_basics", "job_ads", "employer_reviews"],
    "ecommerce": ["search_rank", "ai_answers", "product_pages", "review_volume", "shipping_returns", "marketplaces",
                  "social_cadence", "referral_program", "unanswered_reviews", "help_center", "payment_options", "legal_basics"],
    "general": ["search_rank", "ai_answers", "directories", "b2b_platforms", "local_listing", "review_volume", "trust_signals",
                "certifications", "trade_shows", "tenders", "legal_basics", "open_roles", "grants"],
}
# Small companies don't need these yet; bigger ones get them earlier.
NOT_YET = {"tiny": {"employer_reviews", "missing_functions", "security_page", "careers_page", "certifications"}}
SOONER = {"mid": ["security_page", "employer_reviews", "missing_functions"],
          "large": ["security_page", "employer_reviews", "missing_functions", "legal_basics"]}
SHORTLIST = 12
MIN_OTHER = 3  # checks from outside sales and marketing in every shortlist


def shortlist(pack_key: str | None, size: str | None) -> list[Check]:
    """The checks worth considering for this type and size of company, most important first."""
    fits = {c.key: c for c in runnable(pack_key)}
    order = list(PRIORITY.get(pack_key or "", PRIORITY["general"]))
    for k in reversed(SOONER.get(size or "", [])):  # bigger companies: these move up
        if k in order:
            order.remove(k)
        order.insert(4, k)
    skip = NOT_YET.get(size or "", set())
    picked = [fits[k] for k in dict.fromkeys(order) if k in fits and k not in skip][:SHORTLIST]
    others = [c for c in picked if c.team not in GTM]
    if len(others) < MIN_OTHER:  # always room for the rest of the company
        extra = [c for k, c in fits.items() if c.team not in GTM and c not in picked and k not in skip][:MIN_OTHER - len(others)]
        picked = picked[: SHORTLIST - len(extra)] + extra
    return picked


def unlockable(pack_key: str | None) -> list[dict]:
    """Per team: the checks connecting a tool unlocks, for "Connect to unlock"."""
    teams: dict[str, list[Check]] = {}
    for c in deeper(pack_key):
        teams.setdefault(c.team, []).append(c)
    order = ["finance", "sales", "support", "it", "hiring", "engineering", "store", "legal", "marketing"]
    from app.catalog import TOOLS

    return [{"team_kind": t, "checks": [{"key": c.key, "title": c.title, "how": c.how, "tool": c.tool, "goal": c.goal,
                                         "label": TOOLS[c.tool].label if c.tool in TOOLS else c.tool}
                                        for c in teams[t]]}
            for t in sorted(teams, key=lambda t: order.index(t) if t in order else 99)]
