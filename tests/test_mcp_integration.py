"""End-to-end over the MCP server: memory, taint and handoff tools share ONE configured graph.
Path covered (Pika #2522 item 5): source -> claim -> artifact -> receipt/correction -> recall -> requeue
-> start_session -> complete_task. The second test runs the real server over stdio with an MCP client."""

import asyncio
import importlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.delenv("FALKORDB_URL", raising=False)
    monkeypatch.setenv("TEAMGRAPH_DB", str(tmp_path / "mcp.db"))
    monkeypatch.setenv("TEAMGRAPH_GRAPH", "it")
    sys.modules.pop("teamgraph.mcp_server", None)
    return importlib.import_module("teamgraph.mcp_server")


def test_graph_is_explicitly_configured(m):
    assert m.GRAPH == "it" and m.tt.g is m.tg.g  # memory and taint tools: same graph object
    from teamgraph import web  # demo UI: its own sandbox graph, never agent memory

    assert web.DEMO_GRAPH == "taint_demo" and web.T.g.name == "taint_demo" and m.tg.g.name == "it"


def test_source_text_is_retained_and_used_by_receipts(m):
    m.add_source("spec", "Spec sheet", "https://acme.example/spec")  # URL only first
    m.add_source("spec", "Spec sheet", text="Battery life: 3.5 hours. Supports 12 languages.")  # text later
    m.add_source("spec", "Spec sheet")  # empty args never wipe
    row = m.tg.g.query("MATCH (s:Source {id:'spec'}) RETURN s.url, s.text, count(*)").result_set[0]
    assert row == ["https://acme.example/spec", "Battery life: 3.5 hours. Supports 12 languages.", 1]
    good = m.assert_claim("Scout", "Supports 12 languages", "12", ["spec"], "Supports 12 languages")
    bad = m.assert_claim("Scout", "Records for 35 hours", "35", ["spec"], "Battery life: 3.5 hours")
    fake = m.assert_claim("Scout", "Records for 40 hours", "40", ["spec"], "Battery life: 40 hours")
    flagged = {b["claim"]: b["reason"] for b in m.check_receipts()}
    assert good not in flagged and flagged[bad].startswith("said 35") and flagged[fake] == "quote not found in spec"


def test_full_path_source_to_complete_task(m):
    m.add_source("spec", "Spec sheet", "https://acme.example/spec", text="Battery life: 3.5 hours.")
    c = m.assert_claim("Scout", "Records for 35 hours", "35", ["spec"], "Battery life: 3.5 hours")
    m.register_artifact("Quill", "blog", "blog", "Launch blog", [c], url="https://acme.example/blog", reach=4200, owner="Quill")
    m.register_artifact("Reel", "short", "video", "Short", ["blog"], url="https://youtube.example/s", reach=27400, owner="Mara")
    m.register_artifact("Quill", "faq", "page", "FAQ", [], url="https://acme.example/faq", reach=900)
    assert [b["claim"] for b in m.check_receipts()] == [c]
    assert {r["id"]: r["hops"] for r in m.correct_claim(c, "3.5", "decimal dropped")} == {"blog": 1, "short": 2}
    plan = m.recall_plan()  # register_artifact metadata
    assert [(i["id"], i["reach"], i["url"], i["owner"], i["agent"]) for i in plan["items"]] == [
        ("short", 27400, "https://youtube.example/s", "Mara", "Reel"),
        ("blog", 4200, "https://acme.example/blog", "Quill", "Quill"),
    ]
    assert plan["total_reach"] == 31600 and plan["live_urls"] == 2  # faq: no path, not recalled
    q1 = m.requeue_tainted()
    q2 = m.requeue_tainted()  # stable ids, idempotent
    assert sorted(r["task"] for r in q1) == sorted(r["task"] for r in q2) == ["redo-blog", "redo-short"]
    assert [(t["task"], t["title"]) for t in m.start_session("Reel")["tasks"]] == [("redo-short", "Redo Short")]
    m.hand_off("Reel", "Quill", "redo-short", "please redo with 3.5 h")
    m.requeue_tainted()  # must not hand it back to Reel
    assert m.start_session("Reel")["tasks"] == []
    q = {t["task"]: t for t in m.start_session("Quill")["tasks"]}
    assert set(q) == {"redo-blog", "redo-short"} and q["redo-short"]["from_agent"] == "Reel"
    assert m.complete_task("redo-short") == "redo-short"
    assert [t["task"] for t in m.start_session("Quill")["tasks"]] == ["redo-blog"]
    with pytest.raises(ValueError):
        m.complete_task("no-such-task")
    m.remember_episode("Quill", "Redid the Short with 3.5 hours", task="redo-short")  # memory recall, same graph
    assert m.recall("3.5 hours")[0]["who"] == "Quill"
    assert m.why_tainted("short")[0]["path"][-1] == "Records for 35 hours"


def test_stdio_server_exposes_wired_tools(tmp_path):
    """Run `python -m teamgraph.mcp_server` as a real MCP stdio server and call tools through a client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "TEAMGRAPH_DB": str(tmp_path / "stdio.db"), "TEAMGRAPH_GRAPH": "stdio"}
    env.pop("FALKORDB_URL", None)
    params = StdioServerParameters(command=sys.executable, args=["-m", "teamgraph.mcp_server"], env=env, cwd=ROOT)

    async def run():
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            assert {"url", "reach", "owner"} <= set(tools["register_artifact"].input_schema["properties"])
            assert "text" in tools["add_source"].input_schema["properties"]

            def call(n, **a):
                return s.call_tool(n, a)

            await call("add_source", id="spec", title="Spec", text="Battery life: 3.5 hours.")
            c = (await call("assert_claim", agent="Scout", text="35 h", value="35", sources=["spec"], quote="Battery life: 3.5 hours")).content[0].text
            await call(
                "register_artifact",
                agent="Reel",
                id="short",
                kind="video",
                title="Short",
                derived_from=[c],
                url="https://y.example/s",
                reach=100,
                owner="Reel",
            )
            await call("correct_claim", claim=c, value="3.5", reason="decimal")
            await call("requeue_tainted")
            brief = json.loads((await call("start_session", agent="Reel")).content[0].text)
            assert [t["task"] for t in brief["tasks"]] == ["redo-short"]
            await call("complete_task", task="redo-short")
            assert json.loads((await call("start_session", agent="Reel")).content[0].text)["tasks"] == []

    asyncio.run(run())
