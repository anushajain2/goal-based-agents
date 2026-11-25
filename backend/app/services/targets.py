"""Ongoing goals and their time-boxed targets.

A goal is ongoing, like a person's job ("Get newsletter signups from dispatchers"). What it
aims for right now is a target on its primary metric for a period ("15 signups this week").
When a period ends it is marked hit or missed and the same target carries on into the next
period, unless someone approved a change: the AI employee (or its team's AI lead) proposes
new targets with its reasoning, and a person approves.

Metric values are running totals (what record_metric records), so progress in a period is the
latest value minus the value when the period started.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import Campaign, CampaignStatus, MetricSnapshot, utcnow
from app.services import activity

PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 91}
PERIOD_WORD = {"week": "this week", "month": "this month", "quarter": "this quarter"}
HISTORY = 8  # closed periods kept on the goal


def _iso(d: datetime) -> str:
    return d.isoformat()


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def period_of(value: str | None, default: str = "month") -> str:
    return value if value in PERIOD_DAYS else default


def active(c: Campaign) -> dict | None:
    return next((t for t in reversed(c.targets or []) if t.get("status") == "active"), None)


def planned(c: Campaign) -> dict | None:
    return next((t for t in reversed(c.targets or []) if t.get("status") == "planned"), None)


def current(c: Campaign) -> dict | None:
    """The target people see now: the active one, else the one waiting for the goal to start."""
    return active(c) or planned(c)


def plan_first(c: Campaign, target: float | None, period: str, why: str = "", set_by: str = "setup") -> None:
    """The first target of a goal that hasn't started yet."""
    c.targets = [t for t in c.targets or [] if t.get("status") != "planned"]
    if target:
        c.targets = [*c.targets, {"id": uuid.uuid4().hex[:8], "period": period_of(period), "target": float(target),
                                  "status": "planned", "why": why, "set_by": set_by}]
    c.target_value = float(target) if target else None


async def value_now(s: AsyncSession, c: Campaign) -> float:
    q = select(MetricSnapshot.value).where(MetricSnapshot.campaign_id == c.id)
    if c.primary_metric:
        named = (await s.execute(q.where(MetricSnapshot.metric == c.primary_metric)
                                 .order_by(MetricSnapshot.recorded_at.desc(), MetricSnapshot.id.desc()).limit(1))).scalar_one_or_none()
        if named is not None:
            return float(named)
    latest = (await s.execute(q.order_by(MetricSnapshot.recorded_at.desc(), MetricSnapshot.id.desc()).limit(1))).scalar_one_or_none()
    return float(latest or 0)


def _start(c: Campaign, period: str, target: float, start: datetime, baseline: float, why: str, set_by: str) -> dict:
    t = {"id": uuid.uuid4().hex[:8], "period": period, "target": float(target), "start": _iso(start),
         "end": _iso(start + timedelta(days=PERIOD_DAYS[period])), "baseline": baseline, "status": "active",
         "result": None, "why": why, "set_by": set_by}
    closed = [x for x in c.targets or [] if x.get("status") in ("hit", "missed", "replaced")][-HISTORY:]
    c.targets = [*closed, t]
    flag_modified(c, "targets")  # entries are edited in place too (closing a period)
    c.target_value = float(target)
    return t


async def set_target(s: AsyncSession, c: Campaign, *, target: float, period: str, why: str = "",
                     set_by: str = "person", now: datetime | None = None) -> dict:
    """Change what the goal aims for. A running goal starts a fresh period now (the current one is
    closed as replaced, with its result so far); a goal that hasn't started gets a new first target."""
    period = period_of(period)
    if c.status == CampaignStatus.draft.value or not active(c):
        if c.status == CampaignStatus.draft.value:
            plan_first(c, target, period, why, set_by)
            return planned(c)
    now = now or utcnow()
    value = await value_now(s, c)
    old = active(c)
    if old:
        old["status"] = "replaced"
        old["result"] = value - (old.get("baseline") or 0)
        old["end"] = _iso(now)
    c.targets = list(c.targets or [])  # new list so the JSON column is saved
    return _start(c, period, target, now, value, why, set_by)


async def ensure_started(s: AsyncSession, c: Campaign, now: datetime | None = None) -> dict | None:
    """A running goal has an active target: start the planned one (or, for goals made before
    targets existed, one from target_value)."""
    if c.status != CampaignStatus.active.value or active(c):
        return active(c)
    now = now or utcnow()
    p = planned(c)
    if p:
        c.targets = [t for t in c.targets if t is not p]
        return _start(c, p["period"], p["target"], now, await value_now(s, c), p.get("why", ""), p.get("set_by", "setup"))
    if c.target_value:
        return _start(c, "month", c.target_value, now, await value_now(s, c), "", "person")
    return None


async def roll_over(s: AsyncSession, c: Campaign, now: datetime | None = None) -> dict | None:
    """Close the active period if it has ended (hit or missed) and carry the target into the next
    one. Returns the closed period, if any."""
    now = now or utcnow()
    t = await ensure_started(s, c, now)
    if not t or _dt(t["end"]) > now:
        return None
    value = await value_now(s, c)
    t["result"] = value - (t.get("baseline") or 0)
    t["status"] = "hit" if t["result"] >= t["target"] else "missed"
    end = _dt(t["end"])
    # Pick up where the last period ended (or now, if the goal was paused for a while).
    start = end if now - end < timedelta(days=PERIOD_DAYS[t["period"]]) else now
    c.targets = list(c.targets)
    _start(c, t["period"], t["target"], start, value, "Same target carried over", "auto")
    word = {"week": "Week", "month": "Month", "quarter": "Quarter"}[t["period"]]
    await activity.log(
        s, c.id, "metric",
        f"{word} ended: {fmt(t['result'])} of {fmt(t['target'])} {c.primary_metric}: "
        + ("target hit" if t["status"] == "hit" else "target missed"),
        status="info", details={"period": t},
    )
    return t


def fmt(v: float | None) -> str:
    return "0" if not v else f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def view(c: Campaign, value: float | None = None, now: datetime | None = None) -> dict | None:
    """For the API: what the goal aims for now, how far along it is, and how past periods went."""
    t = current(c)
    history = [{"period": x["period"], "target": x["target"], "result": x.get("result"), "status": x["status"],
                "start": x.get("start"), "end": x.get("end")}
               for x in c.targets or [] if x.get("status") in ("hit", "missed", "replaced")][-6:]
    if not t:
        return {"period": None, "target": None, "progress": None, "history": history} if history else None
    now = now or utcnow()
    progress = None
    days_left = None
    if t["status"] == "active" and value is not None:
        progress = max(value - (t.get("baseline") or 0), 0)
        days_left = max((_dt(t["end"]) - now).total_seconds() / 86400, 0)
    return {"period": t["period"], "target": t["target"], "status": t["status"], "progress": progress,
            "pace": pace(c, value, now) if t["status"] == "active" else None,
            "start": t.get("start"), "end": t.get("end"), "days_left": round(days_left, 1) if days_left is not None else None,
            "why": t.get("why", ""), "set_by": t.get("set_by", ""), "history": history}


def pace(c: Campaign, value: float | None, now: datetime | None = None) -> dict | None:
    """Where the goal should be by now in this period, against where it is: the rate it needs from
    here on, the rate so far, and ahead / on pace / behind."""
    t = active(c)
    if not t or value is None or not t.get("start") or not t.get("end"):
        return None
    now = now or utcnow()
    start, end = _dt(t["start"]), _dt(t["end"])
    total = max((end - start).total_seconds() / 86400, 0.01)
    gone = min(max((now - start).total_seconds() / 86400, 0), total)
    left = max(total - gone, 0)
    progress = max(value - (t.get("baseline") or 0), 0)
    expected = t["target"] * gone / total
    needed = max(t["target"] - progress, 0)
    so_far = progress / gone if gone >= 0.5 else None
    status = "hit" if progress >= t["target"] else "behind" if progress < expected * 0.85 - 0.01 else \
        "ahead" if progress > expected * 1.15 + 0.01 else "on_pace"
    return {"target": t["target"], "progress": progress, "expected_by_now": round(expected, 1),
            "needed": needed, "days_left": round(left, 1),
            "per_day_needed": round(needed / left, 2) if left >= 0.1 else None,
            "per_day_so_far": round(so_far, 2) if so_far is not None else None, "status": status}


def pace_text(c: Campaign, p: dict | None, waiting: int = 0, oldest_hours: float | None = None) -> str:
    """For the brief: the pace in one or two lines, with what to do when behind."""
    if not p:
        return ""
    lines = [f"{fmt(p['progress'])} of {fmt(p['target'])} {c.primary_metric} so far; about {fmt(p['expected_by_now'])} "
             f"expected by now; {p['days_left']:g} days left."]
    if p["status"] == "behind":
        lines.append(f"BEHIND: you need about {p['per_day_needed']:g} a day from here"
                     + (f" (so far {p['per_day_so_far']:g} a day)" if p.get("per_day_so_far") is not None else "")
                     + ". Change something now: work the bottleneck harder, try a stronger approach, work more often "
                       "within the budget, or propose a new target with your reasoning.")
    elif p["status"] in ("ahead", "hit"):
        lines.append("Ahead of pace: keep what works, and consider proposing a higher target.")
    if waiting:
        lines.append(f"{waiting} approval{'s' if waiting != 1 else ''} waiting on people"
                     + (f", the oldest for {oldest_hours:.0f} hours" if oldest_hours else "")
                     + ". If that's what holds the goal back, say so in your update.")
    return "\n".join(lines)


def describe(c: Campaign, value: float, now: datetime | None = None) -> str:
    """For the agent's brief."""
    t = active(c)
    if not t:
        return f"No target set yet for {c.primary_metric}."
    v = view(c, value, now)
    lines = [f"Target {PERIOD_WORD[t['period']]}: {fmt(t['target'])} {c.primary_metric}; "
             f"{fmt(v['progress'])} so far, {v['days_left']:g} days left in the period."]
    if t.get("why") and t.get("set_by") not in ("auto",):
        lines.append(f"Why this target: {t['why']}")
    for h in v["history"][-4:]:
        lines.append(f"- Earlier {h['period']}: {fmt(h['result'])} of {fmt(h['target'])} ({h['status']})")
    return "\n".join(lines)


def change_title(c: Campaign, change: dict) -> str:
    """One line for a proposed change, e.g. 'Raise the target to 30 signups a week'."""
    kind = change.get("type")
    if kind == "target":
        t = current(c)
        per = {"week": "a week", "month": "a month", "quarter": "a quarter"}[period_of(change.get("period"))]
        new = f"{fmt(change['target'])} {c.primary_metric} {per}"
        if t and t["period"] == change.get("period"):
            verb = "Raise" if change["target"] > t["target"] else "Lower" if change["target"] < t["target"] else "Keep"
            return f"{verb} the target to {new}"
        return f"Change the target to {new}"
    if kind == "pause":
        return f"Pause \"{c.name}\""
    if kind == "resume":
        return f"Restart \"{c.name}\""
    if kind == "new_goal":
        return f"Start a new goal: {c.name}"
    if kind == "new_agent":
        return f"Hire {(change.get('agent') or {}).get('name') or 'a new AI employee'} to {c.name[:1].lower() + c.name[1:]}"
    return "Change this goal"
