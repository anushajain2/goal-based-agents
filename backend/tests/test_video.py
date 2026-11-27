"""Launch videos: the storyboard checks, the job from start to review, and serving the file."""

import json

import httpx
from sqlalchemy import select

from app.agent.executor import ToolExecutor
from app.agent.llm import MeteredClaude
from app.agent.tools import all_tools
from app.db import session_scope
from app.main import app
from app.models import AgentRun, LaunchVideo, Organization
from app.video import job as job_mod
from app.video.capture import Capture
from app.video.render import Rendered
from app.video.storyboard import contrast, finalize, palette, seconds
from tests.fakes import FakeAnthropic
from tests.helpers import agent_in, org_of, sign_in_with_org


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


SHOTS = [{"src": f"shot{i}.jpg", "width": 2880, "height": 1800, "y": i * 900} for i in range(4)]
QUOTE = "Routeco cut our planning time from two hours to ten minutes every single morning."


def cap(**kw) -> Capture:
    base = dict(url="https://routeco.example", title="Routeco", headline="Route planning for small fleets",
                headings=["Plan in minutes", "Live tracking"], buttons=["Start free trial"], quotes=[QUOTE],
                colors={"bg": "#f8f8f3", "fg": "#ffffff", "accent": "#151a0e"}, dark=False, shots=list(SHOTS))
    base.update(kw)
    return Capture(**base)


def scene(type_, **kw) -> dict:
    blank = {k: None for k in ("lines", "title", "tagline", "kicker", "body", "shot", "focus", "click", "quote", "who",
                               "cta", "url")}
    return {**blank, "type": type_, "beats": kw.pop("beats", 6), **kw}


GOOD = {
    "bpm": 110, "tone": "default",
    "palette": {"bg": "#0e1a2b", "fg": "#ffffff", "accent": "#36c48f", "accent2": "#1d6b52", "muted": "#a9b4c2", "dark": True},
    "title": "Routeco launch video",
    "share_copy": "We built Routeco so a 10-van fleet plans its day in minutes. https://routeco.example",
    "scenes": [
        scene("hook", lines=["Two hours planning routes", "before a single van leaves."], beats=5),
        scene("reveal", title="Routeco", tagline="Route planning for small fleets", beats=6),
        scene("feature", kicker="Plan", title="A day's routes in one click", shot=1,
              focus={"x": 0.5, "y": 0.2, "w": 0.3, "h": 0.3}, click={"x": 0.6, "y": 0.3}, beats=8),
        scene("feature", kicker="Track", title="Every van, live", shot=7,  # no such screenshot
              focus={"x": 0.9, "y": -0.2, "w": 0.6, "h": 0.01}, click={"x": 5, "y": 5}, beats=8),
        scene("proof", quote="Routeco doubled our revenue overnight", who="Made up", beats=8),  # not on the site
        scene("proof", quote=QUOTE, who="Dana, Ops lead", beats=8),
        scene("outro", title="Plan less. Deliver more.", cta="Start free trial", url="evil.example", beats=7),
    ],
}


def test_storyboard_is_checked_before_it_is_rendered():
    sb = finalize(json.loads(json.dumps(GOOD)), cap(), name="Routeco")
    types = [s["type"] for s in sb["scenes"]]
    assert types[0] == "hook" and types[1] == "reveal" and types[-1] == "outro"
    assert MIN <= seconds(sb) <= MAX
    # Only quotes that are really on the site.
    assert all(s["quote"] == QUOTE for s in sb["scenes"] if s["type"] == "proof")
    # Screenshot indexes and boxes are kept inside what exists.
    feats = [s for s in sb["scenes"] if s["type"] == "feature"]
    assert feats[1]["shot"] == 3
    box = feats[1]["focus"]
    assert 0 <= box["x"] and box["x"] + box["w"] <= 1 and 0 <= box["y"] and box["y"] + box["h"] <= 1 and box["h"] >= 0.08
    click = feats[1]["click"]
    assert box["x"] <= click["x"] <= box["x"] + box["w"] and box["y"] <= click["y"] <= box["y"] + box["h"]
    # The outro points at the company's own site, whatever came back.
    assert sb["scenes"][-1]["url"] == "routeco.example"
    assert sb["brand"]["colors"]["accent"] == "#36c48f" and sb["brand"]["dark"] is True


def test_every_scene_gets_time_to_be_read():
    raw = json.loads(json.dumps(GOOD))
    for s in raw["scenes"]:
        s["beats"] = 1
    sb = finalize(raw, cap(), name="Routeco")
    hook = sb["scenes"][0]
    words = sum(len(x.split()) for x in hook["lines"])
    assert hook["beats"] * 60 / sb["bpm"] >= words * 0.3  # about 0.3s a word
    assert MIN <= seconds(sb)


def test_a_too_long_storyboard_is_cut_down_and_an_empty_one_still_renders():
    raw = json.loads(json.dumps(GOOD))
    for s in raw["scenes"]:
        s["beats"] = 12
    assert seconds(finalize(raw, cap(), name="Routeco")) <= MAX
    sb = finalize({}, cap(), name="Routeco")
    assert [s["type"] for s in sb["scenes"]] == ["reveal", "outro"]  # still a valid storyboard
    assert sb["scenes"][-1]["cta"] == "Start free trial"


def test_palette_is_readable_even_when_the_hints_are_wrong():
    colors, dark = palette({}, {"bg": "#f8f8f3", "fg": "#ffffff", "accent": "#f3f3ee"})
    assert not dark and contrast(colors["fg"], colors["bg"]) >= 7
    assert contrast(colors["accent"], colors["bg"]) >= 2.6 and contrast(colors["muted"], colors["bg"]) >= 4.5
    colors, dark = palette({"bg": "not a colour", "fg": "#0e0e0e"}, {"bg": "#0b0b0b"})
    assert dark and colors["fg"] == "#ffffff"


MIN, MAX = 15.0, 26.0


async def test_a_goal_makes_a_video_and_it_goes_for_review(monkeypatch, tmp_path):
    async def fake_capture(url, job, fmt):
        job.mkdir(parents=True, exist_ok=True)
        for s in SHOTS:
            (job / s["src"]).write_bytes(b"\xff\xd8jpeg")
        return cap(url=url)

    rendered = {}

    async def fake_render(job, sb):
        rendered["sb"] = sb
        (job / "launch.mp4").write_bytes(b"0123456789" * 10)
        (job / "poster.jpg").write_bytes(b"\xff\xd8poster")
        return Rendered(video=job / "launch.mp4", poster=job / "poster.jpg", seconds=21.4)

    monkeypatch.setattr(job_mod.capture_mod, "capture", fake_capture)
    monkeypatch.setattr(job_mod.render_mod, "render", fake_render)
    fake = FakeAnthropic(lambda kw: [], routes={"share_copy": lambda kw: GOOD})

    async with client() as c, client() as stranger:
        await sign_in_with_org(c, "founder@routeco.test", departments=("marketing",))
        org = await org_of(c)
        async with session_scope() as s:
            (await s.get(Organization, org["org"]["id"])).website = "https://routeco.example"
        r = await c.post("/api/campaigns", json={"name": "Launch video", "goal_description": "A launch video",
                                                 "primary_metric": "views", "budget_total": 10,
                                                 "agent_id": agent_in(org, "Marketing"), "launch": True})
        goal = r.json()["id"]
        async with session_scope() as s:
            run = AgentRun(campaign_id=goal, cycle_number=1, status="running")
            s.add(run)
            await s.flush()
            run_id = run.id
        ex = ToolExecutor(MeteredClaude(client=fake), goal, run_id, org["org"]["id"])
        out = await ex.call("make_launch_video", {"format": "landscape", "notes": "For small fleet owners"}, "t1")
        assert "Started" in out.content
        again = await ex.call("make_launch_video", {}, "t2")
        assert "already being made" in again.content

        async with session_scope() as s:
            v = (await s.execute(select(LaunchVideo).where(LaunchVideo.campaign_id == goal))).scalar_one()
            assert v.url == "https://routeco.example" and v.status == "queued"
            video_id = v.id
        await job_mod.run_video(video_id, MeteredClaude(client=fake))

        # Claude saw the screenshots and the site's copy.
        call = next(k for k in fake.calls if "share_copy" in k["output_config"]["format"]["schema"]["properties"])
        blocks = call["messages"][0]["content"]
        assert sum(b["type"] == "image" for b in blocks) == 4 and QUOTE in blocks[0]["text"]
        assert "For small fleet owners" in blocks[0]["text"]
        assert rendered["sb"]["scenes"][0]["type"] == "hook"

        info = (await c.get(f"/api/videos/{video_id}")).json()
        assert info["status"] == "done" and info["seconds"] == 21.4 and info["video_url"]
        assert (await stranger.get(f"/api/videos/{video_id}")).status_code in (401, 409)

        # The review shows the player and the copy to post it with.
        req = next(q for q in (await c.get("/api/requests")).json() if q["kind"] == "review")
        assert req["preview"]["video_id"] == video_id and req["preview"]["fields"]["content"] == GOOD["share_copy"]

        # The file, whole and in ranges (browsers seek with ranges).
        whole = await c.get(f"/api/videos/{video_id}/video.mp4")
        assert whole.status_code == 200 and whole.headers["content-type"] == "video/mp4" and len(whole.content) == 100
        part = await c.get(f"/api/videos/{video_id}/video.mp4", headers={"Range": "bytes=10-19"})
        assert part.status_code == 206 and part.content == b"0123456789"
        assert part.headers["content-range"] == "bytes 10-19/100"
        assert (await c.get(f"/api/videos/{video_id}/video.mp4", headers={"Range": "bytes=500-"})).status_code == 416
        assert (await c.get(f"/api/videos/{video_id}/poster.jpg")).content == b"\xff\xd8poster"

        # The public link (for apps that fetch the file to post it) only works once approved.
        from app.api.videos import share_sig
        share = f"/api/videos/{video_id}/share/{share_sig(video_id)}.mp4"
        assert (await stranger.get(share)).status_code == 404
        assert (await stranger.get(f"/api/videos/{video_id}/share/{'0' * 32}.mp4")).status_code == 404
        edited = "We built Routeco for 10-van fleets. https://routeco.example"
        r = await c.post(f"/api/requests/{req['id']}/decide", json={"decision": "approve", "edited_fields": {"content": edited}})
        assert r.status_code == 200, r.text
        assert (await stranger.get(share)).status_code == 200
        log = (await c.get(f"/api/campaigns/{goal}/activity")).json()
        assert any("Ready to post with the approved copy" in a["title"] and share in a["title"] for a in log)
        async with session_scope() as s:
            assert (await s.get(LaunchVideo, video_id)).share_copy == edited


async def test_a_failed_video_says_why_in_the_work_log(monkeypatch):
    async def broken_capture(url, job, fmt):
        raise RuntimeError("The site didn't load")

    monkeypatch.setattr(job_mod.capture_mod, "capture", broken_capture)
    async with client() as c:
        await sign_in_with_org(c, "founder@fleet.test", departments=("marketing",))
        org = await org_of(c)
        r = await c.post("/api/campaigns", json={"name": "Video", "goal_description": "A video", "primary_metric": "views",
                                                 "budget_total": 10, "agent_id": agent_in(org, "Marketing"), "launch": True})
        goal = r.json()["id"]
        async with session_scope() as s:
            v = LaunchVideo(org_id=org["org"]["id"], campaign_id=goal, url="https://fleet.example")
            s.add(v)
            await s.flush()
            video_id = v.id
        await job_mod.run_video(video_id, MeteredClaude(client=FakeAnthropic(lambda kw: [])))
        info = (await c.get(f"/api/videos/{video_id}")).json()
        assert info["status"] == "failed" and "didn't load" in info["error"]
        log = (await c.get(f"/api/campaigns/{goal}/activity")).json()
        assert any("Couldn't make the launch video" in a["title"] for a in log)


def test_the_video_tool_is_only_offered_where_videos_can_be_rendered():
    names = lambda sets: {t["name"] for t in all_tools(False, False, sets)}  # noqa: E731
    assert "make_launch_video" in names(["video"]) and "make_launch_video" not in names([])
