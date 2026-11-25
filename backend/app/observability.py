"""Start-up checks and optional error reporting, shared by the API and the worker."""

from __future__ import annotations

import logging
import sys

from app.config import get_settings

log = logging.getLogger("autopilot")


def check_and_init(process: str) -> None:
    """Refuse to start a misconfigured hosted copy; log warnings; turn on Sentry if configured."""
    settings = get_settings()
    problems = settings.check_production()
    if problems:
        for p in problems:
            print(f"[autopilot {process}] config error: {p}", file=sys.stderr)
        raise SystemExit(1)
    for w in settings.production_warnings():
        log.warning("%s: %s", process, w)
    if settings.sentry_dsn:
        try:
            import sentry_sdk
        except ImportError:
            log.warning("SENTRY_DSN is set but sentry-sdk isn't installed")
            return
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.0,
                        send_default_pii=False, server_name=process)
