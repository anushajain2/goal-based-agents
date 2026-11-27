"""Application settings, read from environment variables / a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database -----------------------------------------------------------
    # Local default: a SQLite file, nothing to install. For many workers / hosting, point this
    # at Postgres, e.g. postgresql+asyncpg://user:pass@host:5432/autopilot
    database_url: str = f"sqlite+aiosqlite:///{REPO_ROOT / 'data' / 'autopilot.db'}"

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, url: str) -> str:
        """Hosts (Render, Heroku...) hand out postgres://...?sslmode=require; we need asyncpg."""
        return normalize_database_url(url)

    # --- Where it runs ----------------------------------------------------------
    # "development" (your computer) or "production" (hosted for others). Production refuses to
    # start without a SECRET_KEY and turns off things that only make sense on one computer.
    environment: str = "development"
    # Oton Chrome: a visible Chrome on the same computer as the worker. Hosted, there is no
    # screen and no one to sign in, so it's off (websites wait for the desktop helper).
    agent_chrome: bool | None = None  # None = on in development, off in production
    sentry_dsn: str | None = None  # optional error reporting

    # --- Desktop helper -------------------------------------------------------------
    # The helper app connects out to the API's public address (WebSockets don't go through the
    # Next.js proxy). On Render, RENDER_EXTERNAL_URL is set on the API automatically.
    public_api_url: str | None = None
    render_external_url: str | None = None
    # How the worker reaches the API over the private network to borrow a helper's browser.
    api_internal_url: str | None = None
    api_internal_hostport: str | None = None  # render.yaml fills this from autopilot-api
    helper_download_url: str = "https://github.com/anushajain2/goal-based-agents/releases/latest"
    # Helpers seen within this many seconds count as online.
    helper_online_seconds: int = 90

    # --- Claude -------------------------------------------------------------
    anthropic_api_key: str | None = None
    # Each job gets the cheapest model that does it well:
    #   planner - reviews results and plans each work session (one call per session)
    #   worker  - carries out the plan step by step (most calls)
    #   checker - checks each outgoing action against the guardrails (a yes/no judgement)
    planner_model: str = "claude-opus-5-5"
    planner_effort: str = "medium"
    worker_model: str = "claude-sonnet-5-5"
    worker_effort: str = "medium"
    checker_model: str = "claude-haiku-5-5"
    checker_effort: str = "low"
    agent_max_tokens: int = 16000
    # Hard ceiling on model calls in a single optimization cycle (runaway guard).
    max_model_calls_per_cycle: int = 60

    # --- WhatsApp (optional): approvals and questions on people's phones ------------
    # The platform's own WhatsApp Business number on Meta's Cloud API, shared by every
    # organization (like the Composio key). Set all of these to turn it on; see docs/WHATSAPP.md.
    whatsapp_access_token: str | None = None  # a System User token with whatsapp_business_messaging
    whatsapp_phone_number_id: str | None = None  # the business number's id in the Cloud API
    whatsapp_business_number: str | None = None  # the same number, e.g. +14155550123 (for wa.me links)
    whatsapp_app_secret: str | None = None  # the Meta app's secret: checks webhook signatures
    whatsapp_verify_token: str | None = None  # any string; entered in Meta's webhook settings too
    whatsapp_waba_id: str | None = None  # WhatsApp Business Account id (only to create the templates)
    whatsapp_graph_version: str = "v23.0"
    whatsapp_template_lang: str = "en"

    # --- Composio (optional app connectors) ----------------------------------
    composio_api_key: str | None = None
    # Composio scopes connected accounts per "user"; locally there is one user.
    composio_user_id: str = "autopilot-local-user"

    # --- Market checks at setup (optional, the platform's own keys) -------------
    # Used by "What you're missing out on". Customers never enter these: set them once for the
    # whole platform. Each source is used when its key is set and skipped otherwise; checks that
    # need no key (DNS, Wikipedia, App Store, popularity ranks) always run.
    serpapi_key: str | None = None  # real Google results by country, AI Overviews, Maps, Google Play, ads
    dataforseo_login: str | None = None  # search volume and keyword difficulty
    dataforseo_password: str | None = None
    google_api_key: str | None = None  # PageSpeed Insights and YouTube Data API
    openpagerank_key: str | None = None  # domain authority
    meta_ad_library_token: str | None = None  # ads running on Facebook and Instagram (EU)
    openai_api_key: str | None = None  # what ChatGPT recommends
    openai_model: str = "gpt-5-mini"
    perplexity_api_key: str | None = None
    perplexity_model: str = "sonar"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # What one call costs, for the setup cost shown to people (US$).
    serpapi_cost_usd: float = 0.015
    dataforseo_cost_usd: float = 0.08
    assistant_cost_usd: float = 0.01

    # --- GitHub sign-in (optional) ---------------------------------------------
    # An OAuth app (github.com/settings/developers) lets people connect a repository with
    # "Sign in with GitHub". Its callback URL is <frontend origin>/api/integrations/github/callback.
    # Without it, people paste a fine-grained token instead.
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # --- Oton Chrome ---------------------------------------------------------
    chrome_path: str | None = None  # auto-detected when unset
    chrome_profile_dir: Path = REPO_ROOT / "data" / "agent-chrome-profile"
    chrome_debug_port: int = 9333
    browser_headless: bool = False  # only for CI/tests; locally you want to see the window

    # --- Launch videos ------------------------------------------------------------
    # The renderer (video/, Remotion) needs Node and its packages installed (npm ci in video/).
    # Whether goals can make videos: on when this machine can render, unless set. Hosted, the video
    # worker renders, so the API and agent worker are told with VIDEOS=true.
    videos: bool | None = None
    video_dir: Path = REPO_ROOT / "video"
    video_chrome_path: str | None = None  # Chrome for rendering; Remotion's own headless shell when unset
    video_render_concurrency: int = 2  # browser tabs rendering frames in parallel (about 1 per CPU)
    video_timeout_seconds: int = 1800

    # --- Files ------------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"

    # --- Sign-in ---------------------------------------------------------------------
    # Signs sign-in state and hashes login codes. Generated and saved to data/secret_key when unset.
    secret_key: str | None = None
    # Google sign-in (optional): an OAuth client of type "Web application" from Google Cloud.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Email for sign-in codes (optional): any SMTP service (Gmail, Resend, Postmark, SES...).
    # When unset, codes are printed in the backend's terminal instead (fine for local use).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # e.g. "Oton <login@yourdomain.com>"
    smtp_ssl: bool = False  # True for port 465 (implicit TLS); False uses STARTTLS

    # --- Misc ---------------------------------------------------------------------
    # The address people open in their browser. Google redirects back here after sign-in.
    frontend_origin: str = "http://localhost:3000"
    worker_poll_seconds: float = 2.0
    # Typical Claude cost of one work session, used to estimate budgets until an organization
    # has its own history (see services/estimate.py).
    est_session_cost_usd: float = 0.30
    # MCP servers on this computer or your network (e.g. http://localhost:8001/mcp). Set to
    # false when Oton is hosted for others, so nobody can point it at internal machines.
    allow_private_mcp: bool = True

    @property
    def production(self) -> bool:
        return self.environment.lower() in ("production", "prod", "staging")

    @property
    def helper_server_url(self) -> str:
        """The address a desktop helper connects to."""
        url = self.public_api_url or self.render_external_url
        if url:
            return url.rstrip("/")
        return "http://localhost:8000" if not self.production else self.frontend_origin.rstrip("/")

    @property
    def internal_api_url(self) -> str:
        if self.api_internal_url:
            return self.api_internal_url.rstrip("/")
        if self.api_internal_hostport:
            return f"http://{self.api_internal_hostport}"
        return "http://127.0.0.1:8000"

    @property
    def agent_chrome_enabled(self) -> bool:
        return (not self.production) if self.agent_chrome is None else self.agent_chrome

    def check_production(self) -> list[str]:
        """Problems that stop a hosted copy from starting, and warnings worth logging."""
        if not self.production:
            return []
        problems = []
        if not self.secret_key or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set (32+ characters) in production")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point at Postgres in production")
        if not self.frontend_origin.startswith("https://"):
            problems.append("FRONTEND_ORIGIN must be the https:// address people open")
        return problems

    def production_warnings(self) -> list[str]:
        if not self.production:
            return []
        out = []
        if not self.smtp_enabled:
            out.append("SMTP_HOST is not set: sign-in codes are only printed in the logs")
        if not self.anthropic_api_key:
            out.append("ANTHROPIC_API_KEY is not set: Oton can't work")
        if self.allow_private_mcp:
            out.append("ALLOW_PRIVATE_MCP is on: set it to false so MCP servers can't reach internal hosts")
        return out

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id and self.whatsapp_business_number
                    and self.whatsapp_app_secret)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host)

    def secret(self) -> bytes:
        if self.secret_key:
            return self.secret_key.encode()
        path = self.data_dir / "secret_key"
        if not path.exists():
            import secrets

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        return path.read_text().strip().encode()

    @property
    def composio_enabled(self) -> bool:
        return bool(self.composio_api_key)


def normalize_database_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        # asyncpg doesn't take libpq's sslmode; it negotiates TLS itself (ssl='prefer').
        query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("sslmode", "ssl")]
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
