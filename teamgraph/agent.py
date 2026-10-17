"""A real agent loop: Gemini picks tools, every tool call goes over MCP (stdio) to teamgraph.mcp_server,
so the model can only see and change the world through FalkorDB.

  GEMINI_API_KEY=... python -m teamgraph.agent --seed recall "Support says battery life is 3.5 hours, not 35"
  GEMINI_API_KEY=... python -m teamgraph.agent session Reel
  GEMINI_API_KEY=... python -m teamgraph.agent session Quill

Prints each tool call and its result, then the agent's summary and token use. Uses $TEAMGRAPH_GRAPH /
$TEAMGRAPH_DB / $FALKORDB_URL like the MCP server. `--seed` loads the synthetic Acme Notes story first (wipes that graph)."""
import asyncio, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, "prompts.json")))
ROLES = {"Scout": "research", "Quill": "copywriting", "Reel": "video and captions", "Lens": "QA"}
RECALL_TOOLS = ["check_receipts", "claim_risk", "chokepoints", "correct_claim", "recall_plan", "why_shortest",
                "requeue_tainted", "draft_recall_memo", "remember_episode", "trust_ledger"]
SESSION_TOOLS = ["start_session", "complete_task", "hand_off", "remember_episode", "recall"]

def _a(o, *names):
    """Field across MCP SDK versions (snake_case or camelCase)."""
    for n in names:
        if hasattr(o, n): return getattr(o, n)

def to_gemini(tool):
    """MCP tool (JSON Schema) -> Gemini function declaration (OpenAPI subset)."""
    def clean(s):
        out = {k: v for k, v in s.items() if k in ("type", "description", "items", "properties", "required", "enum")}
        if "properties" in out: out["properties"] = {k: clean(v) for k, v in out["properties"].items()}
        if "items" in out: out["items"] = clean(out["items"])
        if "anyOf" in s and "type" not in out: out["type"] = "string"
        return out
    params = clean(_a(tool, "input_schema", "inputSchema") or {"type": "object"})
    d = {"name": tool.name, "description": (tool.description or tool.name)[:900]}
    if params.get("properties"): d["parameters"] = params
    return d

def gemini(key, model, contents, decls):
    body = {"contents": contents, "tools": [{"functionDeclarations": decls}], "generationConfig": {"temperature": 0}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    return json.load(urllib.request.urlopen(req, timeout=60))

async def run(mode, arg, call_llm=None, log=print):
    """Run one agent ('recall' with a correction, or 'session' with an agent name).
    `call_llm(contents, decls)` can be injected (tests); default calls Gemini."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LUMEGRID_GEMINI_API_KEY")
    model = P["model"]
    call_llm = call_llm or (lambda c, d: gemini(key, model, c, d))
    prompt = P["recall"].format(correction=arg) if mode == "recall" else P["session"].format(agent=arg, role=ROLES.get(arg, "team"))
    allowed = RECALL_TOOLS if mode == "recall" else SESSION_TOOLS
    params = StdioServerParameters(command=sys.executable, args=["-m", "teamgraph.mcp_server"], env=dict(os.environ))
    trace, usage = [], {"in": 0, "out": 0}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t for t in (await s.list_tools()).tools if t.name in allowed]
            decls = [to_gemini(t) for t in tools]
            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            for _ in range(P["max_turns"]):
                resp = call_llm(contents, decls)
                um = resp.get("usageMetadata", {}); usage["in"] += um.get("promptTokenCount", 0); usage["out"] += um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0)
                msg = resp["candidates"][0]["content"]; contents.append(msg)
                calls = [p["functionCall"] for p in msg.get("parts", []) if "functionCall" in p]
                if not calls:
                    text = "".join(p.get("text", "") for p in msg.get("parts", []))
                    return dict(summary=text.strip(), trace=trace, usage=usage, model=model)
                parts = []
                for c in calls:
                    res = await s.call_tool(c["name"], c.get("args") or {})
                    sc = _a(res, "structured_content", "structuredContent")
                    out = sc if sc is not None else "\n".join(getattr(x, "text", "") for x in res.content)
                    if isinstance(sc, dict) and list(sc) == ["result"]: out = sc["result"]
                    if isinstance(out, str):
                        try: out = json.loads(out)
                        except ValueError: pass
                    if _a(res, "is_error", "isError"): out = {"error": out}
                    trace.append(dict(tool=c["name"], args=c.get("args") or {}, result=out))
                    log(f"→ {c['name']}({json.dumps(c.get('args') or {})})\n  {json.dumps(out)[:300]}")
                    parts.append({"functionResponse": {"name": c["name"], "response": out if isinstance(out, dict) else {"result": out}}})
                contents.append({"role": "user", "parts": parts})
    return dict(summary="(stopped: turn limit)", trace=trace, usage=usage, model=model)

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--seed"]
    if "--seed" in sys.argv:
        from .taint import connect; from .demo_seed import seed; seed(connect())
    out = asyncio.run(run(a[0], a[1] if len(a) > 1 else "Support says battery life is 3.5 hours, not 35"))
    print("\nSUMMARY:", out["summary"]); print("tokens:", out["usage"])
