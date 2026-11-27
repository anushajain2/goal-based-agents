"""Organization, departments, AI employees, people and invitations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.org_setup import build_starter_team, initial_steps
from app.auth import EMAIL_PATTERN, current_user
from app.config import get_settings
from app.db import get_session
from app.models import (
    Activity,
    Agent,
    AgentRun,
    Campaign,
    Department,
    DepartmentMember,
    Invitation,
    LeadReview,
    LedgerEntry,
    Membership,
    Organization,
    OrgSetup,
    Role,
    User,
    UserRequest,
)
from app.org import (
    DEPARTMENT_PRESETS,
    Member,
    set_head,
    add_department,
    approvers,
    create_organization,
    current_member,
    default_agent_name,
    load_member,
    require_admin,
)

from app.agent.team_lead import lead_name, review_json, spent_this_month
from app.services.website import UnsafeURL, normalize_url

router = APIRouter(prefix="/api", tags=["organization"])


def _user(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email}


# --- setup -------------------------------------------------------------------------------------

@router.get("/org/presets")
async def presets():
    return {"departments": [{"kind": k, "name": n} for k, n in DEPARTMENT_PRESETS]}


BASIC_TEAM = ["sales", "marketing", "research"]


class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=3000)
    # Pick departments by hand. Leave empty to have setup research work them out.
    departments: list[str] = Field(default_factory=list, max_length=30)


def _website(raw: str) -> str:
    try:
        return normalize_url(raw)
    except UnsafeURL as e:
        raise HTTPException(400, str(e)) from e


def _can_research() -> bool:
    return bool(get_settings().anthropic_api_key)


@router.post("/org")
async def create_org(body: OrgIn, s: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    if await load_member(s, user):
        raise HTTPException(409, "You already belong to an organization.")
    website = _website(body.website)
    if body.departments:
        org = await create_organization(s, user, body.name, body.departments, website, body.description)
        return {"id": org.id, "name": org.name, "setup_id": None}
    if not website and not body.description.strip():
        raise HTTPException(400, "Add your website or a sentence about what you do, so we can set up your team.")
    if not _can_research():
        # Without a Claude key there's no research: start with the usual team for this type of company.
        org = await create_organization(s, user, body.name, [], website, body.description)
        await s.commit()  # the starter team is built in its own transaction
        built = await build_starter_team(org.id, user.id)
        return {"id": org.id, "name": org.name, "setup_id": None, "setup_skipped": "no_api_key",
                "company_type": built["company_type"]}
    org = await create_organization(s, user, body.name, [], website, body.description)
    setup = OrgSetup(org_id=org.id, requested_by=user.id, steps=initial_steps())
    s.add(setup)
    await s.flush()
    return {"id": org.id, "name": org.name, "setup_id": setup.id}


# --- setup research: status, re-run, basic fallback -------------------------------------------

def _setup_json(x: OrgSetup | None) -> dict | None:
    if x is None:
        return None
    from app.agent.org_setup import mode_of

    return {
        "id": x.id, "mode": mode_of(x.plan), "status": x.status, "steps": x.steps or [], "error": x.error,
        "cost_usd": float(x.cost_usd or 0), "plan": x.plan, "created": x.created,
        "created_at": x.created_at.isoformat(), "updated_at": x.updated_at.isoformat(),
    }


@router.get("/org/setup")
async def get_setup(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    from app.agent.org_setup import mode_of

    org = await s.get(Organization, me.org_id)
    recent = (await s.execute(select(OrgSetup).where(OrgSetup.org_id == me.org_id)
                              .order_by(OrgSetup.created_at.desc()).limit(20))).scalars().all()
    # "setup" is the company research (onboarding, or "Check again"); "task" is the latest
    # "Suggest more goals" / "Find more opportunities" / add-a-function run.
    latest = next((x for x in recent if mode_of(x.plan) == "start"), None)
    task = next((x for x in recent if mode_of(x.plan) != "start"), None)
    n_departments = (await s.execute(select(func.count()).select_from(Department)
                                     .where(Department.org_id == me.org_id))).scalar_one()
    return {
        "org": {"id": org.id, "name": org.name, "website": org.website, "description": org.description,
                "profile": org.profile},
        "setup": _setup_json(latest),
        "task": _setup_json(task),
        "can_research": _can_research(),
        "can_run": me.is_admin,
        "has_team": n_departments > 0,
    }


class SetupIn(BaseModel):
    website: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=3000)
    # Add these functions now (department kinds or names), reusing earlier research.
    add_functions: list[str] | None = Field(default=None, max_length=6)
    # start: research the company and find what it's missing out on; goals: suggest more goals per
    # function; more: find more opportunities (skipping what was found before).
    mode: str = Field(default="start", pattern="^(start|goals|more)$")


@router.post("/org/setup")
async def rerun_setup(body: SetupIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Research the company again and add what's missing (existing departments and goals stay)."""
    require_admin(me)
    if not _can_research():
        raise HTTPException(400, "Add ANTHROPIC_API_KEY to the .env file and restart to research your company.")
    busy = (await s.execute(select(OrgSetup.id).where(OrgSetup.org_id == me.org_id,
                                                      OrgSetup.status.in_(["queued", "running"])))).first()
    if busy:
        raise HTTPException(409, "Setup is already running.")
    org = await s.get(Organization, me.org_id)
    if body.website is not None:
        org.website = _website(body.website)
    if body.description is not None:
        org.description = body.description.strip()
    if not org.website and not org.description:
        raise HTTPException(400, "Add your website or a sentence about what you do first.")
    include = [f.strip()[:120] for f in body.add_functions or [] if f.strip()]
    if body.add_functions is not None and not include:
        raise HTTPException(400, "Pick a function to add.")
    mode = "include" if include else body.mode
    setup = OrgSetup(org_id=org.id, requested_by=me.user.id, steps=initial_steps(mode),
                     plan={"mode": mode, **({"include": include} if include else {})})
    s.add(setup)
    await s.flush()
    return _setup_json(setup)


@router.post("/org/opportunities/{finding}/milestones/{step}/goal")
async def milestone_goal(finding: int, step: int, s: AsyncSession = Depends(get_session),
                         me: Member = Depends(current_member)):
    """Turn a later milestone of a finding into a draft goal, ready to start."""
    require_admin(me)
    from app.agent import opportunities

    goal_id = await opportunities.milestone_goal(s, me.org_id, me.user.id, finding, step)
    await s.commit()
    if not goal_id:
        raise HTTPException(404, "That step can't be set up: its team may not exist yet.")
    return {"goal_id": goal_id}


@router.post("/org/unlock/{check_key}")
async def unlock(check_key: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """"Connect to unlock": a goal for the team that runs this check on the company's own data."""
    require_admin(me)
    from app.agent import opportunities

    goal_id = await opportunities.unlock_goal(s, me.org_id, me.user.id, check_key)
    if not goal_id:
        raise HTTPException(404, "Add that team first, then Oton can run this check for it.")
    await s.commit()
    return {"goal_id": goal_id}


@router.post("/org/setup/starter-budgets")
async def use_starter_budgets(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Suggested goals made before one-week starter budgets existed: switch the ones not started yet."""
    require_admin(me)
    from decimal import Decimal

    from app.services import estimate

    per, kind, n = await estimate.session_cost(s, me.org_id)
    changed, before, after = 0, 0.0, 0.0
    for c in (await s.execute(select(Campaign).where(Campaign.org_id == me.org_id, Campaign.origin == "setup",
                                                     Campaign.status == "draft"))).scalars():
        old = c.budget_basis or {}
        if old.get("starter") or old.get("milestone"):  # a milestone keeps the price people were shown
            continue
        basis = estimate.starter(per, c.cycle_hours, old.get("days") or estimate.DEFAULT_DAYS,
                                 old.get("paid_spend_usd") or 0, kind, n)
        before += float(c.budget_total)
        c.budget_total = Decimal(str(basis["suggested_usd"]))
        c.budget_basis = {**basis, "chosen_usd": basis["suggested_usd"]}
        after += basis["suggested_usd"]
        changed += 1
    return {"changed": changed, "before_usd": before, "after_usd": after}


@router.post("/org/setup/basic")
async def basic_team(s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Research failed or was skipped: start with the usual team for this type of company instead."""
    require_admin(me)
    n = (await s.execute(select(func.count()).select_from(Department).where(Department.org_id == me.org_id))).scalar_one()
    if n == 0:
        org_id, user_id = me.org_id, me.user.id
        await s.commit()
        built = await build_starter_team(org_id, user_id)
        return {"ok": True, "company_type": built["company_type"]}
    return {"ok": True}


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
    # How often people approve its work exactly as written (work it prepared, not questions).
    decided: dict[str, list[int]] = {}
    for agent_id, status, edited in (
        await s.execute(
            select(Campaign.agent_id, UserRequest.status, UserRequest.edited_fields)
            .join(UserRequest, UserRequest.campaign_id == Campaign.id)
            .where(Campaign.org_id == org_id, UserRequest.kind == "action",
                   UserRequest.status.in_(["approved", "rejected"]))
        )
    ).all():
        d = decided.setdefault(agent_id, [0, 0])
        d[0] += 1
        d[1] += 1 if status == "approved" and not edited else 0
    for agent_id, (n, as_is) in decided.items():
        stats.setdefault(agent_id, {"goals": 0, "active_goals": 0, "spent": 0.0, "working": False, "needs_you": 0})[
            "approved_as_is"] = {"decided": n, "as_is": as_is, "rate": round(as_is / n, 2)}
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
    last_reviews: dict[str, LeadReview] = {}
    for r in (await s.execute(select(LeadReview).where(LeadReview.org_id == me.org_id)
                              .order_by(LeadReview.created_at))).scalars():
        last_reviews[r.department_id] = r
    lead_cost = {d.id: float(await spent_this_month(s, d.id)) for d in departments}
    empty = {"goals": 0, "active_goals": 0, "spent": 0.0, "working": False, "needs_you": 0}
    invitations = []
    if me.is_admin:
        invitations = [
            {"id": i.id, "email": i.email, "role": i.role, "department_ids": i.department_ids,
             "head_department_ids": i.head_department_ids or [],
             "created_at": i.created_at.isoformat()}
            for i in (await s.execute(select(Invitation).where(Invitation.org_id == me.org_id,
                                                                Invitation.accepted_at.is_(None)))).scalars()
        ]
    return {
        "org": {"id": org.id, "name": org.name, "website": org.website, "description": org.description,
                "profile": org.profile},
        "me": {**_user(me.user), "role": me.role, "department_ids": sorted(me.department_ids), "is_admin": me.is_admin,
               "is_operator": get_settings().is_operator(me.user.email)},
        "departments": [
            {
                "id": d.id, "name": d.name, "kind": d.kind,
                "head": _user(users[d.head_user_id]) if d.head_user_id in users else None,
                "lead": {"name": lead_name(d), "enabled": d.lead_enabled, "review_days": d.lead_review_days,
                         "monthly_cap_usd": float(d.lead_monthly_cap_usd), "spent_this_month_usd": lead_cost[d.id],
                         "last_review_at": d.lead_last_review_at.isoformat() if d.lead_last_review_at else None,
                         "last": review_json(last_reviews[d.id]) if d.id in last_reviews else None},
                "people": [_user(users[u]) for u in by_dept.get(d.id, []) if u in users],
                "agents": [
                    {"id": a.id, "name": a.name, "title": a.title, "objective": a.objective, "role": a.role_key,
                     "reports_to": _user(users[a.reports_to_user_id]) if a.reports_to_user_id in users else None,
                     "handoff_to_agent_id": a.handoff_to_agent_id, "handoff_review": a.handoff_review,
                     **stats.get(a.id, empty)}
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


class LeadPatch(BaseModel):
    enabled: bool | None = None
    review_days: int | None = Field(default=None, ge=1, le=30)
    monthly_cap_usd: float | None = Field(default=None, ge=0, le=500)


def _may_manage_team(me: Member, department_id: str) -> None:
    if not (me.is_admin or me.in_department(department_id)):
        raise HTTPException(403, "Only people on this team (or admins) can do that.")


@router.patch("/departments/{department_id}/lead")
async def update_lead(department_id: str, body: LeadPatch, s: AsyncSession = Depends(get_session),
                      me: Member = Depends(current_member)):
    d = await _department(s, me, department_id)
    _may_manage_team(me, d.id)
    changes = body.model_dump(exclude_unset=True)
    if "enabled" in changes:
        d.lead_enabled = bool(changes["enabled"])
    if changes.get("review_days"):
        d.lead_review_days = changes["review_days"]
    if changes.get("monthly_cap_usd") is not None:
        from decimal import Decimal

        d.lead_monthly_cap_usd = Decimal(str(changes["monthly_cap_usd"]))
    return {"ok": True}


@router.get("/departments/{department_id}/lead/reviews")
async def lead_reviews(department_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    d = await _department(s, me, department_id)
    rows = (await s.execute(select(LeadReview).where(LeadReview.department_id == d.id)
                            .order_by(LeadReview.created_at.desc()).limit(10))).scalars()
    return [review_json(r) for r in rows]


@router.post("/departments/{department_id}/lead/review")
async def review_now(department_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    """Ask the team's Reviewer to review the team now (the worker picks it up within seconds)."""
    d = await _department(s, me, department_id)
    _may_manage_team(me, d.id)
    if not _can_research():
        raise HTTPException(400, "Add ANTHROPIC_API_KEY to the .env file and restart to use Reviewers.")
    busy = (await s.execute(select(LeadReview.id).where(LeadReview.department_id == d.id,
                                                        LeadReview.status.in_(["queued", "running"])))).first()
    if busy:
        raise HTTPException(409, f"The {lead_name(d)} is already reviewing the team.")
    if await spent_this_month(s, d.id) >= d.lead_monthly_cap_usd:
        raise HTTPException(400, f"This month's limit for the {lead_name(d)} (${d.lead_monthly_cap_usd:.2f}) is used up. Raise it to review now.")
    r = LeadReview(org_id=me.org_id, department_id=d.id, requested_by=me.user.id)
    s.add(r)
    await s.flush()
    return review_json(r)


class DepartmentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    head_user_id: str | None = None  # send null to clear


@router.patch("/departments/{department_id}")
async def update_department(department_id: str, body: DepartmentPatch, s: AsyncSession = Depends(get_session),
                            me: Member = Depends(current_member)):
    require_admin(me)
    d = await _department(s, me, department_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name"):
        d.name = changes["name"].strip()
    if "head_user_id" in changes:
        head = changes["head_user_id"]
        if head:
            in_org = (await s.execute(select(Membership.id).where(Membership.org_id == me.org_id,
                                                                  Membership.user_id == head))).first()
            if not in_org:
                raise HTTPException(400, "Pick someone in the organization. Invite them first.")
            await set_head(s, d, head)
        else:
            d.head_user_id = None
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
        raise HTTPException(400, "This department still has goals. Move or delete those first.")
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
    objective: str = Field(default="", max_length=600)
    reports_to_user_id: str | None = None  # empty: the department's head (or the owner)


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    objective: str | None = Field(default=None, max_length=600)
    department_id: str | None = None
    reports_to_user_id: str | None = None  # send null to report to the department's head again
    handoff_to_agent_id: str | None = None  # send null to stop handing work on
    handoff_review: bool | None = None


async def _manager(s: AsyncSession, me: Member, user_id: str | None) -> str | None:
    if not user_id:
        return None
    ok = (await s.execute(select(Membership.id).where(Membership.org_id == me.org_id, Membership.user_id == user_id))).first()
    if not ok:
        raise HTTPException(400, "Requests can only go to someone in the organization.")
    return user_id


def _may_staff(me: Member, department_id: str) -> None:
    """Admins staff any department; people in a department (like its head) can add AI employees to it."""
    if not (me.is_admin or me.in_department(department_id)):
        raise HTTPException(403, "Only admins or people in this department can do that.")


async def _agent(s: AsyncSession, me: Member, agent_id: str) -> Agent:
    a = await s.get(Agent, agent_id)
    if not a or a.org_id != me.org_id:
        raise HTTPException(404, "Not found")
    return a


@router.post("/agents")
async def hire_agent(body: AgentIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    d = await _department(s, me, body.department_id)
    _may_staff(me, d.id)
    a = Agent(org_id=me.org_id, department_id=d.id, name=body.name.strip() or default_agent_name(d.name),
              title=body.title.strip(), objective=body.objective.strip(),
              reports_to_user_id=await _manager(s, me, body.reports_to_user_id))
    s.add(a)
    await s.flush()
    return {"id": a.id, "name": a.name}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    a = await _agent(s, me, agent_id)
    d = await s.get(Department, a.department_id)
    goal_count = (await s.execute(select(func.count()).select_from(Campaign).where(Campaign.agent_id == a.id))).scalar_one()
    return {
        "id": a.id, "name": a.name, "title": a.title, "objective": a.objective,
        "reports_to_user_id": a.reports_to_user_id,
        "handoff_to_agent_id": a.handoff_to_agent_id, "handoff_review": a.handoff_review,
        "department": {"id": d.id, "name": d.name},
        "approvers": [_user(u) for u in await approvers(s, me.org_id, d.id, a.id)],
        "can_manage": me.in_department(d.id),
        "can_edit": me.is_admin or me.in_department(d.id),
        "goals": goal_count,
        "actions": (
            await s.execute(select(func.count()).select_from(Activity).join(Campaign, Campaign.id == Activity.campaign_id)
                            .where(Campaign.agent_id == a.id, Activity.kind == "action", Activity.status == "done"))
        ).scalar_one(),
    }


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentPatch, s: AsyncSession = Depends(get_session),
                       me: Member = Depends(current_member)):
    a = await _agent(s, me, agent_id)
    _may_staff(me, a.department_id)
    changes = body.model_dump(exclude_unset=True)
    if body.department_id:
        _may_staff(me, body.department_id)
        a.department_id = (await _department(s, me, body.department_id)).id
    if body.name is not None and body.name.strip():
        a.name = body.name.strip()
    if body.title is not None:
        a.title = body.title.strip()
    if body.objective is not None:
        a.objective = body.objective.strip()
    if "reports_to_user_id" in changes:
        a.reports_to_user_id = await _manager(s, me, body.reports_to_user_id)
    if "handoff_to_agent_id" in changes:
        target = body.handoff_to_agent_id
        if target:
            t = await _agent(s, me, target)
            if t.id == a.id:
                raise HTTPException(400, "Work can't be handed on to where it came from.")
        a.handoff_to_agent_id = target or None
    if body.handoff_review is not None:
        a.handoff_review = body.handoff_review
    return {"ok": True}


@router.delete("/agents/{agent_id}")
async def remove_agent(agent_id: str, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    a = await _agent(s, me, agent_id)
    if (await s.execute(select(func.count()).select_from(Campaign).where(Campaign.agent_id == a.id))).scalar_one():
        raise HTTPException(400, "This still has goals. Reassign or delete them first.")
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
        await s.flush()
        for d in (await s.execute(select(Department).where(Department.org_id == me.org_id))).scalars():
            if d.head_user_id == user_id and d.id not in valid:
                d.head_user_id = None  # left the team: its AI employees go back to the default
            elif d.id in valid and not d.head_user_id and m.role != Role.owner.value:
                d.head_user_id = user_id  # the first person on a team gets its AI employees' requests
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
    head_of: list[str] = Field(default_factory=list)  # departments they will lead


@router.post("/invitations")
async def invite(body: InviteIn, s: AsyncSession = Depends(get_session), me: Member = Depends(current_member)):
    require_admin(me)
    email = body.email.strip().lower()
    existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing and (await s.execute(select(Membership).where(Membership.user_id == existing.id))).scalar_one_or_none():
        raise HTTPException(409, "This person already belongs to an organization.")
    wanted = list(dict.fromkeys([*body.department_ids, *body.head_of]))
    valid = list((await s.execute(select(Department.id).where(Department.org_id == me.org_id,
                                                              Department.id.in_(wanted or ["-"])))).scalars())
    await s.execute(delete(Invitation).where(Invitation.org_id == me.org_id, Invitation.email == email,
                                             Invitation.accepted_at.is_(None)))
    inv = Invitation(org_id=me.org_id, email=email, role=body.role, department_ids=valid, invited_by=me.user.id,
                     head_department_ids=[d for d in body.head_of if d in valid])
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
