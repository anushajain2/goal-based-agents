"""AI cost by task: what each kind of model call costs, from the model_usage rows (one per call)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import TASKS, task_model
from app.config import get_settings
from app.models import ModelUsage, Organization, utcnow


async def by_task(s: AsyncSession, days: int = 30, org_id: str | None = None) -> dict:
    since = utcnow() - timedelta(days=days)
    where = [ModelUsage.created_at >= since] + ([ModelUsage.org_id == org_id] if org_id else [])
    rows = (await s.execute(
        select(ModelUsage.task, func.count(), func.coalesce(func.sum(ModelUsage.cost_usd), 0),
               func.coalesce(func.sum(ModelUsage.input_tokens), 0), func.coalesce(func.sum(ModelUsage.output_tokens), 0),
               func.coalesce(func.sum(ModelUsage.cache_read_tokens), 0), func.coalesce(func.sum(ModelUsage.web_searches), 0))
        .where(*where).group_by(ModelUsage.task))).all()
    models = dict((await s.execute(
        select(ModelUsage.task, func.max(ModelUsage.model)).where(*where).group_by(ModelUsage.task))).all())
    got = {r[0]: r for r in rows}
    total = sum((Decimal(str(r[2])) for r in rows), Decimal("0"))
    settings = get_settings()
    tasks = []
    for key, (slot, label) in TASKS.items():
        r = got.get(key)
        calls, cost = (int(r[1]), Decimal(str(r[2]))) if r else (0, Decimal("0"))
        model, effort = task_model(settings, key)
        tasks.append({"task": key, "label": label, "slot": slot, "model": model, "effort": effort,
                      "served_by": models.get(key), "calls": calls, "cost_usd": float(round(cost, 4)),
                      "avg_usd": float(round(cost / calls, 5)) if calls else 0.0,
                      "share": float(round(cost / total, 4)) if total else 0.0,
                      "input_tokens": int(r[3]) if r else 0, "output_tokens": int(r[4]) if r else 0,
                      "cache_read_tokens": int(r[5]) if r else 0, "web_searches": int(r[6]) if r else 0})
    tasks.sort(key=lambda t: -t["cost_usd"])
    orgs = []
    if not org_id:
        top = (await s.execute(
            select(ModelUsage.org_id, Organization.name, func.count(), func.sum(ModelUsage.cost_usd))
            .join(Organization, Organization.id == ModelUsage.org_id, isouter=True).where(*where)
            .group_by(ModelUsage.org_id, Organization.name).order_by(func.sum(ModelUsage.cost_usd).desc()).limit(15))).all()
        orgs = [{"org_id": o, "name": n or "(no organization)", "calls": int(c), "cost_usd": float(round(Decimal(str(v or 0)), 4))}
                for o, n, c, v in top]
    return {"days": days, "total_usd": float(round(total, 4)), "calls": sum(t["calls"] for t in tasks),
            "tasks": tasks, "orgs": orgs}
