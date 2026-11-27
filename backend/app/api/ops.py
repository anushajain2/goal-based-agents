"""For the people who run this Oton (OPERATOR_EMAILS): AI cost by task across all organizations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.models import User
from app.services import costs

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/costs")
async def cost_by_task(days: int = Query(default=30, ge=1, le=365), user: User = Depends(current_user),
                       s: AsyncSession = Depends(get_session)):
    if not get_settings().is_operator(user.email):
        raise HTTPException(403, "Only the people who run this Oton (OPERATOR_EMAILS) can see this.")
    return await costs.by_task(s, days)
