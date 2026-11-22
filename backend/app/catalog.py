"""The tools goals usually need, and the two ways an AI employee can use each one:
through an app connector (Composio, signed in once with the app's own login page) or by
signing in to the website once in Agent Chrome. Custom MCP servers are listed separately.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    app: str | None  # Composio toolkit slug
    site: str | None  # website to sign in to in Agent Chrome
    login_url: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


TOOLS: dict[str, Tool] = {t.key: t for t in [
    Tool("gmail", "Gmail", "gmail", "mail.google.com", "https://mail.google.com"),
    Tool("outlook", "Outlook", "outlook", "outlook.office.com", "https://outlook.office.com/mail"),
    Tool("googlecalendar", "Google Calendar", "googlecalendar", "calendar.google.com", "https://calendar.google.com"),
    Tool("calendly", "Calendly", "calendly", "calendly.com", "https://calendly.com/login"),
    Tool("linkedin", "LinkedIn", "linkedin", "linkedin.com", "https://www.linkedin.com/login"),
    Tool("twitter", "X (Twitter)", "twitter", "x.com", "https://x.com/login"),
    Tool("instagram", "Instagram", "instagram", "instagram.com", "https://www.instagram.com/accounts/login/"),
    Tool("facebook", "Facebook", "facebook", "facebook.com", "https://www.facebook.com/login"),
    Tool("reddit", "Reddit", "reddit", "reddit.com", "https://www.reddit.com/login"),
    Tool("youtube", "YouTube", "youtube", "youtube.com", "https://www.youtube.com"),
    Tool("hubspot", "HubSpot", "hubspot", "app.hubspot.com", "https://app.hubspot.com/login"),
    Tool("salesforce", "Salesforce", "salesforce", "login.salesforce.com", "https://login.salesforce.com"),
    Tool("pipedrive", "Pipedrive", "pipedrive", "app.pipedrive.com", "https://app.pipedrive.com/auth/login"),
    Tool("apollo", "Apollo", "apollo", "app.apollo.io", "https://app.apollo.io/#/login"),
    Tool("slack", "Slack", "slack", "app.slack.com", "https://slack.com/signin"),
    Tool("notion", "Notion", "notion", "notion.so", "https://www.notion.so/login"),
    Tool("googlesheets", "Google Sheets", "googlesheets", "docs.google.com", "https://docs.google.com/spreadsheets"),
    Tool("googledocs", "Google Docs", "googledocs", "docs.google.com", "https://docs.google.com/document"),
    Tool("mailchimp", "Mailchimp", "mailchimp", "mailchimp.com", "https://login.mailchimp.com"),
    Tool("shopify", "Shopify", "shopify", "admin.shopify.com", "https://accounts.shopify.com/store-login"),
    Tool("stripe", "Stripe", "stripe", "dashboard.stripe.com", "https://dashboard.stripe.com/login"),
    Tool("googleads", "Google Ads", "googleads", "ads.google.com", "https://ads.google.com"),
    Tool("metaads", "Meta Ads", "facebook", "adsmanager.facebook.com", "https://adsmanager.facebook.com"),
    Tool("producthunt", "Product Hunt", None, "producthunt.com", "https://www.producthunt.com/login"),
    Tool("wordpress", "WordPress", "wordpress", None, None),
    Tool("webflow", "Webflow", "webflow", "webflow.com", "https://webflow.com/dashboard/login"),
]}

# Channel names people pick in the goal wizard -> tools.
CHANNEL_TOOLS = {
    "email": "gmail", "linkedin": "linkedin", "x / twitter": "twitter", "twitter": "twitter", "x": "twitter",
    "instagram": "instagram", "reddit": "reddit", "product hunt": "producthunt", "calendar": "googlecalendar",
    "facebook": "facebook", "youtube": "youtube", "newsletter": "mailchimp", "newsletters": "mailchimp",
}


def tool_for(name: str | None) -> Tool | None:
    if not name:
        return None
    key = name.strip().lower()
    return TOOLS.get(key) or TOOLS.get(CHANNEL_TOOLS.get(key, ""))
