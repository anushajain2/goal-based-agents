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

    # --- Deeper checks with a connected tool ---------------------------------------------------------
    Check("lead_followup", "sales", "Leads nobody followed up", "Leads and deals left without a reply", "tool", B2B, "hubspot"),
    Check("lead_followup_sf", "sales", "Stalled deals", "Deals with no activity for weeks", "tool", B2B, "salesforce"),
    Check("inbox_unanswered", "sales", "Inbound emails left unanswered", "Prospect and customer emails waiting for a reply",
          "tool", ALL, "gmail"),
    Check("social_exact", "marketing", "Exact posting and engagement", "Your company page's real posting frequency and engagement",
          "tool", ALL, "linkedin"),
    Check("near_miss_searches", "marketing", "Searches you almost rank for", "Queries where you're on page 2", "tool", ALL,
          "searchconsole"),
    Check("failed_payments", "finance", "Failed payments never recovered", "Failed charges and quiet churn", "tool",
          SOFTWARE + ("ecommerce",), "stripe"),
    Check("overdue_invoices", "finance", "Overdue invoices nobody chased", "Unpaid invoices by age", "tool", B2B, "quickbooks"),
    Check("support_backlog", "support", "Slow replies to customers", "First reply times and tickets waiting", "tool", ALL, "zendesk"),
    Check("code_backlog", "engineering", "Bugs waiting for weeks", "Old issues and pull requests", "tool", SOFTWARE, "github"),
    Check("abandoned_checkouts", "store", "Abandoned checkouts", "Carts never completed and customers who never came back", "tool",
          ("ecommerce",), "shopify"),
]

BY_KEY = {c.key: c for c in CHECKS}


def for_company(pack_key: str | None) -> list[Check]:
    """The checks that suit this type of company (all of them when the type isn't known)."""
    pack = pack_key if pack_key in ALL else None
    return [c for c in CHECKS if pack is None or pack in c.packs]


def runnable(pack_key: str | None) -> list[Check]:
    return [c for c in for_company(pack_key) if c.method != "tool"]


def deeper(pack_key: str | None) -> list[Check]:
    return [c for c in for_company(pack_key) if c.method == "tool"]
