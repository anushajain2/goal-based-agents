"""Launch videos: their progress, and the finished mp4 and poster (for the review player).

Only members of the organization that owns a video can see it. The mp4 is served with byte ranges,
which browsers need to seek in a video and Safari needs to play one at all.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.config import get_settings
from app.db import get_session
from app.models import Deliverable, LaunchVideo
from app.org import Member, current_member

router = APIRouter(prefix="/api/videos", tags=["videos"])


async def _video(s: AsyncSession, me: Member, video_id: str, *load) -> LaunchVideo:
    q = select(LaunchVideo).where(LaunchVideo.id == video_id, LaunchVideo.org_id == me.org_id)
    if load:
        q = q.options(*(undefer(c) for c in load))
    v = (await s.execute(q)).scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Video not found")
    return v


@router.get("/{video_id}")
async def get_video(video_id: str, me: Member = Depends(current_member), s: AsyncSession = Depends(get_session)):
    v = await _video(s, me, video_id)
    return {"id": v.id, "status": v.status, "step": v.step, "error": v.error, "title": v.title, "url": v.url,
            "format": v.format, "seconds": v.seconds, "share_copy": v.share_copy, "campaign_id": v.campaign_id,
            "deliverable_id": v.deliverable_id, "created_at": v.created_at.isoformat(),
            "video_url": f"/api/videos/{v.id}/video.mp4" if v.status == "done" else None,
            "poster_url": f"/api/videos/{v.id}/poster.jpg" if v.status == "done" else None}


_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def share_sig(video_id: str) -> str:
    return hmac.new(get_settings().secret(), f"video:{video_id}".encode(), hashlib.sha256).hexdigest()[:32]


def share_url(video_id: str) -> str:
    """A link that works without signing in, so an app (LinkedIn, X, YouTube...) can fetch the file to post
    it. It only works once the video has been approved."""
    return f"{get_settings().helper_server_url}/api/videos/{video_id}/share/{share_sig(video_id)}.mp4"


@router.get("/{video_id}/video.mp4")
async def video_file(video_id: str, request: Request, download: bool = False, me: Member = Depends(current_member),
                     s: AsyncSession = Depends(get_session)):
    v = await _video(s, me, video_id, LaunchVideo.video)
    return _serve(v, request, download)


@router.get("/{video_id}/share/{sig}.mp4")
async def shared_file(video_id: str, sig: str, request: Request, s: AsyncSession = Depends(get_session)):
    if not hmac.compare_digest(sig, share_sig(video_id)):
        raise HTTPException(404, "Video not found")
    v = (await s.execute(select(LaunchVideo).where(LaunchVideo.id == video_id).options(undefer(LaunchVideo.video))
                         )).scalar_one_or_none()
    d = await s.get(Deliverable, v.deliverable_id) if v and v.deliverable_id else None
    if not v or not d or d.status != "approved":
        raise HTTPException(404, "Video not found")
    return _serve(v, request, False)


def _serve(v: LaunchVideo, request: Request, download: bool) -> Response:
    if not v.video:
        raise HTTPException(404, "Not ready yet")
    data, size = v.video, len(v.video)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if download:
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", v.title or "launch-video").strip("-") or "launch-video"
        headers["Content-Disposition"] = f'attachment; filename="{name}.mp4"'
    m = _RANGE.match(request.headers.get("range", "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        else:  # the last N bytes
            start, end = max(0, size - int(m.group(2))), size - 1
        if start >= size or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(data[start:end + 1], status_code=206, media_type="video/mp4", headers=headers)
    return Response(data, media_type="video/mp4", headers=headers)


@router.get("/{video_id}/poster.jpg")
async def poster_file(video_id: str, me: Member = Depends(current_member), s: AsyncSession = Depends(get_session)):
    v = await _video(s, me, video_id, LaunchVideo.poster)
    if not v.poster:
        raise HTTPException(404, "Not ready yet")
    return Response(v.poster, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
