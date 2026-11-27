"""Make one launch video, start to finish (run by the worker).

    look at the site -> Claude writes the storyboard -> render -> store -> send for review

The finished video goes to the goal's Reviewer like any other piece of work: they watch it, can
edit the copy to post it with, and approve. Nothing is posted from here.
"""

from __future__ import annotations

import logging
import shutil
from decimal import Decimal

from app.agent.llm import MeteredClaude
from app.config import get_settings
from app.db import session_scope
from app.models import Campaign, Deliverable, Department, LaunchVideo, Organization, RequestKind, UserRequest, utcnow
from app.org import approvers, goal_department
from app.services import activity
from app.services.events import notify
from app.services.mailer import send_approval_needed
from app.video import capture as capture_mod
from app.video import render as render_mod
from app.video import storyboard as storyboard_mod

log = logging.getLogger(__name__)


async def _step(video_id: str, step: str) -> None:
    async with session_scope() as s:
        v = await s.get(LaunchVideo, video_id)
        v.step = step
        v.locked_at = utcnow()  # still alive


async def run_video(video_id: str, claude: MeteredClaude | None = None) -> None:
    claude = claude or MeteredClaude()
    async with session_scope() as s:
        v = await s.get(LaunchVideo, video_id)
        org = await s.get(Organization, v.org_id)
        url, fmt, notes, campaign_id, name = v.url, v.format, v.notes, v.campaign_id, org.name if org else ""
    job = get_settings().data_dir / "videos" / video_id
    cost = Decimal("0")
    try:
        await _step(video_id, "Looking at your website")
        cap = await capture_mod.capture(url, job, fmt)
        if not cap.shots:
            raise RuntimeError("Couldn't take screenshots of the site")

        await _step(video_id, "Writing the story")
        sb, extras, cost = await storyboard_mod.write(claude, cap, job, name=name or cap.title or "", fmt=fmt,
                                                      notes=notes, campaign_id=campaign_id)

        await _step(video_id, "Rendering the video")
        out = await render_mod.render(job, sb)

        async with session_scope() as s:
            v = await s.get(LaunchVideo, video_id)
            v.storyboard, v.title, v.share_copy, v.seconds = sb, extras["title"], extras["share_copy"], out.seconds
            v.video, v.poster = out.video.read_bytes(), out.poster.read_bytes()
            v.cost_usd = cost
            v.status, v.step, v.locked_by = "done", "Ready", None
            if v.campaign_id:
                await _send_for_review(s, v)
    except Exception as e:  # noqa: BLE001 - every failure ends the job with a clear message
        log.exception("launch video %s failed", video_id)
        message = str(e) if isinstance(e, (render_mod.RenderError, RuntimeError)) else f"{type(e).__name__}: {e}"
        async with session_scope() as s:
            v = await s.get(LaunchVideo, video_id)
            v.status, v.error, v.locked_by, v.cost_usd = "failed", message[:2000], None, cost
            if v.campaign_id:
                await activity.log(s, v.campaign_id, "error", f"Couldn't make the launch video: {message}"[:400],
                                   status="failed", details={"video_id": v.id})
    finally:
        shutil.rmtree(job, ignore_errors=True)


async def _send_for_review(s, v: LaunchVideo) -> None:
    campaign = await s.get(Campaign, v.campaign_id)
    d = Deliverable(org_id=v.org_id, campaign_id=campaign.id, agent_id=campaign.agent_id, kind="video",
                    title=v.title, content=v.share_copy,
                    summary=f"A {round(v.seconds or 0)}-second launch video made from {v.url}, with copy to post it with.")
    s.add(d)
    await s.flush()
    v.deliverable_id = d.id
    department_id = await goal_department(s, campaign)
    req = UserRequest(campaign_id=campaign.id, kind=RequestKind.review.value, title=f"Review video: {v.title}"[:300],
                      rationale=d.summary, department_id=department_id,
                      preview={"deliverable_id": d.id, "kind": "video", "video_id": v.id,
                               "fields": {"content": v.share_copy}, "editable": ["content"]})
    s.add(req)
    await s.flush()
    people = await approvers(s, campaign.org_id, department_id, campaign.agent_id) if campaign.org_id else []
    await activity.log(s, campaign.id, "action", f"Made a launch video: {v.title}", status="done",
                       details={"deliverable_id": d.id, "video_id": v.id})
    await activity.log(s, campaign.id, "request", f"Asked {', '.join(p.name or p.email for p in people) or 'the owner'}: "
                       f"{req.title}", status="waiting", details={"request_id": req.id})
    await notify(s, campaign.id, "request", id=req.id)
    dept = await s.get(Department, department_id) if department_id else None
    emails, goal_name, dept_name = [p.email for p in people], campaign.name, dept.name if dept else "your organization"
    try:
        await send_approval_needed(emails, "Oton", dept_name, req.title, campaign.id, goal_name)
    except Exception:  # noqa: BLE001 - email is best effort; the inbox is the source of truth
        log.warning("approval email for video %s failed", v.id)
