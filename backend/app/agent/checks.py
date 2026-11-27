"""The catalog of things Oton can check about a company, to show what it's missing out on.

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
    how: str  # what's looked at, in one line
    method: str = "web"  # search | ai | web | tool | measure
    packs: tuple[str, ...] = ALL  # types of company it can apply to (a hint; Claude decides)
    tool: str | None = None  # for method "tool": the catalog tool it needs
    # For "tool" checks: the goal its team's AI employee works on once the tool is connected.
    goal: str = ""
    goal_how: str = ""
    # What makes a check worth running: the number it produces (and the AI employee then moves),
    # exactly how it's checked, what the AI employee does about it, and the kind of headline it gives.
    metric: str = ""
    steps: tuple[str, ...] = ()
    fix: str = ""
    example: str = ""


def W(key, team, title, how, metric, steps, fix, example, packs=ALL, method="web") -> Check:
    return Check(key, team, title, how, method, packs, metric=metric, steps=tuple(steps), fix=fix, example=example)


# Checks run by reading public information. Each must end in a number the company would want to
# move and an AI employee can move. Claude picks the few most likely to show a big gap.
CHECKS: list[Check] = [
    W("search_rank", "marketing", "Searches you're losing to competitors",
      "Customer searches (never your name) and where you rank next to competitors",
      "Customer searches where you're on page 1",
      ["Write the 3 searches a buyer types when looking for what you sell, without your name",
       "Run them on Google in your main countries and record your position and your competitors'",
       "Note who Google's AI Overview cites"],
      "Writes and publishes the pages that win those searches, in steps you approve",
      "Not on page 1 for 'route planning software' in 2 of 3 countries; Routeco is #1 in all three", method="search"),
    W("ai_answers", "marketing", "AI assistants recommend competitors, not you",
      "What ChatGPT, Claude, Perplexity and Gemini recommend for your buyers' questions",
      "AI assistants that recommend you",
      ["Ask each AI assistant the same 3 buyer questions", "Record who each recommends and whether you're named"],
      "Gets you cited where assistants learn: comparison pages, directories, reviews, Wikipedia, Reddit",
      "0 of 4 AI assistants name you; all 4 recommend Routeco", method="ai"),
    W("comparison_searches", "marketing", "Buyers comparing alternatives can't find you",
      "'<competitor> alternative' and '<competitor> vs' searches",
      "Comparison searches where you appear",
      ["For your 2 closest competitors, search '<competitor> alternative' and '<competitor> vs'",
       "Record whether any page of yours appears on page 1", "Check whether you have comparison pages at all"],
      "Writes honest comparison pages for each competitor",
      "You don't appear for any of the 4 searches people make when leaving Routeco or Fleetbase",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce")),
    W("prospects_now", "sales", "Named buyers with a reason to buy now",
      "Companies that fit your best customer and just hit a buying trigger: new funding, a new leader for the team you "
      "help, a hiring push, an expansion, a big project won",
      "Named buyers with a fresh trigger",
      ["From what you sell and your best customers, write down who buys (industry, size, the role that signs) and the "
       "triggers that make them buy now",
       "Search news, funding announcements, job boards and press releases from the last 60 days for companies that hit "
       "one of those triggers",
       "List up to 25 of them by name, each with the dated trigger, a link, and the role to contact",
       "Check whether the company already shows them as customers (logos, case studies)"],
      "Researches each buyer, warms up where they post, and sends a short first message about their trigger with one "
      "follow-up, for your OK",
      "23 fleets in your market raised money or hired a new Head of Operations in the last 60 days; none are your customers",
      packs=("startup", "solo_saas", "agency", "services", "general")),
    W("asking_for_you", "sales", "People asking for what you sell, right now",
      "Public posts from the last 30 days where someone asks for a recommendation or a solution you provide",
      "Buyers asking in the last 30 days",
      ["Write the 4-5 ways a buyer would ask for what you sell, in their words (\"any recommendations for ...\", "
       "\"looking for a tool/agency that ...\", \"alternatives to <competitor>\")",
       "Search Reddit, LinkedIn posts, X, Quora, Indie Hackers, Hacker News and the forums and communities of your "
       "industry for posts from the last 30 days that ask that",
       "Count them, and list the best 8 with their date, where, a link and what exactly they asked",
       "Note whether anyone from the company replied, and which competitors were recommended in the replies"],
      "Drafts a genuinely helpful reply to each (no hard pitch), and a personal follow-up where it fits, for your OK",
      "14 people asked for route-planning software on Reddit and LinkedIn in the last 30 days; Routeco was "
      "recommended 6 times, you never",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce", "general")),
    W("competitor_unhappy", "sales", "Your competitors' unhappy customers",
      "Recent bad reviews and public complaints about your closest competitors",
      "Unhappy competitor customers in the last 90 days",
      ["For each of the 2 closest competitors, find reviews of 3 stars or less and public complaints from the last 90 days "
       "on G2, Capterra, Trustpilot, the app stores, Reddit and X",
       "Count them and group them into the 2-3 complaints that come up most",
       "Mark the complaints this company clearly answers better (from its site and product)",
       "Where the reviewer or their company is public, note it (only what they posted publicly)"],
      "Replies to people who are clearly shopping for a switch, and reaches out about their exact pain, with one "
      "follow-up, for your OK",
      "31 Routeco customers complained about slow support in the last 90 days; your site promises a 1-hour reply",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce", "general")),
    W("tenders", "sales", "Open tenders you could win",
      "Public tenders and RFPs that match what you offer",
      "Open tenders that fit, and their total value",
      ["Search public tender portals for your countries (e.g. TED in the EU, SAM.gov in the US, national portals)",
       "Keep open tenders that match what you offer and your size", "Record each one's value and deadline"],
      "Drafts the bid for each one worth going for",
      "5 open tenders matching your services, worth about EUR 1.2M, closing in the next 6 weeks",
      packs=("agency", "services", "general")),
    W("review_gap", "marketing", "Review gap against competitors",
      "Reviews on the sites your buyers check, next to your competitors",
      "Reviews on the main review site",
      ["Find the review sites your buyers use (G2, Capterra, Trustpilot, Google)",
       "Count your reviews and rating there, and your 2 closest competitors'"],
      "Asks your happiest customers for reviews at the right moment",
      "12 reviews on G2 at 4.1; Routeco has 240 at 4.6"),
    W("unanswered_reviews", "support", "Bad reviews nobody answered",
      "Recent negative reviews and whether anyone replied",
      "Negative reviews answered",
      ["Collect your reviews of 3 stars or less from the last 12 months on the main review sites",
       "Check each one for a reply from the company"],
      "Drafts a reply to each, and keeps answering new ones within a day",
      "7 of your 9 negative reviews this year have no reply; the oldest is 8 months old"),
    W("complaint_themes", "product", "What customers keep complaining about",
      "Recurring themes across your public reviews",
      "Share of reviews mentioning the top complaint",
      ["Read your public reviews from the last 12 months", "Group the complaints into themes and count each"],
      "Turns the top complaint into a fix plan, help articles and replies",
      "11 of 30 reviews mention slow onboarding; it's the #1 reason for low ratings"),
    W("proof_gap", "marketing", "Customer proof gap",
      "Case studies and testimonials, next to your number of customers and your competitors",
      "Published customer stories",
      ["Count the customer stories, testimonials and logos on your site",
       "Compare with how many customers you say you have and what your 2 closest competitors show"],
      "Interviews happy customers and writes the stories, for their OK",
      "2 customer stories for 14 customers; Routeco shows 23"),
    W("social_performance", "marketing", "Competitors get far more from social media than you",
      "Posts and engagement in the last 30 days on LinkedIn and X: the company page and the founders, next to competitors'",
      "Posts and engagement (likes + comments) in the last 30 days, you vs competitors",
      ["Find the company's LinkedIn page and X account (use the profiles its site links to) and its founders' LinkedIn "
       "and X profiles", "Do the same for the 2 closest competitors and their founders",
       "For each account, count posts from the last 30 days and add up likes and comments (use the measured X numbers "
       "when given; for LinkedIn, read the public posts and their reaction and comment counts)",
       "Note what the best-performing competitor posts get engagement with (format and topic), and any posts that "
       "clearly brought in leads (people asking for demos or pricing in the comments)"],
      "Drafts posts for the company page and the founders twice a week in their voice, built on what works for "
      "competitors, for your OK",
      "Your company page posted 3 times in 30 days for 20 likes and comments; Routeco posted 10 times for 500, and "
      "its founder posts weekly to 4,000 followers",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce", "general")),
    W("launch_video", "marketing", "No launch video people can watch and share",
      "A launch, demo or explainer video on the home page and the first page of each social profile, next to competitors",
      "Places with a clear launch or demo video (home page, YouTube, LinkedIn, X, Product Hunt)",
      ["Check the home page for a video (the measured video embeds are given) and the main page of the company's YouTube, "
       "LinkedIn and X profiles and Product Hunt for a launch, demo or explainer video (only the first page of each)",
       "Do the same for the 2 closest competitors, and note their video's views or engagement where shown"],
      "Makes a 20-second launch video from your website (story, motion, music and share copy), and drafts the posts to "
      "launch it, for your OK",
      "No launch or demo video on your site, YouTube, LinkedIn or X; both Routeco and Fleetbase lead their home page "
      "with one, and Routeco's has 18,000 views",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce", "general")),
    W("listings_gap", "marketing", "Missing where buyers look",
      "Directories, marketplaces and app stores where your competitors are listed",
      "Places where competitors are listed and you're not",
      ["Find the 4-5 directories or marketplaces where buyers in your category look (G2, Clutch, Thomasnet, "
       "app marketplaces, Amazon...)", "Check where your 2 closest competitors are listed, and whether you are"],
      "Creates and fills in each listing",
      "Routeco and Fleetbase are on Capterra, G2 and the HubSpot marketplace; you're on none"),
    W("buying_friction", "sales", "Buying from you is harder than from competitors",
      "Steps and form fields from your home page to a demo, quote or purchase",
      "Steps and form fields to book or buy",
      ["From your home page, follow the main path to book a demo, get a quote or buy",
       "Count clicks and form fields, and note whether prices are shown", "Do the same on 2 competitors' sites"],
      "Writes a shorter path and the copy for it; with website access, ships it",
      "Booking a demo takes 3 clicks and 11 form fields; Routeco needs 1 click and 4 fields"),
    W("homepage_clarity", "marketing", "A new visitor can't tell what you do",
      "The five-second test: your home page's first screen, read the way your buyer reads it, next to competitors'",
      "Of 4 questions (what is it, who is it for, why you, what to do next), how many the first screen answers",
      ["Read the first screen of the home page (headline, subheadline, the main button) as your target buyer would, "
       "in 5 seconds", "Answer: what is it, who is it for, why choose it over alternatives, what should I do next; "
       "mark each answered or not, and quote the words that confuse",
       "Do the same for the 2 closest competitors",
       "Write a clearer headline and subheadline in the company's own words and claims"],
      "Rewrites the first screen (headline, subheadline, button) and tests it, for your OK",
      "Your headline answers 1 of 4 questions (\"AI for procurement\": for whom, and why you?); Routeco's answers all 4",
      packs=("startup", "solo_saas", "agency", "services", "ecommerce", "general")),
    W("outbound_ready", "sales", "Your outreach would land in spam or go nowhere",
      "Whether the company is set up for outbound: email authentication, a way to book a call, a profile buyers check",
      "Outreach basics in place, of 5",
      ["Use the measured email authentication (SPF, DKIM, DMARC and its policy); missing ones send cold email to spam",
       "Check whether the site has an online booking link (measured booking tools are given) or only a contact form",
       "Check the founders' LinkedIn profiles: a clear headline saying what they sell and to whom, and recent activity",
       "Check whether there's a short deck, one-pager or demo video a buyer can be sent",
       "Note whether cold email would go from the main domain: outreach belongs on a separate, warmed-up domain",
       "Score the 5 basics and say which are missing"],
      "Sets up what's missing before any outreach (a separate outreach domain with email authentication, warmed up; "
      "a booking link; a one-pager), with your OK",
      "DMARC is missing and there's no booking link: cold emails will mostly land in spam, and replies can't book a call",
      packs=("startup", "solo_saas", "agency", "services", "general")),
    W("agency_briefs", "sales", "Client briefs you could pitch for",
      "Briefs and requests for agencies like yours posted in the last 30 days",
      "Open briefs that fit, posted in the last 30 days",
      ["Search Upwork, Clutch, LinkedIn posts (\"looking for an agency\"), RFP boards and industry communities for "
       "briefs from the last 30 days that match the agency's services and size",
       "List the best 8 with their date, budget when shown, where and a link",
       "Check where the agency appears for \"<service> agency <its city>\" next to its 2 closest competitors"],
      "Drafts a tailored pitch for each brief worth going for, for your OK",
      "11 briefs for Shopify development were posted in the last 30 days, 4 with budgets over $10k; you pitched none",
      packs=("agency", "services")),
    W("content_gaps", "marketing", "Questions competitors answer and you don't",
      "Guides and use-case pages competitors have that you don't",
      "Buyer questions your site answers",
      ["List the guides, use-case and question pages on your 2 closest competitors' sites",
       "Check which ones you have an equivalent for"],
      "Writes the missing pages, starting with the ones buyers search most",
      "Routeco answers 18 buyer questions (cost per stop, EU driving hours...) that your site doesn't"),
    W("product_pages", "store", "Product pages missing what buyers need",
      "Photos, reviews, size or spec info and descriptions on your top products",
      "Top product pages with everything buyers need",
      ["Open your 5 best-selling products", "Check each for reviews shown, number of photos, size or spec "
       "guide and description length", "Compare with the same product type at 2 competitors"],
      "Rewrites descriptions, adds size guides and asks buyers for reviews",
      "3 of your 5 best sellers show no reviews and one photo; competitors show 6+ photos and 100+ reviews",
      packs=("ecommerce",)),
    W("delivery_promise", "store", "Your delivery and returns offer is weaker",
      "Free-shipping threshold, delivery days and return window, next to competitors",
      "Delivery and returns terms against competitors",
      ["Read your shipping and returns pages: free-shipping threshold, delivery time, return window, who pays returns",
       "Read the same on 2 competitors' sites"],
      "Models the cost of matching them and rewrites the promise on product and checkout pages",
      "Free shipping from EUR 80 and 14-day returns; both competitors offer free shipping from EUR 40 and 30-day returns",
      packs=("ecommerce",)),
    W("funding_available", "finance", "Funding you're likely leaving on the table",
      "Grants, subsidies and R&D tax credits for your country, industry and stage",
      "Funding you likely qualify for",
      ["From your country, industry, size and what you build, find R&D tax credits and grant programs open now",
       "Check the main eligibility rules against what's public about you", "Record amounts and deadlines"],
      "Prepares the application for each one you choose",
      "Likely eligible for Germany's R&D tax credit (up to 25% of R&D salaries) and 2 open innovation grants",
      packs=("startup", "solo_saas", "general")),
    W("hiring_drag", "hiring", "Key roles open for months",
      "How long your roles have been posted, and what the job ads leave out",
      "Roles open 60+ days",
      ["Find your open roles on your careers page and job boards, with the date each was posted",
       "Check each ad for pay, a clear description of the job and the product"],
      "Sources and ranks candidates for each role and rewrites the ads",
      "3 roles open 90+ days, including the Benelux AE; none of the ads mention pay"),
    W("security_trust", "it", "Enterprise buyers can't check your security",
      "A security or trust page (SOC 2, ISO 27001, GDPR) next to competitors",
      "Security answers buyers can find",
      ["Look for a security or trust page, certifications and a data processing agreement",
       "Check what your 2 closest competitors publish"],
      "Writes the trust page and answers to the common security questionnaire",
      "No security page; Routeco and Fleetbase both publish SOC 2 and a trust centre",
      packs=("startup", "solo_saas", "services")),
    W("legal_exposure", "legal", "Legal gaps on your website",
      "Privacy policy, cookie consent before tracking, terms and accessibility",
      "Legal basics in place",
      ["Check for a privacy policy, terms and, in the EU, an imprint",
       "Check whether ad pixels load before cookie consent", "Check basic accessibility on the home page"],
      "Drafts the missing pages and the fixes, for your and your lawyer's review",
      "Your LinkedIn and Meta pixels load before any cookie consent, which EU regulators fine for"),

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
    """The checks Claude can choose from for this type of company (it picks the few worth running)."""
    return [c for c in for_company(pack_key) if c.method not in ("tool", "measure")]


# Early companies always get these checked, whatever the picker scores: where their next customers
# come from and what showcases them (people asking, social media, a launch video, comparisons, a
# clear home page). Claude picks the rest.
EARLY_CORE = ["asking_for_you", "social_performance", "launch_video", "comparison_searches", "homepage_clarity"]


def core(pack_key: str | None, size: str | None) -> list[str]:
    """The checks that always run for this company (early companies only)."""
    if size in ("mid", "large"):
        return []
    keys = {c.key for c in runnable(pack_key)}
    return [k for k in EARLY_CORE if k in keys]


def deeper(pack_key: str | None) -> list[Check]:
    return [c for c in for_company(pack_key) if c.method == "tool"]


# --- What to run for a company ---------------------------------------------------------------------

# Sales and marketing ("go to market"); everything else counts as another function.
GTM = {"sales", "marketing", "pr", "community", "partnerships", "store"}


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
