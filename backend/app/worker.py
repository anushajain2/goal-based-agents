"""Agent worker process.

    python -m app.worker

Loops forever:
  * starts a new cycle for every active campaign whose next check-in is due,
  * claims queued runs (with Postgres, any number of workers can
    run side by side) and drives them with the CycleRunner,
  * recovers runs whose worker died mid-step,
  * runs first-time organization setups (company research -> AI team), see agent/org_setup.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from datetime import timedelta
from pathlib import Path

from sqlalchemy import and_, select, update

from app.agent.org_setup import run_org_setup
from app.agent.runner import CycleRunner
from app.agent.team_lead import run_review, schedule_due_reviews
from app.config import get_settings
from app.db import session_scope
from app.observability import check_and_init
from app.models import AgentRun, Campaign, CampaignStatus, LeadReview, OrgSetup, RunStatus, utcnow
from app.services import activity, targets
from app.services.events import notify

log = logging.getLogger("autopilot.worker")

# A 'stopped' run (campaign paused) is resumed by the API when the campaign resumes, so it
# does not block a new cycle from being scheduled.
OPEN_STATUSES = [RunStatus.queued.value, RunStatus.running.value, RunStatus.waiting.value]
STALE_AFTER = timedelta(minutes=20)
MAX_CONCURRENT_RUNS = int(os.environ.get("AUTOPILOT_MAX_CONCURRENT_RUNS", "3"))
# On a deploy the host sends SIGTERM and waits a while before killing us: finish what we can in
# that time, then hand the rest back so the next worker picks it up at once.
SHUTDOWN_GRACE_SECONDS = float(os.environ.get("AUTOPILOT_SHUTDOWN_GRACE_SECONDS", "20"))


async def schedule_due_cycles() -> int:
    """Create a queued run for each active campaign that is due and has no open run."""
    created = 0
    async with session_scope() as s:
        now = utcnow()
        due = (
            await s.execute(
                select(Campaign)
                .where(Campaign.status == CampaignStatus.active.value,
                       Campaign.next_cycle_at.is_not(None), Campaign.next_cycle_at <= now)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for campaign in due:
            if campaign.end_date and campaign.end_date <= now:
                campaign.status = CampaignStatus.completed.value
                await activity.log(s, campaign.id, "system", "Campaign finished: end date reached", status="info")
                continue
            open_run = (
                await s.execute(
                    select(AgentRun.id).where(AgentRun.campaign_id == campaign.id,
                                              AgentRun.status.in_(OPEN_STATUSES)).limit(1)
                )
            ).scalar_one_or_none()
            if open_run:
                continue
            last = (
                await s.execute(
                    select(AgentRun.cycle_number).where(AgentRun.campaign_id == campaign.id)
                    .order_by(AgentRun.cycle_number.desc()).limit(1)
                )
            ).scalar_one_or_none() or 0
            s.add(AgentRun(campaign_id=campaign.id, cycle_number=last + 1, status=RunStatus.queued.value))
            campaign.next_cycle_at = None
            created += 1
            await notify(s, campaign.id, "run")
    return created


async def roll_over_targets() -> int:
    """Close ended target periods (hit or missed) and start the next ones."""
    closed = 0
    async with session_scope() as s:
        for c in (await s.execute(select(Campaign).where(Campaign.status == CampaignStatus.active.value))).scalars():
            if await targets.roll_over(s, c):
                closed += 1
                await notify(s, c.id, "campaign")
    return closed


async def claim_run(worker_id: str) -> str | None:
    """Atomically take the oldest queued run. Postgres: SKIP LOCKED lets workers claim in
    parallel. SQLite: transactions are serialized, and the status check in the UPDATE makes
    a double claim impossible either way."""
    async with session_scope() as s:
        run_id = (
            await s.execute(
                select(AgentRun.id).where(AgentRun.status == RunStatus.queued.value)
                .order_by(AgentRun.updated_at).limit(1).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if not run_id:
            return None
        result = await s.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status == RunStatus.queued.value)
            .values(status=RunStatus.running.value, locked_by=worker_id, locked_at=utcnow())
        )
        return run_id if result.rowcount == 1 else None


async def recover_stale_runs() -> None:
    async with session_scope() as s:
        await s.execute(
            update(AgentRun)
            .where(and_(AgentRun.status == RunStatus.running.value, AgentRun.locked_at < utcnow() - STALE_AFTER))
            .values(status=RunStatus.queued.value, locked_by=None)
        )


async def claim_setup(worker_id: str) -> str | None:
    """Same claiming pattern as runs, for organization setups."""
    async with session_scope() as s:
        setup_id = (
            await s.execute(
                select(OrgSetup.id).where(OrgSetup.status == "queued")
                .order_by(OrgSetup.created_at).limit(1).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if not setup_id:
            return None
        result = await s.execute(
            update(OrgSetup)
            .where(OrgSetup.id == setup_id, OrgSetup.status == "queued")
            .values(status="running", locked_by=worker_id, locked_at=utcnow(), attempts=OrgSetup.attempts + 1)
        )
        return setup_id if result.rowcount == 1 else None


async def claim_review(worker_id: str) -> str | None:
    """Same claiming pattern, for AI team lead reviews."""
    async with session_scope() as s:
        review_id = (
            await s.execute(
                select(LeadReview.id).where(LeadReview.status == "queued")
                .order_by(LeadReview.created_at).limit(1).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if not review_id:
            return None
        result = await s.execute(
            update(LeadReview).where(LeadReview.id == review_id, LeadReview.status == "queued")
            .values(status="running", locked_by=worker_id, locked_at=utcnow())
        )
        return review_id if result.rowcount == 1 else None


async def recover_stale_reviews() -> None:
    async with session_scope() as s:
        await s.execute(update(LeadReview).where(LeadReview.status == "running", LeadReview.locked_at < utcnow() - STALE_AFTER)
                        .values(status="failed", locked_by=None, error="The review stopped responding."))


async def recover_stale_setups() -> None:
    """A setup whose worker died: try once more, then give up with a clear error."""
    async with session_scope() as s:
        stale = and_(OrgSetup.status == "running", OrgSetup.locked_at < utcnow() - STALE_AFTER)
        await s.execute(update(OrgSetup).where(stale, OrgSetup.attempts < 2)
                        .values(status="queued", locked_by=None))
        await s.execute(update(OrgSetup).where(stale, OrgSetup.attempts >= 2)
                        .values(status="failed", locked_by=None,
                                error="Setup stopped responding. Try again from the setup page."))


async def _drive(runner: CycleRunner, run_id: str) -> None:
    try:
        await runner.run(run_id)
    except Exception as e:
        log.exception("run %s crashed", run_id)
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            run.status = RunStatus.failed.value
            run.error = f"{type(e).__name__}: {e}"[:2000]
            campaign = await s.get(Campaign, run.campaign_id)
            campaign.next_cycle_at = utcnow() + timedelta(hours=1)
            await activity.log(s, run.campaign_id, "error", f"Cycle crashed: {type(e).__name__}: {e}"[:400],
                               run_id=run_id, status="failed")
    finally:
        async with session_scope() as s:
            run = await s.get(AgentRun, run_id)
            if run and run.status == RunStatus.running.value:
                # Runner returned without parking/finishing (should not happen): requeue.
                run.status = RunStatus.queued.value
            if run:
                run.locked_by = None


async def wait_for_schema(timeout_s: float = 900) -> None:
    """On a deploy the API runs the migrations; a new worker waits for them instead of running
    new code against the old tables."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.db import get_engine

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    heads = set(ScriptDirectory.from_config(cfg).get_heads())
    waited = 0.0
    while True:
        async with get_engine().connect() as conn:
            current = set(await conn.run_sync(lambda c: MigrationContext.configure(c).get_current_heads()))
        if current == heads:
            return
        if waited >= timeout_s:
            raise SystemExit(f"database is at {current or 'nothing'}, code expects {heads}: run alembic upgrade head")
        if waited == 0:
            log.info("waiting for database migrations (%s -> %s)", current or "nothing", heads)
        await asyncio.sleep(5)
        waited += 5


async def release_claims(worker_id: str) -> None:
    """Put this worker's unfinished work back in the queue (runs resume from their last step)."""
    async with session_scope() as s:
        await s.execute(update(AgentRun).where(AgentRun.locked_by == worker_id,
                                               AgentRun.status == RunStatus.running.value)
                        .values(status=RunStatus.queued.value, locked_by=None))
        await s.execute(update(OrgSetup).where(OrgSetup.locked_by == worker_id, OrgSetup.status == "running")
                        .values(status="queued", locked_by=None, attempts=OrgSetup.attempts - 1))
        await s.execute(update(LeadReview).where(LeadReview.locked_by == worker_id, LeadReview.status == "running")
                        .values(status="queued", locked_by=None))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check_and_init("worker")
    settings = get_settings()
    if settings.production:
        await wait_for_schema()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    runner = CycleRunner()
    tasks: set[asyncio.Task] = set()
    last_rollover = None
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stopping.set)
        except (NotImplementedError, RuntimeError):  # Windows
            pass
    log.info("worker %s started (max %d concurrent runs)", worker_id, MAX_CONCURRENT_RUNS)
    while not stopping.is_set():
        try:
            await recover_stale_runs()
            await recover_stale_setups()
            await schedule_due_cycles()
            if not last_rollover or utcnow() - last_rollover > timedelta(minutes=1):
                last_rollover = utcnow()
                await roll_over_targets()
                await recover_stale_reviews()
                if settings.anthropic_api_key:
                    await schedule_due_reviews()
            while len(tasks) < MAX_CONCURRENT_RUNS:
                review_id = await claim_review(worker_id)
                if not review_id:
                    break
                log.info("team lead review (%s)", review_id)
                task = asyncio.create_task(run_review(review_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            while len(tasks) < MAX_CONCURRENT_RUNS:
                setup_id = await claim_setup(worker_id)
                if not setup_id:
                    break
                log.info("setting up organization (%s)", setup_id)
                task = asyncio.create_task(run_org_setup(setup_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            while len(tasks) < MAX_CONCURRENT_RUNS:
                run_id = await claim_run(worker_id)
                if not run_id:
                    break
                log.info("running %s", run_id)
                task = asyncio.create_task(_drive(runner, run_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except Exception:
            log.exception("worker loop error")
        try:
            await asyncio.wait_for(stopping.wait(), settings.worker_poll_seconds)
        except TimeoutError:
            pass

    log.info("worker %s stopping: %d task(s) in progress", worker_id, len(tasks))
    if tasks:
        _done, pending = await asyncio.wait(set(tasks), timeout=SHUTDOWN_GRACE_SECONDS)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    await release_claims(worker_id)
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    asyncio.run(main())
