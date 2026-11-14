"""Campaign CRUD, lifecycle (launch / pause / resume / run now) and activity."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import activity_json, campaign_json
from app.db import get_session
from app.models import (
    Activity,
    AgentRun,
    Campaign,
    CampaignStatus,
    ExclusionRule,
    PermissionGrant,
    RunStatus,
    utcnow,
)
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

GOAL_TEMPLATES = {
    "sales": {"label": "Sell more of my product", "metric": "sales"},
    "followers": {"label": "Grow my followers", "metric": "followers"},
    "traffic": {"label": "Drive website traffic", "metric": "website visits"},
    "leads": {"label": "Get more leads / sign-ups", "metric": "leads"},
    "awareness": {"label": "Build awareness", "metric": "impressions"},
    "custom": {"label": "Something else", "metric": ""},
}


class ExclusionIn(BaseModel):
    kind: str = Field(pattern="^(action_type|app|site|text)$")
    value: str = Field(min_length=1, max_length=2000)


class GrantIn(BaseModel):
    action_type: str
    scope: str | None = None
    spend_limit_usd: Decimal | None = None


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal_type: str = "custom"
    goal_description: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1, max_length=120)
    target_value: float | None = None
    context: str = ""
    channels: list[str] = []
    budget_total: Decimal = Field(gt=0)
    daily_cap: Decimal | None = Field(default=None, gt=0)
    end_date: datetime | None = None
    cycle_hours: float = Field(default=6.0, ge=0.5, le=72)
    exclusions: list[ExclusionIn] = []
    grants: list[GrantIn] = []
    launch: bool = False


class CampaignPatch(BaseModel):
    name: str | None = None
    goal_description: str | None = None
    primary_metric: str | None = None
    target_value: float | None = None
    context: str | None = None
    channels: list[str] | None = None
    budget_total: Decimal | None = Field(default=None, gt=0)
    daily_cap: Decimal | None = None
    end_date: datetime | None = None
    cycle_hours: float | None = Field(default=None, ge=0.5, le=72)


async def _get(s: AsyncSession, campaign_id: str) -> Campaign:
    c = await s.get(Campaign, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c


@router.get("/meta")
async def meta():
    return {
        "goal_templates": GOAL_TEMPLATES,
        "action_types": [
            {"key": a.key, "label": a.label, "description": a.description, "default": a.default}
            for a in ACTION_TYPES.values()
        ],
    }


@router.get("")
async def list_campaigns(s: AsyncSession = Depends(get_session)):
    campaigns = (await s.execute(select(Campaign).order_by(Campaign.created_at.desc()))).scalars().all()
    return [await campaign_json(s, c) for c in campaigns]


@router.post("")
async def create_campaign(body: CampaignIn, s: AsyncSession = Depends(get_session)):
    for g in body.grants:
        if g.action_type not in ACTION_TYPES:
            raise HTTPException(400, f"Unknown action type {g.action_type}")
        if g.action_type == "spend_money" and g.spend_limit_usd is None:
            raise HTTPException(400, "A spending permission needs a per-action limit")
    c = Campaign(
        name=body.name, goal_type=body.goal_type, goal_description=body.goal_description,
        primary_metric=body.primary_metric, target_value=body.target_value, context=body.context,
        channels=body.channels, budget_total=body.budget_total, daily_cap=body.daily_cap,
        end_date=body.end_date, cycle_hours=body.cycle_hours,
    )
    s.add(c)
    await s.flush()
    for e in body.exclusions:
        s.add(ExclusionRule(campaign_id=c.id, kind=e.kind, value=e.value.strip()))
    for g in body.grants:
        s.add(PermissionGrant(campaign_id=c.id, action_type=g.action_type, scope=g.scope,
                              spend_limit_usd=g.spend_limit_usd))
    await activity.log(s, c.id, "system", "Campaign created", status="info")
    if body.launch:
        await _launch(s, c)
    await s.flush()
    return await campaign_json(s, c, full=True)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, s: AsyncSession = Depends(get_session)):
    return await campaign_json(s, await _get(s, campaign_id), full=True)


@router.patch("/{campaign_id}")
async def patch_campaign(campaign_id: str, body: CampaignPatch, s: AsyncSession = Depends(get_session)):
    c = await _get(s, campaign_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    if "budget_total" in changes and c.status == CampaignStatus.out_of_budget.value:
        c.status = CampaignStatus.paused.value  # the user can resume now that there is budget
    await activity.log(s, c.id, "system", "Campaign settings updated: " + ", ".join(changes), status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c, full=True)


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, s: AsyncSession = Depends(get_session)):
    await s.delete(await _get(s, campaign_id))
    return {"ok": True}


async def _launch(s: AsyncSession, c: Campaign) -> None:
    c.status = CampaignStatus.active.value
    c.next_cycle_at = utcnow()
    await activity.log(s, c.id, "system", "Campaign launched", status="info")
    await notify(s, c.id, "campaign")


@router.post("/{campaign_id}/launch")
async def launch(campaign_id: str, s: AsyncSession = Depends(get_session)):
    c = await _get(s, campaign_id)
    if c.status not in (CampaignStatus.draft.value, CampaignStatus.paused.value):
        raise HTTPException(400, f"Cannot launch a campaign that is {c.status}")
    await _launch(s, c)
    return await campaign_json(s, c)


@router.post("/{campaign_id}/pause")
async def pause(campaign_id: str, s: AsyncSession = Depends(get_session)):
    c = await _get(s, campaign_id)
    c.status = CampaignStatus.paused.value
    await activity.log(s, c.id, "system", "Campaign paused", status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c)


@router.post("/{campaign_id}/resume")
async def resume(campaign_id: str, s: AsyncSession = Depends(get_session)):
    c = await _get(s, campaign_id)
    if c.status == CampaignStatus.completed.value:
        raise HTTPException(400, "This campaign has finished")
    c.status = CampaignStatus.active.value
    # Continue an interrupted cycle if there is one, otherwise start a new one now.
    interrupted = (
        await s.execute(
            update(AgentRun)
            .where(AgentRun.campaign_id == c.id, AgentRun.status == RunStatus.stopped.value,
                   AgentRun.summary.is_(None))
            .values(status=RunStatus.queued.value)
            .returning(AgentRun.id)
        )
    ).all()
    if not interrupted and not c.next_cycle_at:
        c.next_cycle_at = utcnow()
    await activity.log(s, c.id, "system", "Campaign resumed", status="info")
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c)


@router.post("/{campaign_id}/run-now")
async def run_now(campaign_id: str, s: AsyncSession = Depends(get_session)):
    c = await _get(s, campaign_id)
    if c.status != CampaignStatus.active.value:
        raise HTTPException(400, "Launch or resume the campaign first")
    c.next_cycle_at = utcnow()
    await notify(s, c.id, "campaign")
    return await campaign_json(s, c)


@router.get("/{campaign_id}/activity")
async def campaign_activity(
    campaign_id: str, after_id: int | None = None, before_id: int | None = None, limit: int = 100,
    s: AsyncSession = Depends(get_session),
):
    q = select(Activity).where(Activity.campaign_id == campaign_id)
    if after_id is not None:
        q = q.where(Activity.id > after_id).order_by(Activity.id.asc())
    else:
        if before_id is not None:
            q = q.where(Activity.id < before_id)
        q = q.order_by(Activity.id.desc())
    rows = (await s.execute(q.limit(min(limit, 500)))).scalars().all()
    if after_id is None:
        rows = list(reversed(rows))
    return [activity_json(a) for a in rows]
