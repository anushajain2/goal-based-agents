"""Deciding on what an AI employee asked for: approve (maybe edited, maybe "don't ask again"),
decline, answer. Shared by the Needs you inbox and WhatsApp, so the rules are the same wherever
someone decides: who may decide, which fields can be edited, standing permissions, hand-offs,
tightening after stopped heads-ups, and waking the run that waits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    AgentRun,
    Campaign,
    Deliverable,
    PermissionGrant,
    RequestKind,
    RequestStatus,
    RunStatus,
    UserRequest,
    utcnow,
)
from app.org import Member, approvers, can_decide
from app.services import activity, autonomy
from app.services.events import notify
from app.services.handoff import hand_off
from app.services.policy import ACTION_TYPES
from app.services.proposals import apply_change


class DecisionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class DecisionIn:
    decision: str  # approve | reject
    note: str | None = None
    edited_fields: dict | None = None
    remember: bool = False
    remember_scope: str = "goal"  # goal | department | org (campaign / all are old names)
    remember_any_channel: bool = False
    spend_limit_usd: Decimal | None = None
    via: str = "app"  # app | whatsapp


async def decide(s: AsyncSession, me: Member, request_id: str, body: DecisionIn) -> tuple[UserRequest, Campaign]:
    req = (
        await s.execute(select(UserRequest).where(UserRequest.id == request_id).with_for_update())
    ).scalar_one_or_none()
    campaign = await s.get(Campaign, req.campaign_id) if req else None
    if not req or not campaign or campaign.org_id != me.org_id:
        raise DecisionError(404, "Request not found")
    if not await can_decide(s, me, req.campaign_id, req.department_id):
        people = ", ".join(u.name or u.email for u in await approvers(s, me.org_id, req.department_id, campaign.agent_id))
        raise DecisionError(403, f"This goes to {people}, who the AI employee reports to (or an admin).")
    if req.status != RequestStatus.pending.value:
        raise DecisionError(409, f"Already {req.status}")

    approved = body.decision == "approve"
    if req.kind == RequestKind.question.value and approved and not (body.note or "").strip():
        raise DecisionError(400, "Write an answer first.")
    req.status = RequestStatus.approved.value if approved else RequestStatus.rejected.value
    req.decision_note = body.note
    req.decided_at = utcnow()
    req.decided_by = me.user.id
    who = me.user.name or me.user.email

    if approved and body.edited_fields:
        editable = set((req.preview or {}).get("editable") or [])
        bad = set(body.edited_fields) - editable
        if bad:
            raise DecisionError(400, f"These fields cannot be edited: {', '.join(sorted(bad))}")
        req.edited_fields = body.edited_fields

    grant_note = ""
    if approved and body.remember and req.kind == RequestKind.action.value and req.action_type:
        scope = {"campaign": "goal", "all": "org"}.get(body.remember_scope, body.remember_scope)
        if scope == "org" and not me.is_admin:
            raise DecisionError(403, "Only admins can allow something for the whole organization.")
        if scope == "department" and not req.department_id:
            scope = "goal"
        if req.action_type == "spend_money":
            limit = body.spend_limit_usd or req.est_spend_usd
            if limit is None:
                raise DecisionError(400, "Set a per-action spending limit to stop being asked")
        else:
            limit = None
        req.remember = True
        # Replaces this level's own setting for the same kind of action (e.g. a heads-up from a preset).
        same = select(PermissionGrant).where(
            PermissionGrant.action_type == req.action_type, PermissionGrant.revoked_at.is_(None),
            PermissionGrant.scope.is_(None) if body.remember_any_channel or not req.scope else PermissionGrant.scope == req.scope)
        same = (same.where(PermissionGrant.campaign_id == req.campaign_id) if scope == "goal"
                else same.where(PermissionGrant.campaign_id.is_(None), PermissionGrant.department_id == req.department_id)
                if scope == "department"
                else same.where(PermissionGrant.org_id == me.org_id, PermissionGrant.campaign_id.is_(None),
                                PermissionGrant.department_id.is_(None)))
        for old in (await s.execute(same)).scalars():
            old.revoked_at = utcnow()
        s.add(PermissionGrant(
            org_id=me.org_id, owner_id=me.user.id, granted_by=me.user.id,
            campaign_id=req.campaign_id if scope == "goal" else None,
            department_id=req.department_id if scope == "department" else None,
            action_type=req.action_type,
            scope=None if body.remember_any_channel else req.scope,
            spend_limit_usd=limit, mode="auto", source="user",
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

    handoff_note = ""
    if req.kind == RequestKind.proposal.value and approved:
        try:
            handoff_note = ": " + await apply_change(s, campaign, (req.preview or {}).get("change") or {},
                                                     req.rationale, req.edited_fields)
        except ValueError as e:
            raise DecisionError(400, str(e)) from None
    if req.kind == RequestKind.review.value:
        d = await s.get(Deliverable, (req.preview or {}).get("deliverable_id") or "-")
        if d and d.org_id == me.org_id:
            if req.edited_fields and "content" in req.edited_fields:
                d.content = req.edited_fields["content"]
            if not approved:
                d.status = "changes_requested"
            else:
                d.status = "approved"
                source = await s.get(Agent, d.agent_id) if d.agent_id else None
                target = await s.get(Agent, source.handoff_to_agent_id) if source and source.handoff_to_agent_id else None
                if target and d.kind == "prd":
                    await hand_off(s, d, source, target, who)
                    handoff_note = f" and handed to {target.name}"

    heads_up = req.auto_approve_at is not None
    if heads_up and not approved:
        grant_note += await autonomy.after_stop(s, req, campaign)
    verb = {"action": ("Sent now" if approved else "Stopped") if heads_up else "Approved" if approved else "Declined",
            "login": "Signed in" if approved else "Declined sign-in",
            "connect": "Connected" if approved else "Declined to connect",
            "question": "Answered" if approved else "Skipped the question",
            "review": "Approved" if approved else "Asked for changes to",
            "proposal": "Approved" if approved else "Kept things as they are instead of"}[req.kind]
    edited = " (edited)" if req.edited_fields else ""
    await activity.log(
        s, req.campaign_id, "decision", f"{verb}{edited} by {who}: {req.title}{grant_note}{handoff_note}", run_id=req.run_id,
        status="approved" if approved else "rejected", action_type=req.action_type, channel=req.scope,
        details={"request_id": req.id, "note": body.note, "edited_fields": req.edited_fields, "decided_by": who,
                 **({"via": body.via} if body.via != "app" else {})},
    )

    # Wake the parked run so a worker finishes the action.
    if req.run_id:
        run = await s.get(AgentRun, req.run_id)
        if run and run.status == RunStatus.waiting.value:
            run.status = RunStatus.queued.value
    await notify(s, req.campaign_id, "request", id=req.id)
    return req, campaign
