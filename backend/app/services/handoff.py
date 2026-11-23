"""Hand-offs between AI employees: finished work (e.g. a PRD) becomes another AI employee's goal.

Product Agent -> (the person it reports to approves, if review is on) -> Engineering Agent gets
"Build: <PRD title>" as a new goal, started straight away with a small budget. The engineering
goal proposes code as a pull request; merging waits for an engineer's approval.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Campaign, CampaignStatus, Deliverable, utcnow
from app.services import activity
from app.services.events import notify

HANDOFF_BUDGET_USD = Decimal("10")  # a small, capped budget per handed-off piece of work

KIND_WORDS = {"prd": "PRD", "analysis": "analysis", "report": "report"}


def build_playbook() -> dict:
    return {"source": "handoff", "steps": [
        {"text": "Read the PRD and the code it touches", "action_type": "read_data", "tool": "github"},
        {"text": "Write the change on a new branch and open a pull request", "action_type": "propose_code", "tool": "github"},
        {"text": "Ask an engineer to review and merge it", "action_type": "merge_code", "tool": "github"},
    ]}


async def hand_off(s: AsyncSession, d: Deliverable, from_agent: Agent, to_agent: Agent, who: str) -> Campaign:
    source = await s.get(Campaign, d.campaign_id)
    goal = Campaign(
        org_id=d.org_id, owner_id=source.owner_id if source else None, agent_id=to_agent.id,
        name=f"Build: {d.title}"[:200], goal_type="product",
        goal_description=f"Implement the {KIND_WORDS.get(d.kind, d.kind)} below as a pull request, then ask an engineer to merge it.",
        primary_metric="pull requests merged", target_value=1, done_when="An engineer merged the pull request",
        category="Product & launch", use_case="Build from PRD",
        context=f"{KIND_WORDS.get(d.kind, d.kind)} from {from_agent.name} (approved by {who}):\n\n{d.content}",
        budget_total=HANDOFF_BUDGET_USD, cycle_hours=3, origin="handoff",
        suggested_reason=f"Handed off by {from_agent.name}", first_deliverable="A pull request ready for review",
        key_results=["Pull request opened", "Merged by an engineer"], playbook=build_playbook(),
        budget_basis={"basis": "handoff", "chosen_usd": float(HANDOFF_BUDGET_USD)},
        status=CampaignStatus.active.value, next_cycle_at=utcnow(),
    )
    s.add(goal)
    await s.flush()
    d.status = "handed_off"
    d.handed_to_campaign_id = goal.id
    await activity.log(s, goal.id, "system", f"Handed over by {from_agent.name}: {d.title}", status="info")
    await activity.log(s, d.campaign_id, "decision", f"Handed to {to_agent.name}: {d.title}", status="approved",
                       details={"deliverable_id": d.id, "goal_id": goal.id})
    await notify(s, goal.id, "campaign")
    return goal
