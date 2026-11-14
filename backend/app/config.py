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
    agent_model: str = "claude-opus-5-5"
    # Effort for the main agent loop and for cheap side-calls (rule checks).
    agent_effort: str = "high"
    checker_effort: str = "low"
    agent_max_tokens: int = 16000
    # Hard ceiling on model calls in a single optimization cycle (runaway guard).
    max_model_calls_per_cycle: int = 60

    # --- Composio (optional app connectors) ----------------------------------
    composio_api_key: str | None = None
    # Composio scopes connected accounts per "user"; locally there is one user.
    composio_user_id: str = "autopilot-local-user"

    # --- Agent Chrome ---------------------------------------------------------
    chrome_path: str | None = None  # auto-detected when unset
    chrome_profile_dir: Path = REPO_ROOT / "data" / "agent-chrome-profile"
    chrome_debug_port: int = 9333
    browser_headless: bool = False  # only for CI/tests; locally you want to see the window

    # --- Files ------------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "data"

    # --- Misc ---------------------------------------------------------------------
    frontend_origin: str = "http://localhost:3000"
    worker_poll_seconds: float = 2.0

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def composio_enabled(self) -> bool:
        return bool(self.composio_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
