"""Agent worker process.

    python -m app.worker

Loops forever:
  * starts a new cycle for every active campaign whose next check-in is due,
  * claims queued runs (Postgres `FOR UPDATE SKIP LOCKED`, so any number of workers can
    run side by side) and drives them with the CycleRunner,
  * recovers runs whose worker died mid-step.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import timedelta

from sqlalchemy import and_, select, text, update

from app.agent.runner import CycleRunner
from app.config import get_settings
from app.db import session_scope
from app.models import AgentRun, Campaign, CampaignStatus, RunStatus, utcnow
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
    async with session_scope() as s:
        row = (
            await s.execute(
                text(
                    """
                    UPDATE agent_runs SET status = 'running', locked_by = :worker, locked_at = now()
                    WHERE id = (
                        SELECT id FROM agent_runs WHERE status = 'queued'
                        ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 1
                    )
                    RETURNING id
                    """
                ),
                {"worker": worker_id},
            )
        ).first()
        return row[0] if row else None


async def recover_stale_runs() -> None:
    async with session_scope() as s:
        await s.execute(
            update(AgentRun)
            .where(and_(AgentRun.status == RunStatus.running.value, AgentRun.locked_at < utcnow() - STALE_AFTER))
            .values(status=RunStatus.queued.value, locked_by=None)
        )


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
            await schedule_due_cycles()
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
