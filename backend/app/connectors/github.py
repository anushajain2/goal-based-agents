"""A small GitHub client for Engineering AI employees.

They can read code and issues, and propose a change as a pull request on a new branch. They
never push to the default branch: merging is a separate action. A small pull request that only
changes content (copy, articles, images) and passes its checks is "merge_content", which a goal
may allow without asking; anything else is "merge_code", which waits for an engineer.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx

API = "https://api.github.com"
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests point this at a fake GitHub
MAX_FILE_CHARS = 60_000


class GitHubError(Exception):
    pass


CONTENT_EXTENSIONS = (".md", ".mdx", ".markdown", ".txt", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg")
SENSITIVE_PATH = re.compile(r"(pric|checkout|billing|payment|(^|/)o?auth(/|[._-]|$)|login|sign-?in|sign-?up|legal|terms|privacy|security|"
                            r"\.github/|workflow)", re.I)
CONTENT_MAX_LINES = 300
CONTENT_MAX_FILES = 10


def content_only(files: list[dict], checks: str) -> tuple[bool, str]:
    """Is this pull request a small content change that's safe to merge without an engineer?"""
    if checks != "success":
        why = {"none": "no checks ran on it", "pending": "its checks are still running", "failure": "its checks failed"}
        return False, why.get(checks, "its checks didn't pass")
    if not files or len(files) > CONTENT_MAX_FILES:
        return False, f"it changes {len(files)} files"
    lines = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in files)
    if lines > CONTENT_MAX_LINES:
        return False, f"it changes {lines} lines"
    for f in files:
        path = f.get("path") or ""
        if f.get("status") == "removed":
            return False, f"it deletes {path}"
        if not path.lower().endswith(CONTENT_EXTENSIONS):
            return False, f"it changes {path}, which isn't content"
        if SENSITIVE_PATH.search(path):
            return False, f"it touches {path}"
    return True, f"{len(files)} content files, {lines} lines, checks passed"


def safe_branch(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._/-]+", "-", name.strip().lower()).strip("-/.")
    return ("oton/" + name)[:80] if not name.startswith("oton/") else name[:80]


class GitHub:
    def __init__(self, token: str, repo: str):
        self.repo = repo.strip().strip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "oton"}

    async def _call(self, method: str, path: str, **kw) -> Any:
        async with httpx.AsyncClient(timeout=30, transport=TRANSPORT) as client:
            try:
                r = await client.request(method, API + path, headers=self.headers, **kw)
            except httpx.HTTPError as e:
                raise GitHubError(f"Couldn't reach GitHub ({type(e).__name__}).") from e
        if r.status_code in (401, 403):
            raise GitHubError("GitHub refused the token: check it can read and write this repository.")
        if r.status_code == 404:
            raise GitHubError(f"Not found on GitHub: {path.split('?')[0]}")
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", "")
            except ValueError:
                msg = r.text[:200]
            raise GitHubError(f"GitHub error {r.status_code}: {msg}")
        return r.json() if r.content else {}

    async def my_repos(self) -> list[dict]:
        """Repositories the signed-in person can push to (for picking one after GitHub sign-in)."""
        repos = await self._call("GET", "/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member")
        return [{"full_name": r["full_name"], "private": r.get("private", False), "pushed_at": r.get("pushed_at")}
                for r in repos if (r.get("permissions") or {}).get("push", True)]

    async def repo_info(self) -> dict:
        info = await self._call("GET", f"/repos/{self.repo}")
        return {"full_name": info.get("full_name", self.repo), "default_branch": info.get("default_branch", "main"),
                "private": info.get("private"), "can_push": (info.get("permissions") or {}).get("push", True)}

    async def read_file(self, path: str, ref: str | None = None) -> str:
        q = f"?ref={ref}" if ref else ""
        data = await self._call("GET", f"/repos/{self.repo}/contents/{path.lstrip('/')}{q}")
        if isinstance(data, list):
            return "\n".join(f"{'dir ' if x.get('type') == 'dir' else ''}{x.get('path')}" for x in data)
        text = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        return text[:MAX_FILE_CHARS] + ("\n... [truncated]" if len(text) > MAX_FILE_CHARS else "")

    async def list_files(self, ref: str | None = None, prefix: str = "") -> list[str]:
        branch = ref or (await self.repo_info())["default_branch"]
        tree = await self._call("GET", f"/repos/{self.repo}/git/trees/{branch}?recursive=1")
        paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
        return [p for p in paths if p.startswith(prefix)][:2000]

    async def search_code(self, query: str) -> list[dict]:
        data = await self._call("GET", "/search/code", params={"q": f"{query} repo:{self.repo}", "per_page": 20})
        return [{"path": i.get("path"), "url": i.get("html_url")} for i in data.get("items", [])]

    async def list_issues(self, state: str = "open", limit: int = 30) -> list[dict]:
        data = await self._call("GET", f"/repos/{self.repo}/issues", params={"state": state, "per_page": min(limit, 100)})
        return [{"number": i["number"], "title": i["title"], "labels": [lbl.get("name") for lbl in i.get("labels", [])],
                 "body": (i.get("body") or "")[:1500], "url": i.get("html_url")}
                for i in data if "pull_request" not in i]

    async def open_pull_request(self, *, branch: str, title: str, body: str, files: list[dict],
                                base: str | None = None) -> dict:
        """Create a branch from base, commit the files to it, and open a pull request."""
        base = base or (await self.repo_info())["default_branch"]
        branch = safe_branch(branch)
        head = await self._call("GET", f"/repos/{self.repo}/git/ref/heads/{base}")
        await self._call("POST", f"/repos/{self.repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": head["object"]["sha"]})
        for f in files:
            path = f["path"].lstrip("/")
            sha = None
            try:
                existing = await self._call("GET", f"/repos/{self.repo}/contents/{path}?ref={branch}")
                sha = existing.get("sha") if isinstance(existing, dict) else None
            except GitHubError:
                sha = None  # a new file
            payload = {"message": f.get("message") or f"{title}: {path}", "branch": branch,
                       "content": base64.b64encode(f["content"].encode()).decode()}
            if sha:
                payload["sha"] = sha
            await self._call("PUT", f"/repos/{self.repo}/contents/{path}", json=payload)
        pr = await self._call("POST", f"/repos/{self.repo}/pulls", json={"title": title, "body": body, "head": branch, "base": base})
        return {"number": pr["number"], "url": pr.get("html_url"), "branch": branch, "base": base}

    async def pull_request(self, number: int) -> dict:
        pr = await self._call("GET", f"/repos/{self.repo}/pulls/{number}")
        return {"number": pr["number"], "title": pr.get("title"), "url": pr.get("html_url"), "state": pr.get("state"),
                "merged": pr.get("merged"), "additions": pr.get("additions"), "deletions": pr.get("deletions"),
                "changed_files": pr.get("changed_files"), "head": (pr.get("head") or {}).get("ref"),
                "head_sha": (pr.get("head") or {}).get("sha")}

    async def pull_request_files(self, number: int) -> list[dict]:
        rows = await self._call("GET", f"/repos/{self.repo}/pulls/{number}/files?per_page=100")
        return [{"path": f.get("filename"), "status": f.get("status"), "additions": f.get("additions", 0),
                 "deletions": f.get("deletions", 0)} for f in rows or []]

    async def checks_state(self, sha: str | None) -> str:
        """success, pending, failure, or none (no checks ran)."""
        if not sha:
            return "none"
        runs = (await self._call("GET", f"/repos/{self.repo}/commits/{sha}/check-runs?per_page=100")).get("check_runs") or []
        status = await self._call("GET", f"/repos/{self.repo}/commits/{sha}/status")
        statuses = status.get("statuses") or []
        if not runs and not statuses:
            return "none"
        if any(r.get("status") != "completed" for r in runs) or any(x.get("state") == "pending" for x in statuses):
            return "pending"
        if any(r.get("conclusion") not in ("success", "neutral", "skipped") for r in runs) or any(
                x.get("state") in ("failure", "error") for x in statuses):
            return "failure"
        return "success"

    async def merge_pull_request(self, number: int, method: str = "squash") -> dict:
        r = await self._call("PUT", f"/repos/{self.repo}/pulls/{number}/merge", json={"merge_method": method})
        return {"merged": r.get("merged", False), "sha": r.get("sha"), "message": r.get("message")}
