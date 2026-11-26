"""Starting points for an AI team: a catalog of AI employee roles, and packs per type of company.

A role is one kind of AI employee (Outbound SDR, SEO, Collections...): the team it belongs to,
what it does on its own, what it asks a person about first, the tools it uses, and a starter
goal. A pack is a type of company (B2B startup, agency, e-commerce brand...) with the roles that
usually matter most at each size, in priority order.

At setup Autopilot reads the company's website and researches it; Claude then decides which type
of company it is and how big (org_setup.classify_company), and the planner personalises
everything starting from that pack: the functions and AI employees companies like this usually
need at this stage. Without a Claude key nothing can decide, so the starter team uses the general
pack (templates, not personalised) until the company is researched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

S = tuple  # a step: (text, action_type, tool)


@dataclass(frozen=True)
class GoalTemplate:
    name: str  # ongoing, no numbers: what a person on the team would own
    description: str
    metric: str
    done_when: str
    target: float
    period: str = "week"
    category: str = ""
    use_case: str = ""
    first_week: str = ""
    key_results: tuple[str, ...] = ()
    steps: tuple[S, ...] = ()
    cycle_hours: float = 24


@dataclass(frozen=True)
class Role:
    key: str
    kind: str  # the team (department kind) it belongs to
    title: str  # its focus, a few words
    agent_name: str
    objective: str
    does: str  # on its own
    asks: str  # what waits for a person's OK
    tools: tuple[str, ...]
    goals: tuple[GoalTemplate, ...] = field(default_factory=tuple)


def _r(key, kind, title, agent_name, objective, does, asks, tools, *goals) -> Role:
    return Role(key, kind, title, agent_name, objective, does, asks, tuple(tools), tuple(goals))


G = GoalTemplate

ROLES: dict[str, Role] = {r.key: r for r in [
    # --- Sales ---------------------------------------------------------------------------------
    _r("sdr", "sales", "Outbound pipeline", "Outbound Agent", "Fill the calendar with qualified first meetings",
       "builds lists of ideal customers, researches each, drafts personal first messages",
       "sending emails and messages, booking meetings", ("linkedin", "gmail", "apollo", "hubspot", "googlecalendar"),
       G("Book meetings with ideal customers", "Find people at companies that fit the ideal customer profile and book first meetings.",
         "meetings booked", "Meeting on the calendar with a person who fits the profile", 4, category="Sales", use_case="Cold outbound",
         first_week="40 well-matched prospects, each with a personal first message drafted for your OK",
         key_results=("Reply rate above 8%", "100 prospects contacted"),
         steps=(("Find people who match the ideal customer profile", "research", "web"),
                ("Write a personal first message to each", "create_draft", "gmail"),
                ("Send the messages", "send_message", "gmail"),
                ("Book meetings with people who reply", "other_write", "googlecalendar")))),
    _r("inbound", "sales", "Inbound leads", "Inbound Agent", "Answer every inbound lead fast and qualify it",
       "reads new leads, researches the company, drafts a reply and scores the fit",
       "sending replies, booking meetings", ("gmail", "hubspot", "googlecalendar"),
       G("Respond to and qualify inbound leads", "Reply to every inbound lead within the hour, qualify it and book a call with good fits.",
         "leads qualified", "Lead scored and replied to", 15, category="Sales", use_case="Inbound handling",
         steps=(("Read new leads and research each company", "read_data", "hubspot"),
                ("Draft a reply and a fit score", "create_draft", "gmail"),
                ("Send the reply", "send_message", "gmail")))),
    _r("deal_desk", "sales", "Deal support", "Deal Desk Agent", "Help every open deal reach a clear decision",
       "prepares meeting briefs, drafts follow-ups and proposals, keeps deal notes current",
       "sending follow-ups and proposals, changing deal stages", ("hubspot", "salesforce", "gmail", "googledocs"),
       G("Move open deals to a decision", "Prepare for meetings and follow up on every open deal until there's a yes, a no or a next step.",
         "deals with a next step", "Deal has a dated next step or a decision", 10, category="Sales", use_case="Pipeline follow-up",
         steps=(("Read open deals and recent emails", "read_data", "hubspot"),
                ("Draft a brief and a follow-up for each", "create_draft", "gmail"),
                ("Send the follow-ups", "send_message", "gmail")))),
    _r("proposals", "sales", "Proposals and RFPs", "Proposals Agent", "Turn opportunities into strong, fast proposals",
       "drafts proposals, statements of work and RFP answers from past work",
       "sending a proposal to a client", ("googledocs", "googledrive", "gmail"),
       G("Send strong proposals quickly", "Draft proposals and RFP responses from the opportunity notes and past wins.",
         "proposals ready", "Proposal approved and sent", 3, category="Sales", use_case="Closing support",
         steps=(("Read the opportunity and similar past proposals", "read_data", "googledrive"),
                ("Draft the proposal", "create_draft", "googledocs"),
                ("Send it to the client", "send_message", "gmail")))),
    _r("tenders", "sales", "Tenders and RFQs", "Tenders Agent", "Never miss a tender or quote request you could win",
       "searches tender portals and buyer sites, checks fit, drafts the response",
       "submitting a bid or quote", ("web", "googledocs"),
       G("Find and bid on relevant tenders", "Find tenders and requests for quote that fit, and prepare responses.",
         "bids submitted", "Bid submitted before the deadline", 2, period="month", category="Sales", use_case="Tenders and RFPs",
         steps=(("Search tender portals and buyer sites", "research", "web"),
                ("Draft a response for each good fit", "create_draft", "googledocs"),
                ("Submit the bid", "other_write", "web")))),
    _r("agency_bd", "sales", "New clients", "New Business Agent", "Win the right new clients for the agency",
       "finds companies that need the agency's services, uses case studies to write personal outreach",
       "sending outreach, booking calls", ("linkedin", "gmail", "hubspot"),
       G("Win new clients", "Find companies that need what the agency does and start conversations using relevant case studies.",
         "discovery calls booked", "Call booked with a decision maker", 3, category="For agencies", use_case="Client acquisition",
         steps=(("Find companies with a clear need", "research", "web"),
                ("Write outreach built on a matching case study", "create_draft", "gmail"),
                ("Send it", "send_message", "gmail")))),
    _r("wholesale", "sales", "Wholesale and retail", "Wholesale Agent", "Get the products into the right shops",
       "finds retailers and distributors that fit, drafts pitches with line sheets",
       "sending pitches, agreeing terms", ("gmail", "linkedin", "googlesheets"),
       G("Win wholesale accounts", "Find shops and distributors that fit the brand and pitch them.",
         "wholesale accounts opened", "First order placed", 2, period="month", category="Sales", use_case="Channel sales",
         steps=(("Find retailers that fit the brand", "research", "web"),
                ("Draft a pitch with the line sheet", "create_draft", "gmail"),
                ("Send the pitches", "send_message", "gmail")))),
    _r("partnerships", "partnerships", "Partners", "Partnerships Agent", "Bring customers in through partners",
       "finds integration, reseller and affiliate partners, drafts proposals",
       "sending outreach, agreeing terms", ("linkedin", "gmail"),
       G("Sign partners who bring customers", "Find partners who serve the same customers and agree partnerships that send referrals.",
         "partners signed", "Partner agreed in writing", 2, period="month", category="Partnerships & BD", use_case="Partnerships",
         steps=(("Find partners with the same customers", "research", "web"),
                ("Draft a partnership proposal", "create_draft", "gmail"),
                ("Send it", "send_message", "gmail")))),
    # --- Marketing -----------------------------------------------------------------------------
    _r("content", "marketing", "Content and social", "Content Agent", "Become the name the ideal customer trusts",
       "researches topics, drafts posts, articles and newsletters in the brand's voice",
       "publishing anything", ("linkedin", "twitter", "wordpress", "mailchimp"),
       G("Grow an audience with useful content", "Publish useful posts and articles for the ideal customer, consistently.",
         "posts published", "Post or article published", 3, category="Marketing & demand gen", use_case="Content",
         first_week="A content plan for the month and the first three posts drafted for your OK",
         steps=(("Research what the audience is asking about", "research", "web"),
                ("Draft posts and articles", "create_draft", "googledocs"),
                ("Publish them", "publish_post", "linkedin")))),
    _r("seo", "marketing", "SEO", "SEO Agent", "Grow organic traffic from people searching for what you sell",
       "finds keywords, writes article briefs and drafts, spots on-page fixes",
       "publishing articles, changing the website", ("searchconsole", "googleanalytics", "wordpress", "webflow"),
       G("Grow organic search traffic", "Win search traffic for the topics buyers search for.",
         "articles published", "Article live and indexed", 4, period="month", category="Marketing & demand gen", use_case="SEO",
         steps=(("Find keywords buyers search for", "research", "web"),
                ("Draft articles and page fixes", "create_draft", "googledocs"),
                ("Publish them", "publish_article", "wordpress")))),
    _r("paid_ads", "marketing", "Paid ads", "Ads Agent", "Turn ad spend into customers at a good cost",
       "plans campaigns, writes ad copy, analyses results",
       "launching or changing campaigns, every dollar of spend", ("googleads", "metaads", "googleanalytics"),
       G("Get customers from ads at a good cost", "Run small, measured ad tests and scale what works within the budget.",
         "leads from ads", "Lead or purchase attributed to an ad", 20, category="Marketing & demand gen", use_case="Paid acquisition",
         steps=(("Analyse what's working now", "read_data", "googleanalytics"),
                ("Draft new ads and audiences", "create_draft", "none"),
                ("Launch the tests", "spend_money", "googleads")))),
    _r("lifecycle", "marketing", "Email and lifecycle", "Lifecycle Agent", "Turn signups into active, paying customers",
       "writes onboarding, nurture and win-back emails, analyses open and click rates",
       "sending emails to customers", ("mailchimp", "klaviyo", "hubspot"),
       G("Turn signups into active customers", "Run onboarding and nurture emails that move people to the next step.",
         "activated customers", "Customer reaches the activation step", 10, category="Marketing & demand gen", use_case="Lifecycle",
         steps=(("Read signup and activation data", "read_data", "mixpanel"),
                ("Draft the email sequence", "create_draft", "mailchimp"),
                ("Send it", "send_message", "mailchimp")))),
    _r("influencer", "marketing", "Influencers and creators", "Creator Agent", "Get the brand in front of the right audiences",
       "finds creators who fit the brand, drafts personal pitches and gifting offers",
       "sending pitches, sending products or paying creators", ("instagram", "gmail", "googlesheets"),
       G("Partner with creators who fit the brand", "Find creators whose audience matches and get them to feature the products.",
         "creator posts", "Creator posted about the brand", 3, category="Marketing & demand gen", use_case="Influencers",
         steps=(("Find creators who fit", "research", "web"),
                ("Draft personal pitches", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("events", "marketing", "Events", "Events Agent", "Meet buyers in person at the right events",
       "finds events and speaking slots, drafts applications, books meetings around them",
       "applying, registering or paying", ("web", "gmail", "googlecalendar"),
       G("Meet buyers at events", "Find the events where buyers go, get speaking slots and book meetings there.",
         "meetings at events", "Meeting held at an event", 4, period="quarter", category="Marketing & demand gen", use_case="Events",
         steps=(("Find the events buyers attend", "research", "web"),
                ("Draft talk proposals and meeting invites", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("pr", "pr", "PR and media", "PR Agent", "Earn coverage that makes buyers take notice",
       "finds journalists, podcasts and awards that fit, drafts pitches",
       "sending pitches, submitting applications", ("gmail", "web"),
       G("Earn press and podcast mentions", "Pitch journalists, podcasts and awards with stories that fit.",
         "placements", "Article, episode or award published", 2, period="month", category="Brand, PR & community", use_case="PR",
         steps=(("Find journalists and shows that cover the space", "research", "web"),
                ("Draft tailored pitches", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("community", "community", "Community", "Community Agent", "Build a community customers love to be part of",
       "takes part in relevant communities, drafts helpful answers, plans community moments",
       "posting or replying publicly", ("reddit", "discord", "slack", "linkedin"),
       G("Grow an engaged community", "Be genuinely helpful where the audience gathers, and grow the company's own community.",
         "helpful contributions", "Helpful answer or post that got engagement", 10, category="Brand, PR & community", use_case="Community",
         steps=(("Find questions in communities", "research", "reddit"),
                ("Draft helpful answers", "create_draft", "none"),
                ("Post them", "reply", "reddit")))),
    _r("localization", "marketing", "Localisation", "Localisation Agent", "Make the company feel local in every market",
       "translates and adapts pages, emails and ads for each market",
       "publishing translated content", ("googledocs", "webflow"),
       G("Localise for new markets", "Adapt the key pages, emails and ads for each new market.",
         "pages localised", "Localised page live", 5, period="month", category="Marketing & demand gen", use_case="Localisation",
         steps=(("Pick the pages that matter most", "read_data", "googleanalytics"),
                ("Draft the localised versions", "create_draft", "googledocs"),
                ("Publish them", "publish_article", "webflow")))),
    # --- Customer research and intel -----------------------------------------------------------
    _r("customer_research", "research", "Customer research", "Research Agent", "Know what customers need better than anyone",
       "recruits customers for interviews, drafts surveys, summarises what it hears",
       "inviting customers, sending surveys", ("gmail", "googlecalendar", "googledocs"),
       G("Learn from customers every week", "Talk to customers and prospects every week and turn it into clear insights.",
         "interviews held", "Interview held and summarised", 3, category="Customer research", use_case="Customer interviews",
         steps=(("Pick who to talk to", "read_data", "hubspot"),
                ("Draft interview invites", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail"),
                ("Summarise what customers said", "create_draft", "googledocs")))),
    _r("market_intel", "research", "Market and competitors", "Intel Agent", "Never be surprised by a competitor or a market shift",
       "monitors competitors' launches, pricing and hiring, and market news",
       "nothing: it only reports", ("web",),
       G("Track competitors and the market", "Watch competitors and the market, and send a short brief when something matters.",
         "briefs delivered", "Brief approved", 1, category="Market & competitive intel", use_case="Competitive intel",
         steps=(("Check competitors' sites, changelogs and news", "research", "web"),
                ("Write the brief", "create_draft", "none")))),
    # --- Customer success and support ----------------------------------------------------------
    _r("onboarding", "success", "Onboarding", "Onboarding Agent", "Get every new customer to value quickly",
       "watches new accounts, drafts check-ins and guides, flags stuck customers",
       "emailing customers", ("hubspot", "gmail", "intercom"),
       G("Get new customers live fast", "Check in with every new customer and help them reach their first result.",
         "customers live", "Customer reached their first result", 5, category="Customer success & retention", use_case="Onboarding",
         steps=(("Find new and stuck accounts", "read_data", "hubspot"),
                ("Draft personal check-ins", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("renewals", "success", "Renewals and churn", "Renewals Agent", "Keep customers renewing and growing",
       "watches account health and renewal dates, drafts outreach and save plans",
       "emailing customers, offering discounts", ("hubspot", "stripe", "gmail"),
       G("Keep customers renewing", "Reach out before renewals and to at-risk accounts with a plan to keep them.",
         "renewals secured", "Customer renewed or committed", 3, period="month", category="Customer success & retention", use_case="Renewals",
         steps=(("Find renewals and at-risk accounts", "read_data", "stripe"),
                ("Draft outreach and save plans", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("reviews", "success", "Reviews and advocacy", "Advocacy Agent", "Turn happy customers into public proof",
       "finds happy customers, drafts review, referral and case study requests",
       "emailing customers", ("hubspot", "gmail", "shopify"),
       G("Collect reviews from happy customers", "Ask happy customers for reviews, referrals and case studies.",
         "reviews published", "Review live on a public site", 3, category="Customer success & retention", use_case="Advocacy",
         steps=(("Find happy customers", "read_data", "hubspot"),
                ("Draft personal requests", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("client_onboarding", "success", "Client intake", "Intake Agent", "Make starting work with the firm effortless",
       "prepares welcome packs, collects documents, tracks what's missing",
       "emailing clients", ("gmail", "googledrive", "docusign"),
       G("Onboard new clients smoothly", "Collect everything needed from each new client and get work started.",
         "clients onboarded", "All intake items received", 4, period="month", category="Customer success & retention", use_case="Client onboarding",
         steps=(("List what each new client still owes", "read_data", "googledrive"),
                ("Draft reminders", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("support_agent", "support", "Customer support", "Support Agent", "Answer every customer quickly and well",
       "reads tickets, finds the answer in the help centre and past replies, drafts responses, tags trends",
       "sending replies (until you let it answer simple ones on its own), refunds", ("zendesk", "intercom", "gmail", "shopify"),
       G("Answer customer questions quickly", "Draft accurate replies to every new ticket and escalate what needs a person.",
         "tickets answered", "Customer got a correct answer", 30, category="Customer success & retention", use_case="Support",
         steps=(("Read new tickets", "read_data", "zendesk"),
                ("Draft replies from the help centre", "create_draft", "zendesk"),
                ("Send the replies", "send_message", "zendesk")))),
    _r("help_center", "support", "Help centre", "Docs Agent", "Answer questions before customers have to ask",
       "turns repeated questions into help articles and keeps them current",
       "publishing articles", ("zendesk", "intercom", "notion"),
       G("Turn repeat questions into help articles", "Write and update help articles for the questions customers ask most.",
         "articles published", "Help article live", 4, period="month", category="Customer success & retention", use_case="Help centre",
         steps=(("Find the most repeated questions", "read_data", "zendesk"),
                ("Draft articles", "create_draft", "notion"),
                ("Publish them", "publish_article", "zendesk")))),
    # --- Revenue operations --------------------------------------------------------------------
    _r("crm_hygiene", "revops", "CRM hygiene", "RevOps Agent", "Keep the CRM complete, clean and trusted",
       "finds duplicates, missing fields and stale deals; enriches records",
       "changing CRM records in bulk", ("hubspot", "salesforce", "apollo"),
       G("Keep the CRM complete and accurate", "Fix duplicates, missing fields and stale deals so the pipeline can be trusted.",
         "records fixed", "Record complete and correct", 100, category="Sales", use_case="Sales operations",
         steps=(("Find duplicates and missing fields", "read_data", "hubspot"),
                ("Prepare the fixes", "create_draft", "googlesheets"),
                ("Update the records", "modify_account", "hubspot")))),
    _r("pricing", "revops", "Pricing", "Pricing Agent", "Charge the right price for the value delivered",
       "researches competitor pricing, analyses conversion by plan, proposes experiments",
       "changing prices", ("stripe", "web", "googlesheets"),
       G("Find better pricing", "Study competitors and conversion data, and propose pricing experiments.",
         "experiments proposed", "Experiment approved", 1, period="month", category="Product & launch", use_case="Pricing",
         steps=(("Collect competitor pricing", "research", "web"),
                ("Analyse conversion by plan", "read_data", "stripe"),
                ("Write the proposal", "create_draft", "googledocs")))),
    # --- Product, data and engineering ---------------------------------------------------------
    _r("pm", "product", "Metrics and PRDs", "Product Agent", "Know what to build next, and why",
       "watches product metrics and the market, explains changes, writes prioritised PRDs",
       "nothing ships without engineers; PRDs go to you or Engineering as you choose", ("posthog", "database", "linear", "web"),
       G("Turn product data into the next features", "Find the biggest user problems and write prioritised PRDs.",
         "PRDs approved", "PRD approved", 2, category="Product & launch", use_case="PRDs",
         steps=(("Read usage data and feedback", "read_data", "posthog"),
                ("Rank problems by impact", "read_data", "database"),
                ("Write a PRD for the top one", "create_draft", "none")))),
    _r("data_analyst", "data", "Data analysis", "Data Analyst Agent", "Answer the team's questions with data",
       "writes read-only SQL, builds weekly metrics reports, explains changes",
       "nothing: it only reads data and reports", ("database", "googlesheets", "mixpanel"),
       G("Answer the team's data questions", "Deliver weekly metrics and answer data questions with clear analyses.",
         "analyses delivered", "Analysis approved", 2, category="Product & launch", use_case="Analytics",
         steps=(("Query the numbers", "read_data", "database"),
                ("Write the analysis", "create_draft", "googlesheets")))),
    _r("engineer", "engineering", "Small fixes and builds", "Engineering Agent", "Ship small, safe improvements without slowing the team",
       "reads the code, writes fixes on a branch and opens pull requests",
       "merging anything", ("github", "linear"),
       G("Ship small fixes from open issues", "Fix small, well-defined issues as pull requests.",
         "fixes merged", "Pull request merged by an engineer", 2, category="Product & launch", use_case="Bug fixes",
         steps=(("Pick small issues", "read_data", "github"),
                ("Write the fix and open a pull request", "propose_code", "github"),
                ("Ask an engineer to merge", "merge_code", "github")))),
    _r("qa", "engineering", "QA and testing", "QA Agent", "Catch bugs before customers do",
       "writes tests for risky code, tries key flows, files clear bug reports",
       "merging tests", ("github", "linear"),
       G("Catch bugs before customers do", "Add tests to untested, risky code and report bugs clearly.",
         "tests added", "Test merged", 5, category="Product & launch", use_case="QA",
         steps=(("Find risky, untested code", "read_data", "github"),
                ("Write tests and open a pull request", "propose_code", "github"),
                ("Ask an engineer to merge", "merge_code", "github")))),
    _r("incident_triage", "engineering", "Incident triage", "Triage Agent", "No production error goes unnoticed",
       "watches error reports, groups them, finds the likely cause and drafts a fix",
       "merging fixes, paging people", ("sentry", "github", "slack"),
       G("Triage every new production error", "Group new errors, find likely causes and open issues or fixes.",
         "errors triaged", "Error has an owner and a likely cause", 10, category="Product & launch", use_case="Incident triage",
         steps=(("Read new errors", "read_data", "sentry"),
                ("Find the likely cause in the code", "read_data", "github"),
                ("Open an issue or a fix", "propose_code", "github")))),
    # --- Finance -------------------------------------------------------------------------------
    _r("bookkeeper", "finance", "Bookkeeping", "Bookkeeping Agent", "Keep the books current and clean",
       "categorises and reconciles transactions, flags anything odd",
       "changing the books", ("quickbooks", "xero", "ramp"),
       G("Keep the books up to date", "Categorise and reconcile every transaction each week.",
         "transactions reconciled", "Transaction categorised and matched", 100, category="Finance", use_case="Bookkeeping",
         steps=(("Read new transactions", "read_data", "quickbooks"),
                ("Prepare categories and matches", "create_draft", "googlesheets"),
                ("Record them", "other_write", "quickbooks")))),
    _r("collections", "finance", "Invoices and collections", "Collections Agent", "Get paid on time",
       "lists overdue invoices, drafts polite reminders",
       "sending reminders, changing invoices", ("quickbooks", "xero", "stripe", "gmail"),
       G("Collect overdue invoices", "Chase every overdue invoice until it's paid or has a payment date.",
         "invoices resolved", "Invoice paid or payment date agreed", 5, category="Finance", use_case="Collections",
         steps=(("List overdue invoices", "read_data", "quickbooks"),
                ("Draft polite reminders", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("payables", "finance", "Bills and payables", "Payables Agent", "Pay the right bills on time, and nothing else",
       "reads bills, matches them to orders, prepares payment runs",
       "every payment", ("quickbooks", "ramp", "gmail"),
       G("Process bills on time", "Check every bill against what was ordered and prepare payments.",
         "bills processed", "Bill checked and scheduled", 20, period="month", category="Finance", use_case="Payables",
         steps=(("Read new bills", "read_data", "quickbooks"),
                ("Match them to orders", "read_data", "ramp"),
                ("Schedule the payments", "spend_money", "quickbooks")))),
    _r("fpa", "finance", "Planning and reporting", "FP&A Agent", "Always know burn, runway and where money goes",
       "builds monthly burn, runway and spend reports and simple forecasts",
       "nothing: it only reports", ("quickbooks", "ramp", "googlesheets"),
       G("Report burn, runway and spend", "Send a clear monthly finance report with burn, runway and savings.",
         "reports approved", "Report approved", 1, period="month", category="Finance", use_case="Reporting",
         steps=(("Read transactions and balances", "read_data", "quickbooks"),
                ("Build the report", "create_draft", "googlesheets")))),
    # --- Operations ----------------------------------------------------------------------------
    _r("procurement", "operations", "Procurement", "Procurement Agent", "Buy better and never overpay for renewals",
       "compares vendors, collects quotes, prepares renewal negotiations",
       "agreeing to buy anything", ("web", "gmail", "ramp"),
       G("Get better deals from vendors", "Collect quotes and negotiate renewals so every purchase is a good deal.",
         "savings found", "Saving agreed in writing", 2, period="month", category="Operations & procurement", use_case="Procurement",
         steps=(("Find upcoming renewals and needs", "read_data", "ramp"),
                ("Collect quotes and draft negotiations", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("inventory", "operations", "Inventory and suppliers", "Inventory Agent", "Never run out, never overstock",
       "forecasts stock from sales, drafts purchase orders, chases suppliers",
       "placing orders, paying suppliers", ("shopify", "googlesheets", "gmail"),
       G("Keep stock at the right level", "Forecast demand and prepare purchase orders before stock runs low.",
         "stock-outs avoided", "Reorder placed before stock ran out", 5, period="month", category="Operations & procurement", use_case="Inventory",
         steps=(("Read sales and stock levels", "read_data", "shopify"),
                ("Draft purchase orders", "create_draft", "googlesheets"),
                ("Send them to suppliers", "spend_money", "gmail")))),
    _r("merchandising", "store", "Merchandising", "Merchandising Agent", "Make every product easy to find and want",
       "improves product titles, descriptions, photos and collections; plans promotions",
       "changing the store, launching promotions", ("shopify", "googleanalytics"),
       G("Improve product pages that sell", "Rewrite product pages and collections to lift conversion.",
         "pages improved", "Improved page live", 10, category="Marketing & demand gen", use_case="Merchandising",
         steps=(("Find pages with traffic but few sales", "read_data", "shopify"),
                ("Draft better titles and descriptions", "create_draft", "none"),
                ("Update the store", "modify_account", "shopify")))),
    # --- People --------------------------------------------------------------------------------
    _r("recruiter", "hiring", "Recruiting", "Recruiting Agent", "Fill open roles with great people, fast",
       "writes job posts, sources candidates, ranks them against the role's requirements only",
       "contacting candidates; people make every hiring decision", ("linkedin", "greenhouse", "ashby", "gmail"),
       G("Hire great people for open roles", "Source and shortlist strong candidates for each open role.",
         "candidates shortlisted", "Candidate shortlisted by the hiring manager", 5, category="Hiring & talent", use_case="Sourcing",
         steps=(("Find candidates who fit the requirements", "research", "linkedin"),
                ("Rank them on the requirements only", "read_data", "greenhouse"),
                ("Draft personal notes", "create_draft", "gmail"),
                ("Send them", "send_message", "gmail")))),
    _r("hr_ops", "hiring", "People operations", "People Ops Agent", "Make joining and working here smooth",
       "prepares onboarding plans, answers policy questions from the handbook, tracks paperwork",
       "messaging employees, changing HR records", ("bamboohr", "gusto", "notion", "slack"),
       G("Onboard new hires smoothly", "Prepare everything a new hire needs before day one.",
         "new hires ready", "Checklist done before the start date", 2, period="month", category="Hiring & talent", use_case="Onboarding",
         steps=(("Read upcoming start dates", "read_data", "bamboohr"),
                ("Draft onboarding plans and checklists", "create_draft", "notion"),
                ("Send the welcome", "send_message", "gmail")))),
    # --- IT, security, legal -------------------------------------------------------------------
    _r("it_admin", "it", "Access and apps", "IT Agent", "Everyone has the access they need, and nobody else",
       "keeps an inventory of apps and access, finds leftover accounts",
       "changing anyone's access", ("googleworkspace", "okta", "ramp"),
       G("Keep access clean", "Review who has access to what and close what isn't needed.",
         "accounts reviewed", "Account kept or closed after review", 20, period="month", category="IT & security", use_case="Access",
         steps=(("List apps and who has access", "read_data", "googleworkspace"),
                ("Flag leftover and unused accounts", "create_draft", "googlesheets"),
                ("Close them", "modify_account", "googleworkspace")))),
    _r("compliance", "it", "Security and compliance", "Compliance Agent", "Pass every security review without a scramble",
       "answers security questionnaires from approved material, collects SOC 2 / ISO 27001 evidence",
       "sending answers to customers", ("googledrive", "github", "googleworkspace"),
       G("Answer security reviews quickly", "Answer customer security questionnaires and keep compliance evidence current.",
         "questionnaires answered", "Questionnaire returned", 2, period="month", category="IT & security", use_case="Security reviews",
         steps=(("Read the questionnaire", "read_data", "googledrive"),
                ("Draft answers from approved material", "create_draft", "googledocs"),
                ("Send them", "send_message", "gmail")))),
    _r("contracts", "legal", "Contracts", "Contracts Agent", "Never sign something risky or miss a renewal",
       "summarises contracts, flags unusual terms, tracks renewals and notice periods",
       "sending anything to the other side; people sign", ("googledrive", "docusign"),
       G("Review contracts and track renewals", "Summarise each contract, flag risks for a lawyer and track renewal dates.",
         "contracts reviewed", "Summary and flags delivered", 5, period="month", category="Legal & admin", use_case="Contracts",
         steps=(("Read new and renewing contracts", "read_data", "googledrive"),
                ("Write summaries and risk flags", "create_draft", "googledocs")))),
    # --- Founder's office ----------------------------------------------------------------------
    _r("exec_assistant", "exec", "Executive assistant", "Assistant Agent", "Give the founder hours back every week",
       "triages the inbox, prepares meeting briefs, drafts replies and scheduling",
       "sending emails, accepting meetings", ("gmail", "googlecalendar", "notion"),
       G("Free up the founder's week", "Triage the inbox, prepare for meetings and draft replies.",
         "tasks handled", "Task done or reply drafted", 20, category="Founder leverage", use_case="Executive assistant",
         steps=(("Read the inbox and calendar", "read_data", "gmail"),
                ("Draft replies and meeting briefs", "create_draft", "gmail"),
                ("Send replies", "send_message", "gmail")))),
    _r("chief_of_staff", "exec", "Chief of staff", "Chief of Staff Agent", "Keep the whole company aligned every week",
       "collects progress from every team, writes the weekly summary and tracks decisions",
       "sending the summary to the team", ("slack", "notion", "googledocs"),
       G("Keep the company aligned every week", "Send a short weekly summary of progress, risks and decisions across all teams.",
         "weekly summaries", "Summary approved", 1, category="Founder leverage", use_case="Chief of staff",
         steps=(("Collect each team's progress", "read_data", "notion"),
                ("Write the weekly summary", "create_draft", "googledocs"),
                ("Share it", "send_message", "slack")))),
    _r("investor_relations", "fundraising", "Investor relations", "Investor Relations Agent", "Keep investors informed and helpful",
       "drafts monthly investor updates from the company's numbers, keeps the data room current",
       "sending updates to investors", ("gmail", "googledrive", "googlesheets"),
       G("Keep investors informed", "Send a clear monthly investor update with the numbers and the asks.",
         "updates sent", "Update sent", 1, period="month", category="Fundraising & investors", use_case="Investor updates",
         steps=(("Collect this month's numbers", "read_data", "googlesheets"),
                ("Draft the update", "create_draft", "gmail"),
                ("Send it", "send_message", "gmail")))),
    _r("fundraiser", "fundraising", "Fundraising", "Fundraising Agent", "Raise the next round from the right investors",
       "finds investors who fund this stage and space, finds warm paths, drafts outreach",
       "contacting investors", ("linkedin", "gmail", "googlesheets"),
       G("Meet investors who fit the round", "Find investors who fund this stage and space and book first meetings.",
         "investor meetings", "Meeting held with a partner", 4, category="Fundraising & investors", use_case="Investor outreach",
         steps=(("Find investors for this stage and space", "research", "web"),
                ("Draft personal outreach", "create_draft", "gmail"),
                ("Send it", "send_message", "gmail")))),
    _r("grants", "fundraising", "Grants", "Grants Agent", "Win grants that fund the mission",
       "finds grants that fit, drafts applications from past ones",
       "submitting applications", ("web", "googledocs"),
       G("Win grants", "Find grants that fit and prepare strong applications.",
         "applications submitted", "Application submitted", 2, period="month", category="Fundraising & investors", use_case="Grants",
         steps=(("Find grants that fit", "research", "web"),
                ("Draft the applications", "create_draft", "googledocs"),
                ("Submit them", "other_write", "web")))),
    # --- Agency delivery -----------------------------------------------------------------------
    _r("client_reporting", "delivery", "Client reporting", "Reporting Agent", "Every client always knows the value they get",
       "pulls each client's results, writes a clear weekly report",
       "sending reports to clients", ("googleanalytics", "googleads", "googlesheets", "gmail"),
       G("Send every client a clear weekly report", "Pull each client's numbers and write a short report with results and next steps.",
         "reports sent", "Report sent to the client", 5, category="For agencies", use_case="Client reporting",
         steps=(("Pull each client's results", "read_data", "googleanalytics"),
                ("Write the reports", "create_draft", "googledocs"),
                ("Send them", "send_message", "gmail")))),
    _r("client_delivery", "delivery", "Client work", "Delivery Agent", "Deliver great client work on time",
       "drafts the recurring deliverables for each client (posts, emails, briefs)",
       "publishing or sending anything for a client", ("googledocs", "linkedin", "gmail"),
       G("Deliver recurring client work", "Prepare each client's recurring deliverables ahead of deadlines.",
         "deliverables ready", "Deliverable approved", 10, category="For agencies", use_case="Delivery",
         steps=(("Read each client's brief and calendar", "read_data", "googledocs"),
                ("Draft the deliverables", "create_draft", "googledocs"),
                ("Publish or send them", "publish_post", "linkedin")))),
]}


# --- packs: types of company --------------------------------------------------------------------

@dataclass(frozen=True)
class Pack:
    key: str
    label: str
    description: str
    stages: dict[str, tuple[str, ...]]  # size -> role keys added at that size, most important first
    notes: str  # guidance for the planner
    later: tuple[tuple[str, str], ...] = ()  # (department kind, when)


SIZE_ORDER = ["tiny", "small", "mid", "large"]

PACKS: dict[str, Pack] = {p.key: p for p in [
    Pack("startup", "B2B startup", "Seed to Series A software or tech company selling to businesses",
         {"tiny": ("sdr", "content", "pm", "customer_research", "fundraiser", "engineer"),
          "small": ("inbound", "seo", "onboarding", "recruiter", "collections", "market_intel", "exec_assistant"),
          "mid": ("deal_desk", "renewals", "support_agent", "data_analyst", "crm_hygiene", "compliance", "fpa", "contracts",
                  "chief_of_staff", "qa"),
          "large": ("paid_ads", "pr", "events", "partnerships", "hr_ops", "it_admin", "procurement", "incident_triage",
                    "investor_relations", "help_center", "bookkeeper", "lifecycle")},
         "Growth first: pipeline and product. Fundraising only if they are raising or about to. Engineering only if they "
         "build software in-house. Back office (finance, legal, IT) once there is revenue, enterprise customers or a team.",
         (("finance", "once there is recurring revenue"), ("it", "when enterprise customers send security reviews"),
          ("legal", "when contract volume grows"))),
    Pack("solo_saas", "Solo or bootstrapped software", "Solo founder or small bootstrapped team with a self-serve product",
         {"tiny": ("seo", "content", "community", "support_agent", "lifecycle"),
          "small": ("paid_ads", "reviews", "help_center", "pricing", "engineer", "qa"),
          "mid": ("partnerships", "data_analyst", "bookkeeper", "pm"),
          "large": ("pr", "renewals", "localization")},
         "Self-serve growth and leverage: organic acquisition, community, support and activation. No outbound sales team "
         "unless they sell to businesses with large contracts. Keep it small: the founder approves everything.",
         (("revops", "when pricing and plans multiply"), ("finance", "once revenue needs proper books"))),
    Pack("agency", "Agency", "Marketing, growth, design, development or recruiting agency serving clients",
         {"tiny": ("agency_bd", "client_delivery", "client_reporting", "content"),
          "small": ("proposals", "collections", "reviews", "recruiter"),
          "mid": ("contracts", "fpa", "crm_hygiene", "partnerships"),
          "large": ("pr", "events", "hr_ops", "chief_of_staff")},
         "Two sides: winning clients (the agency's own growth) and delivering for clients (recurring client work and "
         "reports). Client goals should name the client (agencies run goals per client).",
         (("finance", "when invoicing many clients"), ("legal", "when contracts and SOWs pile up"))),
    Pack("services", "Professional services", "Consultancy, accounting, law, IT managed services or another expert firm",
         {"tiny": ("proposals", "sdr", "content", "client_onboarding", "collections"),
          "small": ("reviews", "tenders", "exec_assistant", "recruiter"),
          "mid": ("contracts", "fpa", "crm_hygiene", "compliance", "events"),
          "large": ("pr", "hr_ops", "it_admin", "procurement")},
         "Partners hate business development: relationship-led outreach, thought leadership and fast proposals win work. "
         "Smooth intake and getting paid matter as much as winning. Keep a professional, careful tone.",
         (("legal", "when engagement letters multiply"), ("it", "when clients ask for security reviews"))),
    Pack("ecommerce", "E-commerce or DTC brand", "Brand selling physical products online, direct to consumers",
         {"tiny": ("paid_ads", "content", "influencer", "support_agent", "reviews"),
          "small": ("merchandising", "lifecycle", "seo", "wholesale", "inventory"),
          "mid": ("bookkeeper", "procurement", "data_analyst", "partnerships", "community"),
          "large": ("pr", "localization", "fpa", "recruiter", "events")},
         "Revenue is ads, creators, email and conversion: every ad dollar and every send needs approval. Support and "
         "reviews protect the brand. Inventory and suppliers once volume grows.",
         (("operations", "when stock and suppliers need weekly attention"), ("finance", "when margins need tracking"))),
    Pack("general", "Business", "Any other business",
         {"tiny": ("sdr", "content", "customer_research", "support_agent"),
          "small": ("collections", "reviews", "seo", "recruiter"),
          "mid": ("crm_hygiene", "fpa", "contracts", "exec_assistant"),
          "large": ("it_admin", "hr_ops", "procurement", "pr")},
         "No template fits exactly: choose functions from the catalog that match what this company does."),
]}

def roles_for(pack_key: str, size: str) -> list[Role]:
    """Every role the pack suggests up to this size, most important first."""
    pack = PACKS.get(pack_key) or PACKS["general"]
    keys: list[str] = []
    for s in SIZE_ORDER[: SIZE_ORDER.index(size if size in SIZE_ORDER else "small") + 1]:
        keys += [k for k in pack.stages.get(s, ()) if k not in keys]
    return [ROLES[k] for k in keys]


def catalog_text() -> str:
    """The role catalog for the planner, grouped by team."""
    from app.org import PRESET_NAMES

    by_kind: dict[str, list[Role]] = {}
    for r in ROLES.values():
        by_kind.setdefault(r.kind, []).append(r)
    lines = []
    for kind, roles in by_kind.items():
        lines.append(f"{PRESET_NAMES.get(kind, kind)} (kind {kind}):")
        lines += [f"  - {r.key}: {r.title}. On its own: {r.does}. Asks first: {r.asks}." for r in roles]
    return "\n".join(lines)


def pack_brief(pack_key: str, reason: str = "", size: str = "") -> str:
    """The starting template for the planner: what companies like this usually need, by size."""
    from app.org import PRESET_NAMES

    pack = PACKS.get(pack_key) or PACKS["general"]
    lines = [f"Likely type: {pack.label} ({pack.description})" + (f": {reason}" if reason else "")
             + (f". Likely size: {size}" if size else "") + ". Correct either if the research says otherwise.",
             f"What usually matters for this type: {pack.notes}", "Roles it usually needs, added by size:"]
    for size in SIZE_ORDER:
        keys = pack.stages.get(size) or ()
        if keys:
            lines.append(f"  {size}: " + ", ".join(f"{k} ({PRESET_NAMES.get(ROLES[k].kind, ROLES[k].kind)})" for k in keys))
    return "\n".join(lines)


def starter_plan(pack_key: str, size: str = "small", max_roles: int | None = None) -> dict:
    """A team built from the pack alone (no research or Claude): departments, AI employees from
    the roles, and each role's starter goal. Same shape as the planner's plan."""
    from app.org import PRESET_NAMES

    roles = roles_for(pack_key, size)[: max_roles or None]
    departments: dict[str, dict] = {}
    for i, r in enumerate(roles):
        d = departments.setdefault(r.kind, {"kind": r.kind, "name": PRESET_NAMES.get(r.kind, r.kind.title()),
                                            "why": "", "agents": []})
        d["agents"].append({
            "role": r.key, "name": r.agent_name, "title": r.title, "objective": r.objective,
            "goals": [_goal_dict(g, start_here=i < 2) for g in r.goals[:1]],
        })
    pack = PACKS.get(pack_key) or PACKS["general"]
    return {"profile": {"company_type": pack.key, "size": size}, "departments": list(departments.values()),
            "later": [{"kind": k, "name": PRESET_NAMES.get(k, k), "when": w} for k, w in pack.later]}


def _goal_dict(g: GoalTemplate, start_here: bool = False) -> dict:
    return {
        "name": g.name, "goal_description": g.description, "done_when": g.done_when, "primary_metric": g.metric,
        "target_value": g.target, "target_period": g.period, "category": g.category, "use_case": g.use_case,
        "cycle_hours": g.cycle_hours, "duration_days": 30, "paid_spend_usd": 0,
        "steps": [{"text": t, "action_type": a, "tool": tool} for t, a, tool in g.steps],
        "channels": [], "why": "", "first_week": g.first_week, "start_here": start_here,
        "key_results": list(g.key_results),
    }
