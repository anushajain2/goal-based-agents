"""A scripted stand-in for the Anthropic client, so the agent loop runs without an API key."""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Callable
from typing import Any


class Obj:
    def __init__(self, **data: Any) -> None:
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def model_dump(self, **_kw) -> dict:
        return dict(self._data)


_ids = itertools.count(1)


def tool_use(name: str, **inp) -> dict:
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": inp}


def text(t: str) -> dict:
    return {"type": "text", "text": t}


class FakeAnthropic:
    """`script` is called with the request kwargs and returns a list of content-block dicts.

    Guardrail-review requests (they carry output_config.format) are answered by `reviewer`,
    which defaults to "no rule broken".
    """

    def __init__(self, script: Callable[[dict], list[dict]], reviewer: Callable[[dict], dict] | None = None,
                 planner: Callable[[dict], dict] | None = None,
                 org_planner: Callable[[dict], dict] | None = None, searches: int = 0,
                 classifier: Callable[[dict], dict] | None = None, scanner: Callable[[dict], dict] | None = None,
                 routes: dict[str, Callable[[dict], dict]] | None = None):
        self.script = script
        self.reviewer = reviewer or (lambda kw: {"violates": False, "rule": "", "explanation": ""})
        self.planner = planner or (lambda kw: {"assessment": "Fresh start.", "plan": ["Research", "Post once"],
                                               "strategy": ""})
        self.org_planner = org_planner  # organization setup: the team plan
        self.classifier = classifier or (lambda kw: {"company_type": "general", "size": "small", "reason": ""})
        self.routes = routes or {}  # structured output by a property of its schema, checked first
        self.scanner = scanner or (lambda kw: {"findings": [], "deeper": []})  # setup: what they're missing
        self.searches = searches  # web searches reported per agent-loop call
        self.calls: list[dict] = []
        self.beta = Obj(messages=Obj(create=self._create))

    async def _create(self, **kwargs):
        kwargs = copy.deepcopy(kwargs)  # snapshot: the runner keeps appending to its lists
        self.calls.append(kwargs)
        fmt = kwargs.get("output_config", {}).get("format")
        if fmt:
            props = fmt["schema"]["properties"]
            route = next((f for k, f in self.routes.items() if k in props), None)
            answer = (route if route else self.org_planner if "departments" in props
                      else self.scanner if "findings" in props
                      else self.classifier if "company_type" in props
                      else self.planner if "plan" in props else self.reviewer)
            content = [text(json.dumps(answer(kwargs)))]
            stop = "end_turn"
        else:
            content = self.script(kwargs)
            stop = ("tool_use" if any(b["type"] == "tool_use" for b in content)
                    else "pause_turn" if content and content[-1]["type"] == "server_tool_use" else "end_turn")
        return Obj(
            content=[Obj(**b) for b in content],
            stop_reason=stop,
            model=kwargs["model"],
            usage=Obj(input_tokens=2000, output_tokens=300, cache_creation_input_tokens=0,
                      cache_read_input_tokens=0,
                      server_tool_use=Obj(web_search_requests=self.searches) if self.searches and not fmt else None),
        )

    def agent_calls(self) -> list[dict]:
        return [c for c in self.calls if not c.get("output_config", {}).get("format")]
