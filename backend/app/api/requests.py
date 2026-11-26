"""The "Needs you" inbox: approvals, questions, sign-ins and app connections from AI employees.

Each request goes to the person the AI employee reports to on the org chart (see org.approvers).
That person, or an admin, decides; they can add a comment, which the AI employee reads.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import request_json
from app.db import get_session
from app.models import (
    Agent,
    Campaign,
    Department,
    User,
    UserRequest,
)
from app.org import Member, approvers, current_member, routed_to_me
from app.services import decisions

router = APIRouter(prefix="/api/requests", tags=["requests"])


class Decision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = None
    edited_fields: dict | None = None
    # "Approve & don't ask again": for this goal, every goal in its department, or the whole org.
    remember: bool = False
    remember_scope: str = Field(default="goal", pattern="^(goal|department|org|campaign|all)$")
    remember_any_channel: bool = False  # default: only for this app/site
    spend_limit_usd: Decimal | None = None


async def _enrich(s: AsyncSession, me: Member, rows) -> list[dict]:
    dept_names = dict((await s.execute(select(Department.id, Department.name).where(Department.org_id == me.org_id))).all())
    agents = {a.id: a for a in (await s.execute(select(Agent).where(Agent.org_id == me.org_id))).scalars()}
    deciders = {r.decided_by for r, *_ in rows if r.decided_by}
    names = {
        uid: (name or email)
        for uid, name, email in (
            await s.execute(select(User.id, User.name, User.email).where(User.id.in_(deciders or ["-"])))
        ).all()
    }
    cache: dict[str | None, list] = {}
    out = []
    for r, campaign_name, agent_id, *rest in rows:
        if agent_id not in cache:
            cache[agent_id] = await approvers(s, me.org_id, r.department_id, agent_id)
        people = cache[agent_id]
        agent = agents.get(agent_id)
        out.append({
            **request_json(r, campaign_name),
            "department_id": r.department_id,
            "department_name": dept_names.get(r.department_id),
            "agent_id": agent_id,
            # A team lead's suggestion without an AI employee yet comes from the lead itself.
            "agent_name": agent.name if agent else (r.preview or {}).get("lead"),
            "agent_title": agent.title if agent else ("Reviewer" if (r.preview or {}).get("lead") else None),
            "campaign_metric": rest[0] if rest else None,
            "approvers": [u.name or u.email for u in people],
            "routed_to_me": me.user.id in {u.id for u in people},
            "can_decide": me.is_admin or me.user.id in {u.id for u in people},
            "decided_by_name": names.get(r.decided_by),
        })
    return out


@router.get("")
async def list_requests(status: str | None = "pending", campaign_id: str | None = None,
                        scope: str = "mine", limit: int = 100,
                        s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """scope=mine: what's routed to me. scope=all: everything in the organization (view only)."""
    q = (
        select(UserRequest, Campaign.name, Campaign.agent_id, Campaign.primary_metric)
        .join(Campaign, Campaign.id == UserRequest.campaign_id)
        .where(Campaign.org_id == me.org_id)
    )
    if status:
        q = q.where(UserRequest.status == status)
    if campaign_id:
        q = q.where(UserRequest.campaign_id == campaign_id)
    elif scope == "mine":
        q = q.where(await routed_to_me(s, me))
    rows = (await s.execute(q.order_by(UserRequest.created_at.desc()).limit(min(limit, 500)))).all()
    return await _enrich(s, me, rows)


@router.post("/{request_id}/decide")
async def decide(request_id: str, body: Decision, s: AsyncSession = Depends(get_session),
                 me: Member = Depends(current_member)):
    try:
        req, campaign = await decisions.decide(s, me, request_id, decisions.DecisionIn(**body.model_dump()))
    except decisions.DecisionError as e:
        raise HTTPException(e.status, e.message) from None
    return (await _enrich(s, me, [(req, campaign.name, campaign.agent_id, campaign.primary_metric)]))[0]
