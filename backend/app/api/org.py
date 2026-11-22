"""Organization, departments, AI employees, people and invitations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import EMAIL_PATTERN, current_user
from app.db import get_session
from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    Department,
    DepartmentMember,
    Invitation,
    LedgerEntry,
    Membership,
    Organization,
    Role,
    User,
    UserRequest,
)
from app.org import (
    DEPARTMENT_PRESETS,
    Member,
    add_department,
    approvers,
    create_organization,
    current_member,
    default_agent_name,
    load_member,
    require_admin,
)

router = APIRouter(prefix="/api", tags=["organization"])


def _user(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email}


# --- setup -------------------------------------------------------------------------------------

@router.get("/org/presets")
async def presets():
    return {"departments": [{"kind": k, "name": n} for k, n in DEPARTMENT_PRESETS]}


class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    departments: list[str] = Field(default_factory=list, max_length=30)


@router.post("/org")
async def create_org(body: OrgIn, s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    if await load_member(s, user):
        raise HTTPException(409, "You already belong to an organization.")
    if not body.departments:
        raise HTTPException(400, "Pick at least one department.")
    org = await create_organization(s, user, body.name, body.departments)
    return {"id": org.id, "name": org.name}


# --- the organization at a glance --------------------------------------------------------------

async def _agent_stats(s: AsyncSession, org_id: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for agent_id, n, active in (
        await s.execute(
            select(Campaign.agent_id, func.count(), func.sum(case((Campaign.status == "active", 1), else_=0)))
            .where(Campaign.org_id == org_id).group_by(Campaign.agent_id)
        )
    ).all():
        stats[agent_id] = {"goals": n, "active_goals": int(active or 0), "spent": 0.0, "working": False, "needs_you": 0}
    for agent_id, spent in (
        await s.execute(
            select(Campaign.agent_id, func.coalesce(func.sum(LedgerEntry.amount_usd), 0))
            .join(Campaign, Campaign.id == LedgerEntry.campaign_id)
            .where(Campaign.org_id == org_id, LedgerEntry.status == "settled").group_by(Campaign.agent_id)
        )
    ).all():
        stats.setdefault(agent_id, {"goals": 0, "active_goals": 0, "working": False, "needs_you": 0})["spent"] = float(spent)
    for (agent_id,) in (
        await s.execute(
            select(Campaign.agent_id).join(AgentRun, AgentRun.campaign_id == Campaign.id)
            .where(Campaign.org_id == org_id, AgentRun.status.in_(["queued", "running"])).distinct()
        )
    ).all():
        stats.setdefault(agent_id, {"goals": 0, "active_goals": 0, "spent": 0.0, "needs_you": 0})["working"] = True
    for agent_id, n in (
        await s.execute(
            select(Campaign.agent_id, func.count()).join(UserRequest, UserRequest.campaign_id == Campaign.id)
            .where(Campaign.org_id == org_id, UserRequest.status == "pending").group_by(Campaign.agent_id)
        )
    ).all():
        stats.setdefault(agent_id, {"goals": 0, "active_goals": 0, "spent": 0.0, "working": False})["needs_you"] = n
    return stats


@router.get("/org")
async def get_org(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    org = await s.get(Organization, me.org_id)
    departments = (await s.execute(select(Department).where(Department.org_id == me.org_id).order_by(Department.created_at))).scalars().all()
    agents = (await s.execute(select(Agent).where(Agent.org_id == me.org_id).order_by(Agent.created_at))).scalars().all()
    rows = (
        await s.execute(select(User, Membership.role).join(Membership, Membership.user_id == User.id)
                        .where(Membership.org_id == me.org_id).order_by(Membership.created_at))
    ).all()
    dept_members = (
        await s.execute(select(DepartmentMember.department_id, DepartmentMember.user_id)
                        .join(Department, Department.id == DepartmentMember.department_id)
                        .where(Department.org_id == me.org_id))
    ).all()
    by_dept: dict[str, list[str]] = {}
    by_user: dict[str, list[str]] = {}
    for d, u in dept_members:
        by_dept.setdefault(d, []).append(u)
        by_user.setdefault(u, []).append(d)
    users = {u.id: u for u, _ in rows}
    stats = await _agent_stats(s, me.org_id)
    empty = {"goals": 0, "active_goals": 0, "spent": 0.0, "working": False, "needs_you": 0}
    invitations = []
    if me.is_admin:
        invitations = [
            {"id": i.id, "email": i.email, "role": i.role, "department_ids": i.department_ids,
             "created_at": i.created_at.isoformat()}
            for i in (await s.execute(select(Invitation).where(Invitation.org_id == me.org_id,
                                                                Invitation.accepted_at.is_(None)))).scalars()
        ]
    return {
        "org": {"id": org.id, "name": org.name},
        "me": {**_user(me.user), "role": me.role, "department_ids": sorted(me.department_ids), "is_admin": me.is_admin},
        "departments": [
            {
                "id": d.id, "name": d.name, "kind": d.kind,
                "people": [_user(users[u]) for u in by_dept.get(d.id, []) if u in users],
                "agents": [
                    {"id": a.id, "name": a.name, "title": a.title, **stats.get(a.id, empty)}
                    for a in agents if a.department_id == d.id
                ],
            }
            for d in departments
        ],
        "members": [{**_user(u), "role": role, "department_ids": by_user.get(u.id, [])} for u, role in rows],
        "invitations": invitations,
    }


class OrgPatch(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.patch("/org")
async def rename_org(body: OrgPatch, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    (await s.get(Organization, me.org_id)).name = body.name.strip()
    return {"ok": True}


# --- departments -------------------------------------------------------------------------------

class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = ""


async def _department(s: AsyncSession, me: Member, department_id: str) -> Department:
    d = await s.get(Department, department_id)
    if not d or d.org_id != me.org_id:
        raise HTTPException(404, "Department not found")
    return d


@router.post("/departments")
async def create_department(body: DepartmentIn, s: AsyncSession = Depends(get_session),
                            me: Member = Depends(current_member)):
    require_admin(me)
    d = await add_department(s, me.org_id, body.name, body.kind, members=[me.user.id])
    return {"id": d.id, "name": d.name}


@router.patch("/departments/{department_id}")
async def rename_department(department_id: str, body: DepartmentIn, s: AsyncSession = Depends(get_session),
                            me: Member = Depends(current_member)):
    require_admin(me)
    d = await _department(s, me, department_id)
    d.name = body.name.strip()
    return {"ok": True}


@router.delete("/departments/{department_id}")
async def delete_department(department_id: str, s: AsyncSession = Depends(get_session),
                            me: Member = Depends(current_member)):
    require_admin(me)
    d = await _department(s, me, department_id)
    goals = (
        await s.execute(select(func.count()).select_from(Campaign).join(Agent, Agent.id == Campaign.agent_id)
                        .where(Agent.department_id == d.id))
    ).scalar_one()
    if goals:
        raise HTTPException(400, "This department's AI employees still have goals. Move or delete those first.")
    await s.delete(d)
    return {"ok": True}


class PeopleIn(BaseModel):
    user_ids: list[str]


@router.put("/departments/{department_id}/people")
async def set_department_people(department_id: str, body: PeopleIn, s: AsyncSession = Depends(get_session),
                                me: Member = Depends(current_member)):
    require_admin(me)
    d = await _department(s, me, department_id)
    valid = set(
        (await s.execute(select(Membership.user_id).where(Membership.org_id == me.org_id,
                                                           Membership.user_id.in_(body.user_ids or ["-"])))).scalars()
    )
    await s.execute(delete(DepartmentMember).where(DepartmentMember.department_id == d.id))
    for uid in valid:
        s.add(DepartmentMember(department_id=d.id, user_id=uid))
    return {"ok": True}


# --- AI employees ----------------------------------------------------------------------------------

class AgentIn(BaseModel):
    department_id: str
    name: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=160)


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    department_id: str | None = None


async def _agent(s: AsyncSession, me: Member, agent_id: str) -> Agent:
    a = await s.get(Agent, agent_id)
    if not a or a.org_id != me.org_id:
        raise HTTPException(404, "AI employee not found")
    return a


@router.post("/agents")
async def hire_agent(body: AgentIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    d = await _department(s, me, body.department_id)
    a = Agent(org_id=me.org_id, department_id=d.id, name=body.name.strip() or default_agent_name(d.name),
              title=body.title.strip())
    s.add(a)
    await s.flush()
    return {"id": a.id, "name": a.name}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    a = await _agent(s, me, agent_id)
    d = await s.get(Department, a.department_id)
    goal_count = (await s.execute(select(func.count()).select_from(Campaign).where(Campaign.agent_id == a.id))).scalar_one()
    return {
        "id": a.id, "name": a.name, "title": a.title,
        "department": {"id": d.id, "name": d.name},
        "approvers": [_user(u) for u in await approvers(s, me.org_id, d.id)],
        "can_manage": me.in_department(d.id),
        "goals": goal_count,
        "actions": (
            await s.execute(select(func.count()).select_from(Activity).join(Campaign, Campaign.id == Activity.campaign_id)
                            .where(Campaign.agent_id == a.id, Activity.kind == "action", Activity.status == "done"))
        ).scalar_one(),
    }


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentPatch, s: AsyncSession = Depends(get_session),
                       me: Member = Depends(current_member)):
    require_admin(me)
    a = await _agent(s, me, agent_id)
    if body.department_id:
        a.department_id = (await _department(s, me, body.department_id)).id
    if body.name is not None and body.name.strip():
        a.name = body.name.strip()
    if body.title is not None:
        a.title = body.title.strip()
    return {"ok": True}


@router.delete("/agents/{agent_id}")
async def remove_agent(agent_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    a = await _agent(s, me, agent_id)
    if (await s.execute(select(func.count()).select_from(Campaign).where(Campaign.agent_id == a.id))).scalar_one():
        raise HTTPException(400, "This AI employee still has goals. Reassign or delete them first.")
    await s.delete(a)
    return {"ok": True}


# --- people & invitations -----------------------------------------------------------------------

class MemberPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(owner|admin|member)$")
    department_ids: list[str] | None = None


async def _owners(s: AsyncSession, org_id: str) -> int:
    return (await s.execute(select(func.count()).select_from(Membership)
                            .where(Membership.org_id == org_id, Membership.role == Role.owner.value))).scalar_one()


@router.patch("/members/{user_id}")
async def update_member(user_id: str, body: MemberPatch, s: AsyncSession = Depends(get_session),
                        me: Member = Depends(current_member)):
    require_admin(me)
    m = (await s.execute(select(Membership).where(Membership.org_id == me.org_id, Membership.user_id == user_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Person not found")
    if body.role and body.role != m.role:
        if Role.owner.value in (body.role, m.role) and me.role != Role.owner.value:
            raise HTTPException(403, "Only owners can make or remove owners.")
        if m.role == Role.owner.value and await _owners(s, me.org_id) <= 1:
            raise HTTPException(400, "An organization needs at least one owner.")
        m.role = body.role
    if body.department_ids is not None:
        valid = set((await s.execute(select(Department.id).where(Department.org_id == me.org_id,
                                                                 Department.id.in_(body.department_ids or ["-"])))).scalars())
        org_depts = select(Department.id).where(Department.org_id == me.org_id)
        await s.execute(delete(DepartmentMember).where(DepartmentMember.user_id == user_id,
                                                       DepartmentMember.department_id.in_(org_depts)))
        for d in valid:
            s.add(DepartmentMember(department_id=d, user_id=user_id))
    return {"ok": True}


@router.delete("/members/{user_id}")
async def remove_member(user_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    m = (await s.execute(select(Membership).where(Membership.org_id == me.org_id, Membership.user_id == user_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Person not found")
    if m.role == Role.owner.value and (me.role != Role.owner.value or await _owners(s, me.org_id) <= 1):
        raise HTTPException(400, "Owners can only be removed by another owner, and there must always be one.")
    org_depts = select(Department.id).where(Department.org_id == me.org_id)
    await s.execute(delete(DepartmentMember).where(DepartmentMember.user_id == user_id,
                                                   DepartmentMember.department_id.in_(org_depts)))
    await s.delete(m)
    return {"ok": True}


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    role: str = Field(default="member", pattern="^(admin|member)$")
    department_ids: list[str] = Field(default_factory=list)


@router.post("/invitations")
async def invite(body: InviteIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    email = body.email.strip().lower()
    existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing and (await s.execute(select(Membership).where(Membership.user_id == existing.id))).scalar_one_or_none():
        raise HTTPException(409, "This person already belongs to an organization.")
    valid = list((await s.execute(select(Department.id).where(Department.org_id == me.org_id,
                                                              Department.id.in_(body.department_ids or ["-"])))).scalars())
    await s.execute(delete(Invitation).where(Invitation.org_id == me.org_id, Invitation.email == email,
                                             Invitation.accepted_at.is_(None)))
    inv = Invitation(org_id=me.org_id, email=email, role=body.role, department_ids=valid, invited_by=me.user.id)
    s.add(inv)
    await s.flush()
    from app.services.mailer import send_invitation

    org = await s.get(Organization, me.org_id)
    await send_invitation(email, org.name, me.user.name or me.user.email)
    return {"id": inv.id, "email": email}


@router.delete("/invitations/{invitation_id}")
async def cancel_invite(invitation_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    inv = await s.get(Invitation, invitation_id)
    if not inv or inv.org_id != me.org_id:
        raise HTTPException(404, "Invitation not found")
    await s.delete(inv)
    return {"ok": True}
