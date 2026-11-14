"""The approvals inbox: approve / approve & don't ask again / edit / reject."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import request_json
from app.db import get_session
from app.models import (
    AgentRun,
    Campaign,
    PermissionGrant,
    RequestKind,
    RequestStatus,
    RunStatus,
    UserRequest,
    utcnow,
)
from app.services import activity
from app.services.events import notify
from app.services.policy import ACTION_TYPES

router = APIRouter(prefix="/api/requests", tags=["requests"])


class Decision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = None
    edited_fields: dict | None = None
    # "Approve & don't ask again"
    remember: bool = False
    remember_scope: str = Field(default="campaign", pattern="^(campaign|all)$")
    remember_any_channel: bool = False  # default: only for this app/site
    spend_limit_usd: Decimal | None = None


@router.get("")
async def list_requests(status: str | None = "pending", campaign_id: str | None = None, limit: int = 100,
                        s: AsyncSession = Depends(get_session)):
    q = select(UserRequest, Campaign.name).join(Campaign, Campaign.id == UserRequest.campaign_id)
    if status:
        q = q.where(UserRequest.status == status)
    if campaign_id:
        q = q.where(UserRequest.campaign_id == campaign_id)
    rows = (await s.execute(q.order_by(UserRequest.created_at.desc()).limit(min(limit, 500)))).all()
    return [request_json(r, name) for r, name in rows]


@router.post("/{request_id}/decide")
async def decide(request_id: str, body: Decision, s: AsyncSession = Depends(get_session)):
    req = (
        await s.execute(select(UserRequest).where(UserRequest.id == request_id).with_for_update())
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != RequestStatus.pending.value:
        raise HTTPException(409, f"Already {req.status}")

    approved = body.decision == "approve"
    req.status = RequestStatus.approved.value if approved else RequestStatus.rejected.value
    req.decision_note = body.note
    req.decided_at = utcnow()

    if approved and body.edited_fields:
        editable = set((req.preview or {}).get("editable") or [])
        bad = set(body.edited_fields) - editable
        if bad:
            raise HTTPException(400, f"These fields cannot be edited: {', '.join(sorted(bad))}")
        req.edited_fields = body.edited_fields

    campaign = await s.get(Campaign, req.campaign_id)
    grant_note = ""
    if approved and body.remember and req.kind == RequestKind.action.value and req.action_type:
        if req.action_type == "spend_money":
            limit = body.spend_limit_usd or req.est_spend_usd
            if limit is None:
                raise HTTPException(400, "Set a per-action spending limit to stop being asked")
        else:
            limit = None
        req.remember = True
        s.add(PermissionGrant(
            campaign_id=None if body.remember_scope == "all" else req.campaign_id,
            action_type=req.action_type,
            scope=None if body.remember_any_channel else req.scope,
            spend_limit_usd=limit,
        ))
        label = ACTION_TYPES[req.action_type].label if req.action_type in ACTION_TYPES else req.action_type
        where = "" if body.remember_any_channel or not req.scope else f" on {req.scope}"
        grant_note = f' · won\'t ask again for "{label}"{where}'
        if body.remember_scope == "all":
            for c in (await s.execute(select(Campaign))).scalars():
                c.guardrail_version += 1
        else:
            campaign.guardrail_version += 1

    verb = {"action": "Approved" if approved else "Declined",
            "login": "Signed in" if approved else "Declined sign-in",
            "connect": "Connected" if approved else "Declined to connect"}[req.kind]
    edited = " (edited)" if req.edited_fields else ""
    await activity.log(
        s, req.campaign_id, "decision", f"{verb}{edited}: {req.title}{grant_note}", run_id=req.run_id,
        status="approved" if approved else "rejected", action_type=req.action_type, channel=req.scope,
        details={"request_id": req.id, "note": body.note, "edited_fields": req.edited_fields},
    )

    # Wake the parked run so a worker finishes the action.
    if req.run_id:
        run = await s.get(AgentRun, req.run_id)
        if run and run.status == RunStatus.waiting.value:
            run.status = RunStatus.queued.value
    await notify(s, req.campaign_id, "request", id=req.id)
    return request_json(req, campaign.name)
