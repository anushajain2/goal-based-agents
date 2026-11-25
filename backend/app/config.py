"""Application settings, read from environment variables / a .env file."""

from functools import lru_cache
from pathlib import Path

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

    # --- Agent Chrome ---------------------------------------------------------
    chrome_path: str | None = None  # auto-detected when unset
    chrome_profile_dir: Path = REPO_ROOT / "data" / "agent-chrome-profile"
    chrome_debug_port: int = 9333
    browser_headless: bool = False  # only for CI/tests; locally you want to see the window

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
    smtp_from: str | None = None  # e.g. "Autopilot <login@yourdomain.com>"
    smtp_ssl: bool = False  # True for port 465 (implicit TLS); False uses STARTTLS

    # --- Misc ---------------------------------------------------------------------
    # The address people open in their browser. Google redirects back here after sign-in.
    frontend_origin: str = "http://localhost:3000"
    worker_poll_seconds: float = 2.0
    # Typical Claude cost of one work session, used to estimate budgets until an organization
    # has its own history (see services/estimate.py).
    est_session_cost_usd: float = 0.30
    # MCP servers on this computer or your network (e.g. http://localhost:8001/mcp). Set to
    # false when Autopilot is hosted for others, so nobody can point it at internal machines.
    allow_private_mcp: bool = True

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
