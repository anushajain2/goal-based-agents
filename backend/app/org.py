"""Organizations, departments, people and AI employees: who belongs where, and who may do what.

* Owner/admin: manage the organization, departments, people and AI employees; approve anything.
* Member: sees the whole organization's work; approves requests and manages goals for the
  departments they belong to.

Approval requests are routed to the department of the AI employee doing the work. If that
department has no people in it yet, they go to the organization's admins.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import (
    Agent,
    Campaign,
    Department,
    DepartmentMember,
    ExclusionRule,
    Invitation,
    Membership,
    Organization,
    PermissionGrant,
    Role,
    User,
    utcnow,
)

# Departments people can pick when setting up, keyed by the use-case library category they cover.
DEPARTMENT_PRESETS: list[tuple[str, str]] = [
    ("sales", "Sales"),
    ("marketing", "Marketing"),
    ("research", "Customer Research"),
    ("product", "Product"),
    ("engineering", "Engineering"),
    ("fundraising", "Fundraising"),
    ("hiring", "People & Hiring"),
    ("partnerships", "Partnerships"),
    ("success", "Customer Success"),
    ("finance", "Finance"),
    ("operations", "Operations"),
    ("it", "IT & Security"),
    ("legal", "Legal & Compliance"),
    ("pr", "Brand & PR"),
    ("support", "Customer Support"),
    ("revops", "Revenue Operations"),
    ("data", "Data & Analytics"),
    ("community", "Community"),
    ("exec", "Founder's Office"),
    ("delivery", "Client Delivery"),
    ("store", "Store & Merchandising"),
]
PRESET_NAMES = dict(DEPARTMENT_PRESETS)

# Library categories (as stored on goals) -> their key in the use-case library.
CATEGORY_KEYS = {
    "Sales": "sales", "Marketing & demand gen": "marketing", "Customer research": "research",
    "Product & launch": "product", "Fundraising & investors": "fundraising", "Hiring & talent": "hiring",
    "Partnerships & BD": "partnerships", "Customer success & retention": "success", "Finance": "finance",
    "Operations & procurement": "operations", "Brand, PR & community": "pr",
    "Market & competitive intel": "intel", "For agencies": "agency", "Founder leverage": "founder",
    "Legal & admin": "legal", "IT & security": "it", "Customer support": "support", "Revenue operations": "revops",
    "Data & analytics": "data", "Engineering": "engineering", "E-commerce": "ecommerce",
}

# Library categories (as stored on goals) -> the department kind that handles them.
CATEGORY_TO_KIND = {
    "Sales": "sales", "Marketing & demand gen": "marketing", "Customer research": "research",
    "Product & launch": "product", "Fundraising & investors": "fundraising", "Hiring & talent": "hiring",
    "Partnerships & BD": "partnerships", "Customer success & retention": "success", "Finance": "finance",
    "Operations & procurement": "operations", "Brand, PR & community": "pr",
    "Market & competitive intel": "research", "For agencies": "sales", "Founder leverage": "exec",
    "Legal & admin": "legal", "IT & security": "it", "Customer support": "support", "Revenue operations": "revops",
    "Data & analytics": "data", "Engineering": "engineering", "E-commerce": "store",
}


def default_agent_name(department_name: str) -> str:
    return f"{department_name} Agent"


@dataclass
class Member:
    """The signed-in person, in the context of their organization."""

    user: User
    org_id: str
    role: str
    department_ids: set[str] = field(default_factory=set)

    @property
    def is_admin(self) -> bool:
        return self.role in (Role.owner.value, Role.admin.value)

    def in_department(self, department_id: str | None) -> bool:
        return self.is_admin or (department_id is not None and department_id in self.department_ids)


# --- creating organizations ------------------------------------------------------------------

async def add_department(s: AsyncSession, org_id: str, name: str, kind: str = "", *, with_agent: bool = True,
                         members: list[str] | None = None) -> Department:
    dept = Department(org_id=org_id, name=name.strip()[:120], kind=kind)
    s.add(dept)
    await s.flush()
    if with_agent:
        s.add(Agent(org_id=org_id, department_id=dept.id, name=default_agent_name(dept.name)))
    for user_id in members or []:
        s.add(DepartmentMember(department_id=dept.id, user_id=user_id))
    await s.flush()
    return dept


async def create_organization(s: AsyncSession, user: User, name: str, departments: list[str],
                              website: str = "", description: str = "") -> Organization:
    """`departments` are preset kinds ("sales") or custom names. It may be empty when setup
    research will create the departments (see agent/org_setup.py)."""
    org = Organization(name=name.strip()[:200] or "My company", website=website, description=description.strip())
    s.add(org)
    await s.flush()
    s.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner.value))
    seen: set[str] = set()
    for item in departments:
        label = PRESET_NAMES.get(item, item).strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        await add_department(s, org.id, label, item if item in PRESET_NAMES else "", members=[user.id])
    await s.flush()
    return org


async def _adopt_legacy_data(s: AsyncSession, user: User) -> Organization | None:
    """Goals created before organizations existed move into a new organization owned by their user,
    with a department and AI employee for each kind of goal."""
    goals = (await s.execute(select(Campaign).where(Campaign.owner_id == user.id, Campaign.org_id.is_(None)))).scalars().all()
    has_rules = (
        await s.execute(select(func.count()).select_from(ExclusionRule).where(ExclusionRule.owner_id == user.id))
    ).scalar_one()
    if not goals and not has_rules:
        return None
    label = (user.name or user.email.split("@")[0]).strip()
    org = Organization(name=f"{label}'s team")
    s.add(org)
    await s.flush()
    s.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner.value))
    agents: dict[str, Agent] = {}
    for goal in goals:
        kind = CATEGORY_TO_KIND.get(goal.category, "")
        key = kind or "general"
        if key not in agents:
            dept = await add_department(s, org.id, PRESET_NAMES.get(kind, "General"), kind, with_agent=False,
                                        members=[user.id])
            agent = Agent(org_id=org.id, department_id=dept.id, name=default_agent_name(dept.name))
            s.add(agent)
            await s.flush()
            agents[key] = agent
        goal.org_id = org.id
        goal.agent_id = agents[key].id
    if not agents:
        await add_department(s, org.id, "General", members=[user.id])
    for model in (ExclusionRule, PermissionGrant):
        await s.execute(update(model).where(model.owner_id == user.id, model.org_id.is_(None)).values(org_id=org.id))
    await s.flush()
    return org


async def _accept_invitation(s: AsyncSession, user: User) -> Membership | None:
    inv = (
        await s.execute(
            select(Invitation).where(Invitation.email == user.email, Invitation.accepted_at.is_(None))
            .order_by(Invitation.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not inv:
        return None
    membership = Membership(org_id=inv.org_id, user_id=user.id, role=inv.role)
    s.add(membership)
    valid = set(
        (await s.execute(select(Department.id).where(Department.org_id == inv.org_id,
                                                     Department.id.in_(inv.department_ids or ["-"])))).scalars()
    )
    for dept_id in valid:
        s.add(DepartmentMember(department_id=dept_id, user_id=user.id))
    await s.flush()
    # Their teams' AI employees report to them if the invite said so, or if nobody else on the
    # team has that job yet (the first person on a team gets its requests; changeable any time).
    for dept_id in valid:
        dept = await s.get(Department, dept_id)
        if not dept.head_user_id or dept_id in (inv.head_department_ids or []):
            await set_head(s, dept, user.id)
    inv.accepted_at = utcnow()
    await s.flush()
    return membership


async def set_head(s: AsyncSession, dept: Department, user_id: str) -> None:
    """Make someone the department's head; heads are in the department, so they approve its work."""
    dept.head_user_id = user_id
    exists = (await s.execute(select(DepartmentMember.id).where(DepartmentMember.department_id == dept.id,
                                                                DepartmentMember.user_id == user_id))).first()
    if not exists:
        s.add(DepartmentMember(department_id=dept.id, user_id=user_id))
        await s.flush()


# --- the request context ---------------------------------------------------------------------

async def load_member(s: AsyncSession, user: User) -> Member | None:
    membership = (await s.execute(select(Membership).where(Membership.user_id == user.id))).scalar_one_or_none()
    if membership is None:
        membership = await _accept_invitation(s, user)
    if membership is None and await _adopt_legacy_data(s, user):
        membership = (await s.execute(select(Membership).where(Membership.user_id == user.id))).scalar_one()
    if membership is None:
        return None
    dept_ids = set(
        (
            await s.execute(
                select(DepartmentMember.department_id)
                .join(Department, Department.id == DepartmentMember.department_id)
                .where(DepartmentMember.user_id == user.id, Department.org_id == membership.org_id)
            )
        ).scalars()
    )
    return Member(user=user, org_id=membership.org_id, role=membership.role, department_ids=dept_ids)


async def current_member(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> Member:
    """FastAPI dependency: the signed-in person and their organization. 409 if they have none yet
    (the app then shows the "set up your organization" screen)."""
    member = await load_member(s, user)
    if member is None:
        raise HTTPException(409, "no_organization")
    return member


def require_admin(member: Member) -> None:
    if not member.is_admin:
        raise HTTPException(403, "Only admins can do this.")


# --- goals, routing and approvers ------------------------------------------------------------

async def goal_department(s: AsyncSession, campaign: Campaign) -> str | None:
    if not campaign.agent_id:
        return None
    return (await s.execute(select(Agent.department_id).where(Agent.id == campaign.agent_id))).scalar_one_or_none()


async def get_goal(s: AsyncSession, member: Member, campaign_id: str, *, manage: bool = False) -> Campaign:
    """A goal in the member's organization (404 otherwise). With manage=True, also requires being
    an admin or in the department of the AI employee working on it."""
    c = await s.get(Campaign, campaign_id)
    if not c or c.org_id != member.org_id:
        raise HTTPException(404, "Goal not found")
    if manage and not member.in_department(await goal_department(s, c)):
        raise HTTPException(403, "Only people in this goal's department (or admins) can change it.")
    return c


# --- who approves what: the org chart ------------------------------------------------------------
#
# An AI employee's requests go to one person, never to a whole team at random: someone chosen
# for it, else the person its team's AI employees report to (head_user_id: by default the first
# person added to the team), else the organization's owners. Admins can also decide anything;
# everyone else in the organization can see requests but not decide them.

async def _owners(s: AsyncSession, org_id: str) -> list[User]:
    rows = (await s.execute(select(User, Membership.role).join(Membership, Membership.user_id == User.id)
                            .where(Membership.org_id == org_id, Membership.role.in_([Role.owner.value, Role.admin.value]))
                            .order_by(Membership.created_at))).all()
    owners = [u for u, role in rows if role == Role.owner.value]
    return owners or [u for u, _ in rows]


async def _in_org(s: AsyncSession, org_id: str, user_id: str | None) -> User | None:
    if not user_id:
        return None
    row = (await s.execute(select(User).join(Membership, Membership.user_id == User.id)
                           .where(Membership.org_id == org_id, User.id == user_id))).scalar_one_or_none()
    return row


async def approvers(s: AsyncSession, org_id: str, department_id: str | None = None,
                    agent_id: str | None = None) -> list[User]:
    """Who an AI employee's requests go to (see above). Without an AI employee: the department's
    head, else the owners."""
    agent = await s.get(Agent, agent_id) if agent_id else None
    if agent:
        manager = await _in_org(s, org_id, agent.reports_to_user_id)
        if manager:
            return [manager]
        department_id = agent.department_id
    if department_id:
        dept = await s.get(Department, department_id)
        head = await _in_org(s, org_id, dept.head_user_id if dept else None)
        if head:
            return [head]
    return await _owners(s, org_id)


async def managed_agents(s: AsyncSession, member: Member) -> set[str | None]:
    """The AI employees whose requests come to this person (None = goals with no AI employee)."""
    members = {u for (u,) in (await s.execute(select(Membership.user_id).where(Membership.org_id == member.org_id))).all()}
    heads = {d.id: d.head_user_id for d in (await s.execute(select(Department).where(Department.org_id == member.org_id))).scalars()}
    owners = {u.id for u in await _owners(s, member.org_id)}
    mine: set[str | None] = {None} if member.user.id in owners else set()
    for a in (await s.execute(select(Agent).where(Agent.org_id == member.org_id))).scalars():
        if a.reports_to_user_id in members:
            boss = {a.reports_to_user_id}
        elif heads.get(a.department_id) in members:
            boss = {heads[a.department_id]}
        else:
            boss = owners
        if member.user.id in boss:
            mine.add(a.id)
    return mine


async def routed_to_me(s: AsyncSession, member: Member):
    """SQL filter: the requests this person should act on."""
    from app.models import UserRequest

    agents = await managed_agents(s, member)
    ids = [a for a in agents if a]
    staffed = UserRequest.campaign_id.in_(select(Campaign.id).where(Campaign.org_id == member.org_id,
                                                                    Campaign.agent_id.in_(ids or ["-"])))
    # Goals without an AI employee (old goals, or a team lead's suggested hire) go by their team:
    # to the person the team's AI employees ask, else the owners.
    members = {u for (u,) in (await s.execute(select(Membership.user_id).where(Membership.org_id == member.org_id))).all()}
    owner = None in agents
    teams = [d.id for d in (await s.execute(select(Department).where(Department.org_id == member.org_id))).scalars()
             if (d.head_user_id == member.user.id if d.head_user_id in members else owner)]
    unstaffed = UserRequest.campaign_id.in_(select(Campaign.id).where(Campaign.org_id == member.org_id,
                                                                      Campaign.agent_id.is_(None)))
    by_team = UserRequest.department_id.in_(teams or ["-"])
    if owner:
        by_team = or_(by_team, UserRequest.department_id.is_(None))
    return or_(staffed, and_(unstaffed, by_team))


async def can_decide(s: AsyncSession, member: Member, campaign_id: str, department_id: str | None = None) -> bool:
    if member.is_admin:
        return True
    c = await s.get(Campaign, campaign_id)
    if not c or c.org_id != member.org_id:
        return False
    # A goal waiting for a new AI employee (suggested by a team lead) goes by its team.
    return member.user.id in {u.id for u in await approvers(s, c.org_id, department_id, agent_id=c.agent_id)}


async def pick_agent(s: AsyncSession, org_id: str, category: str) -> Agent | None:
    """Suggest the AI employee for a new goal: one in the department that covers its category."""
    kind = CATEGORY_TO_KIND.get(category, "")
    q = select(Agent).join(Department, Department.id == Agent.department_id).where(Agent.org_id == org_id)
    if kind:
        agent = (await s.execute(q.where(Department.kind == kind).order_by(Agent.created_at).limit(1))).scalar_one_or_none()
        if agent:
            return agent
    return (await s.execute(q.order_by(Agent.created_at).limit(1))).scalar_one_or_none()
