"""Run the renderer (video/render.mjs) on a job folder: storyboard.json in, launch.mp4 and poster.jpg out."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


class RenderError(RuntimeError):
    pass


@dataclass
class Rendered:
    video: Path
    poster: Path
    seconds: float


def available() -> bool:
    """Whether this machine can render videos (Node and the renderer's packages are installed)."""
    d = get_settings().video_dir
    return bool(shutil.which("node")) and (d / "render.mjs").exists() and (d / "node_modules" / "remotion").exists()


def enabled() -> bool:
    """Whether goals are offered the video tool (some worker can make videos)."""
    on = get_settings().videos
    return available() if on is None else on


async def render(job: Path, storyboard: dict) -> Rendered:
    settings = get_settings()
    (job / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False))
    env = {**os.environ, "RENDER_CONCURRENCY": str(settings.video_render_concurrency)}
    if settings.video_chrome_path:
        env["CHROME_PATH"] = settings.video_chrome_path
    proc = await asyncio.create_subprocess_exec(
        "node", str(settings.video_dir / "render.mjs"), str(job), cwd=str(settings.video_dir), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.video_timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RenderError(f"Rendering took longer than {settings.video_timeout_seconds // 60} minutes") from None
    except asyncio.CancelledError:  # the worker is shutting down: don't leave Chrome rendering behind
        proc.kill()
        raise
    if proc.returncode != 0:
        tail = out.decode(errors="replace").strip().splitlines()[-12:]
        raise RenderError("The renderer failed: " + " | ".join(tail)[-1500:])
    result = json.loads((job / "result.json").read_text())
    return Rendered(video=job / "launch.mp4", poster=job / "poster.jpg", seconds=float(result.get("seconds") or 0))
