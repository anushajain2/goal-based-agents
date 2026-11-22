"""The approvals inbox. Requests are routed to the department of the AI employee that raised them:
anyone in that department (or an admin) can approve, edit or decline."""

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
    AgentRun,
    Campaign,
    Department,
    PermissionGrant,
    RequestKind,
    RequestStatus,
    RunStatus,
    User,
    UserRequest,
    utcnow,
)
from app.org import Member, approvers, can_decide, current_member, departments_without_people, routed_to_me
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES

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
    agent_names = dict((await s.execute(select(Agent.id, Agent.name).where(Agent.org_id == me.org_id))).all())
    deciders = {r.decided_by for r, *_ in rows if r.decided_by}
    names = {
        uid: (name or email)
        for uid, name, email in (
            await s.execute(select(User.id, User.name, User.email).where(User.id.in_(deciders or ["-"])))
        ).all()
    }
    approver_cache: dict[str | None, list[str]] = {}
    out = []
    for r, campaign_name, agent_id in rows:
        if r.department_id not in approver_cache:
            approver_cache[r.department_id] = [u.name or u.email for u in await approvers(s, me.org_id, r.department_id)]
        out.append({
            **request_json(r, campaign_name),
            "department_id": r.department_id,
            "department_name": dept_names.get(r.department_id),
            "agent_name": agent_names.get(agent_id),
            "approvers": approver_cache[r.department_id],
            "can_decide": await can_decide(s, me, r.department_id),
            "decided_by_name": names.get(r.decided_by),
        })
    return out


@router.get("")
async def list_requests(status: str | None = "pending", campaign_id: str | None = None,
                        scope: str = "mine", limit: int = 100,
                        s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """scope=mine: what's routed to me. scope=all: everything in the organization (view only)."""
    q = (
        select(UserRequest, Campaign.name, Campaign.agent_id)
        .join(Campaign, Campaign.id == UserRequest.campaign_id)
        .where(Campaign.org_id == me.org_id)
    )
    if status:
        q = q.where(UserRequest.status == status)
    if campaign_id:
        q = q.where(UserRequest.campaign_id == campaign_id)
    elif scope == "mine":
        q = q.where(routed_to_me(me, await departments_without_people(s, me.org_id)))
    rows = (await s.execute(q.order_by(UserRequest.created_at.desc()).limit(min(limit, 500)))).all()
    return await _enrich(s, me, rows)


@router.post("/{request_id}/decide")
async def decide(request_id: str, body: Decision, s: AsyncSession = Depends(get_session),
                 me: Member = Depends(current_member)):
    req = (
        await s.execute(select(UserRequest).where(UserRequest.id == request_id).with_for_update())
    ).scalar_one_or_none()
    campaign = await s.get(Campaign, req.campaign_id) if req else None
    if not req or not campaign or campaign.org_id != me.org_id:
        raise HTTPException(404, "Request not found")
    if not await can_decide(s, me, req.department_id):
        raise HTTPException(403, "This request is for another department. Someone in that department (or an admin) can decide.")
    if req.status != RequestStatus.pending.value:
        raise HTTPException(409, f"Already {req.status}")

    approved = body.decision == "approve"
    req.status = RequestStatus.approved.value if approved else RequestStatus.rejected.value
    req.decision_note = body.note
    req.decided_at = utcnow()
    req.decided_by = me.user.id
    who = me.user.name or me.user.email

    if approved and body.edited_fields:
        editable = set((req.preview or {}).get("editable") or [])
        bad = set(body.edited_fields) - editable
        if bad:
            raise HTTPException(400, f"These fields cannot be edited: {', '.join(sorted(bad))}")
        req.edited_fields = body.edited_fields

    grant_note = ""
    if approved and body.remember and req.kind == RequestKind.action.value and req.action_type:
        scope = {"campaign": "goal", "all": "org"}.get(body.remember_scope, body.remember_scope)
        if scope == "org" and not me.is_admin:
            raise HTTPException(403, "Only admins can allow something for the whole organization.")
        if scope == "department" and not req.department_id:
            scope = "goal"
        if req.action_type == "spend_money":
            limit = body.spend_limit_usd or req.est_spend_usd
            if limit is None:
                raise HTTPException(400, "Set a per-action spending limit to stop being asked")
        else:
            limit = None
        req.remember = True
        s.add(PermissionGrant(
            org_id=me.org_id, owner_id=me.user.id, granted_by=me.user.id,
            campaign_id=req.campaign_id if scope == "goal" else None,
            department_id=req.department_id if scope == "department" else None,
            action_type=req.action_type,
            scope=None if body.remember_any_channel else req.scope,
            spend_limit_usd=limit,
        ))
        label = ACTION_TYPES[req.action_type].label if req.action_type in ACTION_TYPES else req.action_type
        where = "" if body.remember_any_channel or not req.scope else f" on {req.scope}"
        across = {"goal": "", "department": " across the department", "org": " across the organization"}[scope]
        grant_note = f' · won\'t ask again for "{label}"{where}{across}'
        affected = select(Campaign).where(Campaign.org_id == me.org_id)
        if scope == "goal":
            affected = affected.where(Campaign.id == campaign.id)
        elif scope == "department":
            affected = affected.where(Campaign.agent_id.in_(select(Agent.id).where(Agent.department_id == req.department_id)))
        for c in (await s.execute(affected)).scalars():
            c.guardrail_version += 1

    verb = {"action": "Approved" if approved else "Declined",
            "login": "Signed in" if approved else "Declined sign-in",
            "connect": "Connected" if approved else "Declined to connect"}[req.kind]
    edited = " (edited)" if req.edited_fields else ""
    await activity.log(
        s, req.campaign_id, "decision", f"{verb}{edited} by {who}: {req.title}{grant_note}", run_id=req.run_id,
        status="approved" if approved else "rejected", action_type=req.action_type, channel=req.scope,
        details={"request_id": req.id, "note": body.note, "edited_fields": req.edited_fields, "decided_by": who},
    )

    # Wake the parked run so a worker finishes the action.
    if req.run_id:
        run = await s.get(AgentRun, req.run_id)
        if run and run.status == RunStatus.waiting.value:
            run.status = RunStatus.queued.value
    await notify(s, req.campaign_id, "request", id=req.id)
    return (await _enrich(s, me, [(req, campaign.name, campaign.agent_id)]))[0]
