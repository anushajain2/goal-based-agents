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
import socket
from datetime import timedelta

from sqlalchemy import and_, select, update

from app.agent.org_setup import run_org_setup
from app.agent.runner import CycleRunner
from app.config import get_settings
from app.db import session_scope
from app.models import AgentRun, Campaign, CampaignStatus, OrgSetup, RunStatus, utcnow
from app.services import activity
from app.services.events import notify

log = logging.getLogger("autopilot.worker")

# A 'stopped' run (campaign paused) is resumed by the API when the campaign resumes, so it
# does not block a new cycle from being scheduled.
OPEN_STATUSES = [RunStatus.queued.value, RunStatus.running.value, RunStatus.waiting.value]
STALE_AFTER = timedelta(minutes=20)
MAX_CONCURRENT_RUNS = int(os.environ.get("AUTOPILOT_MAX_CONCURRENT_RUNS", "3"))


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


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    runner = CycleRunner()
    tasks: set[asyncio.Task] = set()
    log.info("worker %s started (max %d concurrent runs)", worker_id, MAX_CONCURRENT_RUNS)
    while True:
        try:
            await recover_stale_runs()
            await recover_stale_setups()
            await schedule_due_cycles()
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
        await asyncio.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
