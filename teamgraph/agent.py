"""A real agent loop: Gemini picks tools, every tool call goes over MCP (stdio) to teamgraph.mcp_server,
so the model can only see and change the world through FalkorDB.

  GEMINI_API_KEY=... python -m teamgraph.agent --seed recall "Support says battery life is 3.5 hours, not 35"
  GEMINI_API_KEY=... python -m teamgraph.agent session Reel
  GEMINI_API_KEY=... python -m teamgraph.agent session Quill

Prints each tool call and its result, then the agent's summary and token use. Uses $TEAMGRAPH_GRAPH /
$TEAMGRAPH_DB / $FALKORDB_URL like the MCP server. `--seed` loads the synthetic Acme Notes story first (wipes that graph)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from typing import Any

JSON = dict[str, Any]
LLM = Callable[[list[JSON], list[JSON]], JSON]

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "prompts.json")) as _f:
    P: JSON = json.load(_f)
ROLES = {"Scout": "research", "Quill": "copywriting", "Reel": "video and captions", "Lens": "QA"}
TEAM = set(ROLES)
_FENCE = re.compile('[\x00-\x1f\x7f\u0085\u2028\u2029<>"]+')


def untrusted(text: str, limit: int = 300) -> str:
    """Drop characters that can leave a prompt fence or break a line. Replacement is literal, never re-parsed."""
    return re.sub(r"\s+", " ", _FENCE.sub(" ", text)).strip()[:limit]


def scrub(v: Any) -> Any:
    """Tool results are data. Strip fence characters before they go back to the model."""
    if isinstance(v, str):
        return untrusted(v, 2000)
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {str(k): scrub(x) for k, x in v.items()}
    return v


def recall_prompt(correction: str) -> str:
    return str(P["recall"]).format(correction=untrusted(correction, 300))


def session_prompt(agent: str) -> str:
    safe = untrusted(agent, 32)
    return str(P["session"]).replace("{role}", ROLES.get(agent, "team")).replace("{agent}", safe)


RECALL_TOOLS = [
    "check_receipts",
    "claim_risk",
    "chokepoints",
    "correct_claim",
    "recall_plan",
    "why_shortest",
    "requeue_tainted",
    "draft_recall_memo",
    "remember_episode",
    "trust_ledger",
]
SESSION_TOOLS = ["start_session", "complete_task", "hand_off", "remember_episode", "recall"]
MAX_CALLS = 30


def guard(mode: str, who: str, name: str, a: Any) -> JSON | None:
    """Narrow scoping (mirrors worker/src/agent.js): only this mode's tools, and the agent may only act as itself."""
    if name not in (RECALL_TOOLS if mode == "recall" else SESSION_TOOLS):
        return {"error": "tool not allowed"}
    if not isinstance(a, dict):
        return {"error": "bad arguments"}
    if mode == "session":
        if name == "start_session" and a.get("agent") != who:
            return {"error": f"you are {who}"}
        if name == "hand_off" and a.get("from_agent") != who:
            return {"error": f"you can only hand off your own tasks ({who})"}
        if name == "hand_off" and a.get("to_agent") not in TEAM:
            return {"error": "you can only hand off to Scout, Quill, Reel, or Lens"}
        if name == "remember_episode" and a.get("agent") != who:
            return {"error": f"log episodes as {who}"}
    if mode == "recall" and name == "remember_episode" and a.get("agent") != "RecallAgent":
        return {"error": "log episodes as RecallAgent"}
    return None


def _a(o: Any, *names: str) -> Any:
    """Field across MCP SDK versions (snake_case or camelCase)."""
    for n in names:
        if hasattr(o, n):
            return getattr(o, n)
    return None


def to_gemini(tool: Any) -> JSON:
    """MCP tool (JSON Schema) -> Gemini function declaration (OpenAPI subset)."""

    def clean(s: JSON) -> JSON:
        out = {k: v for k, v in s.items() if k in ("type", "description", "items", "properties", "required", "enum")}
        if "properties" in out:
            out["properties"] = {k: clean(v) for k, v in out["properties"].items()}
        if "items" in out:
            out["items"] = clean(out["items"])
        if "anyOf" in s and "type" not in out:
            out["type"] = "string"
        return out

    params = clean(_a(tool, "input_schema", "inputSchema") or {"type": "object"})
    d: JSON = {"name": tool.name, "description": (tool.description or tool.name)[:900]}
    if params.get("properties"):
        d["parameters"] = params
    return d


def gemini(key: str, model: str, contents: list[JSON], decls: list[JSON]) -> JSON:
    body = {"contents": contents, "tools": [{"functionDeclarations": decls}], "generationConfig": {"temperature": 0}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out: JSON = json.load(resp)
    return out


async def run(mode: str, arg: str, call_llm: LLM | None = None, log: Callable[[str], object] = print) -> JSON:  # noqa: PLR0915
    """Run one agent ('recall' with a correction, or 'session' with an agent name).
    `call_llm(contents, decls)` can be injected (tests); default calls Gemini."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LUMEGRID_GEMINI_API_KEY")
    model = P["model"]
    if call_llm is None:
        if not key:
            raise SystemExit("set GEMINI_API_KEY")
        api_key: str = key

        def call_llm(c: list[JSON], d: list[JSON]) -> JSON:
            return gemini(api_key, model, c, d)

    prompt = recall_prompt(str(arg)) if mode == "recall" else session_prompt(arg)
    allowed = RECALL_TOOLS if mode == "recall" else SESSION_TOOLS
    params = StdioServerParameters(command=sys.executable, args=["-m", "teamgraph.mcp_server"], env=dict(os.environ))
    trace: list[JSON] = []
    usage = {"in": 0, "out": 0}
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [t for t in (await s.list_tools()).tools if t.name in allowed]
        decls = [to_gemini(t) for t in tools]
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        for _ in range(P["max_turns"]):
            resp = call_llm(contents, decls)
            um = resp.get("usageMetadata", {})
            usage["in"] += um.get("promptTokenCount", 0)
            usage["out"] += um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0)
            msg = resp["candidates"][0]["content"]
            contents.append(msg)
            calls = [p["functionCall"] for p in msg.get("parts", []) if "functionCall" in p]
            if not calls:
                text = "".join(p.get("text", "") for p in msg.get("parts", []))
                return {"summary": text.strip(), "trace": trace, "usage": usage, "model": model}
            parts = []
            for c in calls:
                if len(trace) >= MAX_CALLS:
                    return {"summary": "(stopped: tool-call limit)", "trace": trace, "usage": usage, "model": model}
                g = guard(mode, arg, c["name"], c.get("args") or {})
                if g:
                    trace.append({"tool": c["name"], "args": c.get("args") or {}, "result": g})
                    parts.append({"functionResponse": {"name": c["name"], "response": g}})
                    continue
                res = await s.call_tool(c["name"], c.get("args") or {})
                sc = _a(res, "structured_content", "structuredContent")
                out = sc if sc is not None else "\n".join(getattr(x, "text", "") for x in res.content)
                if isinstance(sc, dict) and list(sc) == ["result"]:
                    out = sc["result"]
                if isinstance(out, str):
                    with contextlib.suppress(ValueError):
                        out = json.loads(out)
                if _a(res, "is_error", "isError"):
                    out = {"error": out}
                trace.append({"tool": c["name"], "args": c.get("args") or {}, "result": out})
                log(f"→ {c['name']}({json.dumps(c.get('args') or {})})\n  {json.dumps(out)[:300]}")
                safe = scrub(out)
                parts.append({"functionResponse": {"name": c["name"], "response": safe if isinstance(safe, dict) else {"result": safe}}})
            contents.append({"role": "user", "parts": parts})
    return {"summary": "(stopped: turn limit)", "trace": trace, "usage": usage, "model": model}


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--seed"]
    if "--seed" in sys.argv:
        from .demo_seed import seed
        from .taint import connect

        seed(connect())
    out = asyncio.run(run(a[0], a[1] if len(a) > 1 else "Support says battery life is 3.5 hours, not 35"))
    print("\nSUMMARY:", out["summary"])
    print("tokens:", out["usage"])
