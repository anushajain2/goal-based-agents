"""Applying an approved change to a goal, proposed by its AI employee or its team's AI lead."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Campaign, CampaignStatus, Department, utcnow
from app.services import targets


async def apply_change(s: AsyncSession, c: Campaign, change: dict, reasoning: str, edited: dict | None) -> str:
    """Returns a few words for the work log about what changed."""
    kind = change.get("type")
    by = change.get("by") or "agent"
    if kind == "target":
        value = change.get("target")
        if edited and str(edited.get("target", "")).strip():
            try:
                value = float(str(edited["target"]).replace(",", ""))
            except ValueError:
                raise ValueError("The target must be a number.") from None
        if not value or value <= 0:
            raise ValueError("The target must be above zero.")
        t = await targets.set_target(s, c, target=value, period=change.get("period") or "week", why=reasoning, set_by=by)
        return f"target is now {targets.fmt(t['target'])} {c.primary_metric} a {t['period']}"
    if kind == "pause":
        if c.status == CampaignStatus.active.value:
            c.status = CampaignStatus.paused.value
        return "goal paused"
    if kind == "new_agent":
        spec = change.get("agent") or {}
        dept = await s.get(Department, change.get("department_id") or "-")
        if not dept or dept.org_id != c.org_id:
            raise ValueError("That team no longer exists.")
        if not c.agent_id:
            agent = Agent(org_id=c.org_id, department_id=dept.id, name=(spec.get("name") or "New Agent")[:120],
                          title=(spec.get("title") or "")[:160], objective=spec.get("objective") or "",
                          role_key=spec.get("role") or "")
            s.add(agent)
            await s.flush()
            c.agent_id = agent.id
        kind = "new_goal"
    if kind in ("resume", "new_goal"):
        if c.status in (CampaignStatus.draft.value, CampaignStatus.paused.value):
            c.status = CampaignStatus.active.value
            c.next_cycle_at = c.next_cycle_at or utcnow()
            await targets.ensure_started(s, c)
        return "goal started" if kind == "new_goal" else "goal restarted"
    raise ValueError(f"Unknown change {kind!r}")
