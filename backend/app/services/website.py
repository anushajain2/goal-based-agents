"""Read a company's website as plain text: the home page plus a few telling pages
(about, pricing, customers, careers...).

Fetching a URL someone typed in is a classic way to make a server reach places it shouldn't
(its own admin ports, cloud metadata, the office network). So every hop, redirects included,
must resolve to a public address, and responses are size-capped.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag, urlparse

import httpx

log = logging.getLogger(__name__)

MAX_BYTES = 1_500_000
PAGE_CHARS = 5_000
TOTAL_CHARS = 24_000
MAX_EXTRA_PAGES = 5
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OtonSetup/1.0; reads the site once to set up Oton)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
}

# Pages that say the most about a company, in the order we'd read them. One page per group.
PAGE_HINTS: list[tuple[str, ...]] = [
    ("about", "company", "who-we-are", "our-story", "mission"),
    ("pricing", "plans"),
    ("product", "features", "solutions", "platform", "how-it-works", "services"),
    ("customers", "case-studies", "case-study", "testimonials", "clients", "work", "portfolio"),
    ("careers", "jobs", "join", "hiring"),
    ("team", "people", "leadership", "founders"),
    ("blog", "news", "press", "changelog", "updates"),
]

SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "canvas"}
BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "li", "ul", "ol", "br", "h1", "h2", "h3",
              "h4", "h5", "h6", "tr", "td", "th", "table", "main", "aside", "nav", "blockquote", "figcaption"}


class UnsafeURL(ValueError):
    pass


@dataclass
class Page:
    url: str
    title: str
    description: str
    text: str


@dataclass
class SiteReading:
    url: str
    pages: list[Page] = field(default_factory=list)
    error: str | None = None

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.removeprefix("www.")

    def as_text(self) -> str:
        parts = []
        for p in self.pages:
            head = f"## {p.url}\n" + (f"Title: {p.title}\n" if p.title else "") + (
                f"Description: {p.description}\n" if p.description else "")
            parts.append(head + p.text)
        return "\n\n".join(parts)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.description = ""
        self._skip = 0
        self._in_title = False
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or a.get("property") or "").lower() in ("description", "og:description"):
            self.description = self.description or (a.get("content") or "").strip()
        elif tag == "a" and a.get("href"):
            self._href, self._link_text = a["href"], []
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._link_text).strip()))
            self._href = None
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        self.parts.append(data)
        if self._href is not None:
            self._link_text.append(data.strip())

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in raw.split("\n")]
        out, last = [], None
        for line in lines:
            if line and line != last:  # drop blank and repeated lines (menus, footers)
                out.append(line)
            last = line
        return "\n".join(out)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc.split(":")[0]:
        raise UnsafeURL("That doesn't look like a website address.")
    return url


async def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Only http and https addresses can be read.")
    host = parsed.hostname or ""
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeURL("That address isn't on the public internet.")
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
            candidates = [i[4][0] for i in infos]
        except socket.gaierror:
            # Can't resolve it here (some networks only resolve through a proxy). The request
            # itself will fail if the name is bogus; nothing private is reachable by name alone.
            return
    for addr in candidates:
        ip = ipaddress.ip_address(addr.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("That address isn't on the public internet.")


async def _get(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """GET a page, following up to 5 redirects with each hop checked. Returns (final_url, html)."""
    for _ in range(6):
        await _assert_public(url)
        async with client.stream("GET", url, headers=HEADERS) as r:
            if r.is_redirect and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code >= 400:
                return None
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return None
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return str(r.url), body.decode(r.encoding or "utf-8", errors="replace")
    return None


def _parse(url: str, html: str) -> tuple[Page, list[tuple[str, str]]]:
    p = _TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception:  # broken markup: keep whatever was parsed
        pass
    page = Page(url=url, title=re.sub(r"\s+", " ", p.title).strip()[:200],
                description=p.description[:400], text=p.text()[:PAGE_CHARS])
    return page, p.links


def _pick_pages(base: str, links: list[tuple[str, str]]) -> list[str]:
    host = urlparse(base).netloc.removeprefix("www.")
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for href, label in links:
        absolute = urldefrag(urljoin(base, href))[0].rstrip("/")
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.netloc.removeprefix("www.") != host:
            continue
        if absolute in seen or absolute.rstrip("/") == base.rstrip("/"):
            continue
        if re.search(r"\.(pdf|png|jpe?g|gif|svg|zip|mp4|webp)$", parsed.path, re.I):
            continue
        seen.add(absolute)
        candidates.append((absolute, f"{parsed.path} {label}".lower()))
    picked: list[str] = []
    for hints in PAGE_HINTS:
        for url, haystack in candidates:
            path = urlparse(url).path.lower()
            if url not in picked and path.count("/") <= 3 and any(h in haystack for h in hints):
                picked.append(url)
                break
        if len(picked) >= MAX_EXTRA_PAGES:
            break
    return picked


async def read_site(url: str) -> SiteReading:
    """Read the home page and up to five telling pages. Never raises: errors land in `.error`."""
    try:
        url = normalize_url(url)
    except UnsafeURL as e:
        return SiteReading(url=url, error=str(e))
    reading = SiteReading(url=url)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            home = await _get(client, url)
            if not home:
                reading.error = "The website didn't return a readable page."
                return reading
            reading.url = home[0]
            page, links = _parse(*home)
            reading.pages.append(page)
            results = await asyncio.gather(*[_get(client, u) for u in _pick_pages(reading.url, links)],
                                           return_exceptions=True)
            total = len(page.text)
            for res in results:
                if isinstance(res, tuple):
                    extra, _ = _parse(*res)
                    if extra.text and total < TOTAL_CHARS:
                        extra.text = extra.text[: TOTAL_CHARS - total]
                        total += len(extra.text)
                        reading.pages.append(extra)
    except UnsafeURL as e:
        reading.error = str(e)
    except httpx.HTTPError as e:
        reading.error = f"Couldn't reach the website ({type(e).__name__})."
    except Exception as e:  # never let a strange site break setup
        log.exception("reading %s failed", url)
        reading.error = f"Couldn't read the website ({type(e).__name__})."
    return reading
