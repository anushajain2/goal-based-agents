"""What an AI employee may do on a goal, per kind of action: on its own, after a heads-up, ask
first, or never.

This reads the same rules the policy engine enforces (services/policy.decide), so what people
see is exactly what happens: built-in defaults, then "never" rules and permissions set on the
goal, its department or the whole organization (the strictest applicable one wins).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExclusionRule, PermissionGrant
from app.services.policy import ACTION_TYPES, applies_to, strictest

LEVEL_ORDER = {"goal": 0, "department": 1, "org": 2}


def _level(row) -> str:
    return "goal" if row.campaign_id else "department" if row.department_id else "org"


async def effective(s: AsyncSession, campaign_id: str, *, with_suggestions: bool = True) -> list[dict]:
    from app.services import autonomy

    rules = (await s.execute(select(ExclusionRule).where(
        ExclusionRule.kind == "action_type", applies_to(ExclusionRule, campaign_id)))).scalars().all()
    grants = (await s.execute(select(PermissionGrant).where(
        PermissionGrant.revoked_at.is_(None), applies_to(PermissionGrant, campaign_id)))).scalars().all()
    out = []
    for t in ACTION_TYPES.values():
        item = {
            "key": t.key, "label": t.label, "description": t.description,
            "default": t.default, "mode": t.default, "set_at": "default", "spend_limit_usd": None,
            "daily_cap": None, "source": None,
            "only_on": [],  # permissions limited to one app or site that go ahead without asking
            "asks_on": [],  # ...and ones that always ask (e.g. a personal profile)
            "suggestion": None,
        }
        mine = [g for g in grants if g.action_type == t.key]
        unscoped = [g for g in mine if not g.scope]
        if t.default == "ask" and unscoped:
            g = strictest(unscoped)
            item.update(mode=g.mode or "auto", set_at=_level(g), daily_cap=g.daily_cap, source=g.source,
                        spend_limit_usd=float(g.spend_limit_usd) if g.spend_limit_usd is not None else None)
        item["only_on"] = sorted({g.scope for g in mine if g.scope and (g.mode or "auto") != "ask"})
        item["asks_on"] = sorted({g.scope for g in mine if g.scope and g.mode == "ask"})
        never = [r for r in rules if r.value == t.key]
        if never:  # a "never" rule always wins, wherever it was set
            r = min(never, key=lambda r: LEVEL_ORDER[_level(r)])
            item.update(mode="never", set_at=_level(r))
        out.append(item)
    if with_suggestions:
        found = await autonomy.suggestions(s, campaign_id, {i["key"]: i["mode"] for i in out})
        for i in out:
            i["suggestion"] = found.get(i["key"])
    return out
