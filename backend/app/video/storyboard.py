"""Claude writes the launch video's storyboard: data for our fixed templates (video/src), never code.

It looks at the screenshots of the company's site and its copy, and returns the scenes (hook, reveal,
features with the part of a screenshot to zoom into, proof, outro), the palette and tempo, and the
copy to post the video with. Then `finalize()` checks every field: lengths, timing, boxes inside
the screenshots, quotes that really appear on the site, readable colours. Whatever Claude returns,
the renderer only ever gets a valid storyboard.
"""

from __future__ import annotations

import base64
import math
import json
import re
from decimal import Decimal
from pathlib import Path

from app.agent.llm import MeteredClaude
from app.video.capture import Capture

FPS = 30
TRANSITION_FRAMES = 12  # keep in step with video/src/Launch.tsx
MIN_SECONDS, MAX_SECONDS, TARGET_SECONDS = 15.0, 26.0, 21.0
READ_SECONDS_PER_WORD = 0.3

SYSTEM = """You direct short launch videos for software and service companies, made from their own website.
You write the storyboard as data; fixed motion templates render it. Your job is the story, the words, and
which part of which screenshot to show.

The shape (about 20 seconds):
1. hook (2-3 seconds): one or two short lines about the buyer's problem or desire, in the buyer's words.
   Specific and a little sharp. Never the company name, never a question like "Tired of...?".
2. reveal: the name, and a tagline that says plainly what it does (not a slogan).
3. two or three features: each shows ONE real screen from the screenshots and zooms into the part that
   proves the point. The title says what the buyer gets (an outcome), in 2-6 words. Don't repeat the words
   already visible in that part of the screenshot: the screenshot shows the thing, the title says why it
   matters. Optional kicker (1-3 words, like a step label) and one short body line.
4. proof (optional): ONLY a testimonial quoted word for word from the site's quotes given to you, with the
   name/role shown there. If there's no real quote, skip it.
5. outro: a short punchline title, the call to action from the site's own buttons, and the domain.

Laws:
- Specific beats generic. Use the company's real nouns, numbers and claims from its site. No "revolutionize",
  "seamless", "unlock", "supercharge", "all-in-one", "game-changer", "next-level", no exclamation marks.
- Nothing invented: no numbers, customers, awards or features that aren't on the site.
- No personal data: no emails, phone numbers, or people's names except a quote's author as shown on the site.
- Readable: every text needs about 0.3 seconds per word plus a second to land. Fewer words, bigger impact.
- Beats: scenes are measured in beats at the tempo you pick (96-124 bpm). Hook 4-6 beats, reveal 5-7,
  each feature 7-9, proof 7-9, outro 6-8. Total about 20 seconds.
- Focus boxes are fractions (0-1) of the screenshot's width and height: x, y = top-left corner, w, h = size.
  Pick a region that's readable when zoomed (a card, a chart, a table, a form), not a whole page and not a
  single word: w between 0.2 and 0.5. Click (optional) is a point inside the box on a real button or control.
- Only use screenshots that show the product or the offer clearly. Skip screens that are mostly a cookie
  banner, empty space, a footer or a wall of text.
- Palette: confirm the brand's colours from what you see in the screenshots (the hints from the page's CSS can
  be wrong). bg is the video's background (usually the brand's dark or light hero colour), fg the text on it,
  accent the brand's signature colour (buttons, highlights), accent2 a second brand colour or a darker accent,
  muted a quieter text colour. Hex like #1a2b3c.
- Share copy: 1-3 sentences to post with the video on LinkedIn or X. Plain, specific, first person plural,
  with the link at the end. No hashtags unless the company uses them.
"""


def schema() -> dict:
    nullable = lambda t: {"anyOf": [{"type": t}, {"type": "null"}]}  # noqa: E731
    box = {"type": "object", "properties": {k: {"type": "number"} for k in "xywh"},
           "required": list("xywh"), "additionalProperties": False}
    point = {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
             "required": ["x", "y"], "additionalProperties": False}
    scene = {"type": "object", "properties": {
        "type": {"type": "string", "enum": ["hook", "reveal", "feature", "proof", "outro"]},
        "beats": {"type": "integer"},
        "lines": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}],
                  "description": "hook: one or two short lines"},
        "title": nullable("string"),
        "tagline": nullable("string"),
        "kicker": nullable("string"),
        "body": nullable("string"),
        "shot": nullable("integer"),
        "focus": {"anyOf": [box, {"type": "null"}]},
        "click": {"anyOf": [point, {"type": "null"}]},
        "quote": nullable("string"),
        "who": nullable("string"),
        "cta": nullable("string"),
        "url": nullable("string"),
    }, "required": ["type", "beats", "lines", "title", "tagline", "kicker", "body", "shot", "focus", "click",
                    "quote", "who", "cta", "url"], "additionalProperties": False}
    color = {"type": "string", "description": "#rrggbb"}
    return {"type": "json_schema", "schema": {"type": "object", "properties": {
        "bpm": {"type": "integer"},
        "tone": {"type": "string", "enum": ["default", "polished", "bold"]},
        "palette": {"type": "object", "properties": {"bg": color, "fg": color, "accent": color, "accent2": color,
                                                     "muted": color, "dark": {"type": "boolean"}},
                    "required": ["bg", "fg", "accent", "accent2", "muted", "dark"], "additionalProperties": False},
        "scenes": {"type": "array", "items": scene},
        "share_copy": {"type": "string"},
        "title": {"type": "string", "description": "A short name for this video, e.g. 'Oton launch video'"},
    }, "required": ["bpm", "tone", "palette", "scenes", "share_copy", "title"], "additionalProperties": False}}


def _task(cap: Capture, name: str, notes: str) -> str:
    def lst(items: list[str]) -> str:
        return "\n".join(f"- {t}" for t in items) or "- (none found)"
    return f"""Company: {name}
Website: {cap.url}
Page title: {cap.title}
Description: {cap.description}
Headline: {cap.headline}

Headings on the page:
{lst(cap.headings)}

Buttons (calls to action):
{lst(cap.buttons)}

Testimonials quoted on the site (the only quotes you may use):
{lst(cap.quotes)}

Colour hints read from the page's CSS (may be wrong): {json.dumps(cap.colors)}; looks {'dark' if cap.dark else 'light'}.

{f'What the person asking for the video wants: {notes}' if notes else ''}

The screenshots follow, numbered from 0 (the first screen, then further down the page). Write the storyboard."""


async def write(claude: MeteredClaude, cap: Capture, job: Path, *, name: str, fmt: str = "landscape",
                notes: str = "", campaign_id: str | None = None, run_id: str | None = None) -> tuple[dict, dict, Decimal]:
    """Ask Claude for the storyboard; return (storyboard, extras {share_copy, title}, cost)."""
    content: list[dict] = [{"type": "text", "text": _task(cap, name, notes)}]
    for i, shot in enumerate(cap.shots):
        look = job / f"look{i}.jpg"
        path = look if look.exists() else job / shot["src"]
        content.append({"type": "text", "text": f"Screenshot {i}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.b64encode(path.read_bytes()).decode()}})
    result = await claude.create(campaign_id=campaign_id, run_id=run_id, purpose="launch video storyboard", role="planner",
                                 system=SYSTEM, messages=[{"role": "user", "content": content}], max_tokens=8000,
                                 output_format=schema())
    text = "\n".join(b.get("text", "") for b in result.content if b.get("type") == "text").strip()
    try:
        raw = json.loads(text or "{}")
    except ValueError:
        raw = {}
    if not any((x or {}).get("type") == "feature" for x in raw.get("scenes") or []):
        raise RuntimeError("Couldn't write a story for the video from this site (no screens worth showing)")
    sb = finalize(raw, cap, name=name, fmt=fmt)
    share = _clip(raw.get("share_copy") or "", 600) or f"{sb['scenes'][1].get('tagline') or name}. {cap.url}"
    return sb, {"share_copy": share, "title": _clip(raw.get("title") or f"{name} launch video", 120)}, result.cost


# ---------------------------------------------------------------------------------------- checking


def _clip(text, n: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") or text[:n]


def _words(*texts) -> int:
    return sum(len(str(t or "").split()) for t in texts)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _hex(c, default: str) -> str:
    m = _HEX.match(str(c or "").strip())
    return f"#{m.group(1).lower()}" if m else default


def _lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(a: str, b: str, t: float) -> str:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def _toward(color: str, bg: str, need: float) -> str:
    """Move a colour away from the background until it stands out enough (keeps its hue)."""
    target = "#ffffff" if _lum(bg) < 0.4 else "#000000"
    for step in range(11):
        c = _mix(color, target, step / 10)
        if contrast(c, bg) >= need:
            return c
    return target


def palette(raw: dict | None, hints: dict | None) -> tuple[dict, bool]:
    raw, hints = raw or {}, hints or {}
    bg = _hex(raw.get("bg"), _hex(hints.get("bg"), "#0f1115"))
    dark = _lum(bg) < 0.4
    fg = _hex(raw.get("fg"), _hex(hints.get("fg"), "#ffffff" if dark else "#0c111d"))
    if contrast(fg, bg) < 7:
        fg = "#ffffff" if dark else "#0c111d"
    accent = _hex(raw.get("accent"), _hex(hints.get("accent"), "#6d5dfc"))
    if contrast(accent, bg) < 2.6:
        accent = _toward(accent, bg, 2.6)
    accent2 = _hex(raw.get("accent2"), _hex(hints.get("accent2"), accent))
    muted = _hex(raw.get("muted"), _mix(fg, bg, 0.3))
    if contrast(muted, bg) < 4.5:
        muted = _mix(fg, bg, 0.3)
    return {"bg": bg, "fg": fg, "accent": accent, "accent2": accent2, "muted": muted}, dark


def _box(b, default=None) -> dict | None:
    if not isinstance(b, dict):
        return default
    try:
        x, y, w, h = (float(b.get(k)) for k in "xywh")
    except (TypeError, ValueError):
        return default
    w, h = min(max(w, 0.12), 1.0), min(max(h, 0.08), 1.0)
    x, y = min(max(x, 0.0), 1.0 - w), min(max(y, 0.0), 1.0 - h)
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _min_beats(scene: dict, bpm: int) -> int:
    """Enough time to read the scene: 0.3s a word for what's read (headlines, quotes), half that for a
    supporting line that's skimmed, plus half a second to land."""
    read = _words(*(scene.get("lines") or []), scene.get("title"), scene.get("tagline"), scene.get("kicker"),
                  scene.get("quote"), scene.get("cta"))
    skim = _words(scene.get("body"), scene.get("who"))
    secs = (read + skim / 2) * READ_SECONDS_PER_WORD + 0.5
    floor = {"hook": 4, "reveal": 5, "feature": 6, "proof": 6, "outro": 6}[scene["type"]]
    return max(floor, math.ceil(round(secs * bpm / 60, 2)))


def seconds(sb: dict) -> float:
    fpb = 60 / sb["bpm"] * sb["fps"]
    frames = sum(round(s["beats"] * fpb) for s in sb["scenes"]) - TRANSITION_FRAMES * max(0, len(sb["scenes"]) - 1)
    return frames / sb["fps"]


def finalize(raw: dict, cap: Capture, *, name: str, fmt: str = "landscape") -> dict:
    """Turn whatever came back into a storyboard the templates can render well."""
    bpm = int(min(max(int(raw.get("bpm") or 110), 92), 128))
    colors, dark = palette(raw.get("palette"), cap.colors)
    shots = [{"src": s["src"], "width": s["width"], "height": s["height"]} for s in cap.shots]
    quotes = [_norm(q) for q in cap.quotes]
    domain = re.sub(r"^https?://(www\.)?", "", cap.url).split("/")[0]

    scenes: list[dict] = []
    for s in raw.get("scenes") or []:
        t = s.get("type")
        try:
            asked = int(s.get("beats") or 0)
        except (TypeError, ValueError):
            asked = 0
        before = len(scenes)
        if t == "hook":
            lines = [_clip(x, 42) for x in (s.get("lines") or []) if str(x or "").strip()][:2]
            if lines:
                scenes.append({"type": "hook", "lines": lines})
        elif t == "reveal":
            scenes.append({"type": "reveal", "title": _clip(s.get("title") or name, 28) or name,
                           "tagline": _clip(s.get("tagline") or cap.headline, 70)})
        elif t == "feature" and shots:
            title = _clip(s.get("title"), 48)
            if not title:
                continue
            try:
                shot = int(s.get("shot") or 0)
            except (TypeError, ValueError):
                shot = 0
            shot = min(max(shot, 0), len(shots) - 1)
            f = {"type": "feature", "title": title, "shot": shot,
                 "focus": _box(s.get("focus"), {"x": 0.2, "y": 0.2, "w": 0.5, "h": 0.5})}
            if (s.get("kicker") or "").strip():
                f["kicker"] = _clip(s["kicker"], 24)
            if (s.get("body") or "").strip():
                f["body"] = _clip(s["body"], 80)
            click = s.get("click")
            if isinstance(click, dict):
                try:
                    box = f["focus"]
                    cx = min(max(float(click["x"]), box["x"]), box["x"] + box["w"])
                    cy = min(max(float(click["y"]), box["y"]), box["y"] + box["h"])
                    f["click"] = {"x": round(cx, 4), "y": round(cy, 4)}
                except (KeyError, TypeError, ValueError):
                    pass
            scenes.append(f)
        elif t == "proof":
            q = _clip(s.get("quote"), 200)
            # Only words that are really on the site.
            if q and any(_norm(q) in full or full in _norm(q) for full in quotes if len(full) > 20):
                scenes.append({"type": "proof", "quote": q, "who": _clip(s.get("who") or "", 60)})
        elif t == "outro":
            scenes.append({"type": "outro", "title": _clip(s.get("title") or cap.headline or name, 40),
                           "cta": _clip(s.get("cta") or (cap.buttons[0] if cap.buttons else "Try it"), 24),
                           "url": domain})
        if len(scenes) > before:
            scenes[-1]["beats"] = asked
        if len(scenes) >= 8:
            break

    # The fixed shape: at most one hook first, one reveal, up to 3 features, at most one proof, an outro last.
    hooks = [s for s in scenes if s["type"] == "hook"][:1]
    reveal = next((s for s in scenes if s["type"] == "reveal"), None) or {
        "type": "reveal", "title": _clip(name, 28), "tagline": _clip(cap.headline or cap.description, 70)}
    features = [s for s in scenes if s["type"] == "feature"][:3]
    proof = [s for s in scenes if s["type"] == "proof"][:1]
    outro = next((s for s in scenes if s["type"] == "outro"), None) or {
        "type": "outro", "title": _clip(cap.headline or name, 40),
        "cta": _clip(cap.buttons[0] if cap.buttons else "Try it", 24), "url": domain}
    ordered = hooks + [reveal] + features + proof + [outro]

    for s in ordered:
        s["beats"] = min(max(int(s.get("beats") or 0), _min_beats(s, bpm)), 12)

    sb = {"format": fmt if fmt in ("landscape", "vertical", "square") else "landscape", "fps": FPS, "bpm": bpm,
          "tone": raw.get("tone") if raw.get("tone") in ("default", "polished", "bold") else "default",
          "brand": {"name": _clip(name, 40), "url": domain, "colors": colors, "dark": dark},
          "shots": shots, "scenes": ordered}
    if cap.logo:
        sb["brand"]["logo"] = cap.logo
        if cap.logo_aspect:
            sb["brand"]["logoAspect"] = cap.logo_aspect
        if cap.logo_bg and _HEX.match(cap.logo_bg):
            sb["brand"]["logoBg"] = _hex(cap.logo_bg, "#ffffff")
    if cap.font:
        sb["brand"]["font"] = cap.font

    # Length: drop the proof, then the last feature, while too long; stretch features while too short.
    while seconds(sb) > MAX_SECONDS and (proof or len(features) > 1):
        victim = proof.pop() if proof else features.pop()
        sb["scenes"].remove(victim)
    while seconds(sb) < MIN_SECONDS:
        grow = [s for s in sb["scenes"] if s["type"] in ("feature", "reveal", "outro") and s["beats"] < 12]
        if not grow:
            break
        for s in grow:
            s["beats"] += 1
    return sb
