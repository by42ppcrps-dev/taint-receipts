"""Agent loop over real MCP stdio, with a scripted LLM (no network), plus the graph-algorithm tools."""
import asyncio, pytest
from teamgraph.taint import connect
from teamgraph.demo_seed import seed
from teamgraph.graph import TeamGraph
from teamgraph import agent

@pytest.fixture
def t(tmp_path, monkeypatch):
    monkeypatch.delenv("FALKORDB_URL", raising=False)
    monkeypatch.setenv("TEAMGRAPH_DB", str(tmp_path / "ag.db")); monkeypatch.setenv("TEAMGRAPH_GRAPH", "ag")
    x = connect(); seed(x); return x

def test_pagerank_risk_ranks_claims_with_reach(t):
    r = {x["claim"]: x for x in t.risk()}
    assert set(r) == {"c-battery", "c-price", "c-lang", "c-users"}
    assert r["c-battery"]["downstream"] == 10 and r["c-battery"]["exposed_reach"] > 70000 and r["c-battery"]["pagerank"] > 0

def test_betweenness_finds_brief_and_blog_as_chokepoints(t):
    assert {"brief", "blog"} <= {x["id"] for x in t.chokepoints(3)}

def test_shortest_path_why(t):
    t.correct("c-battery", "3.5", "decimal dropped")
    w = t.why_shortest("short")
    assert w[0]["ids"] == ["short", "script", "blog", "brief", "c-battery"] and w[0]["hops"] == 4 and "3.5" in w[0]["quote"]
    assert t.why_shortest("faq") == []

def test_handoff_refuses_ping_pong_and_self(t):
    tg = TeamGraph(t.g); t.correct("c-battery", "3.5", "x"); t.requeue()
    tg.handoff("Reel", "Quill", "redo-script", "copy fix")
    with pytest.raises(ValueError, match="instead of handing it back"): tg.handoff("Quill", "Reel", "redo-script", "back")
    with pytest.raises(ValueError, match="yourself"): tg.handoff("Quill", "Quill", "redo-script", "me")

def scripted(steps):
    it = iter(steps)
    def llm(contents, decls):
        names = {d["name"] for d in decls}; nxt = next(it)
        if isinstance(nxt, str): return {"candidates": [{"content": {"role": "model", "parts": [{"text": nxt}]}}]}
        assert all(c[0] in names for c in nxt), (nxt, names)
        return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}} for n, a in nxt]}}]}
    return llm

def test_recall_then_new_sessions_remember_and_hand_off(t):
    s1 = asyncio.run(agent.run("recall", "battery is 3.5 h", scripted([
        [("check_receipts", {}), ("claim_risk", {})],
        [("correct_claim", {"claim": "c-battery", "value": "3.5", "reason": "decimal dropped"})],
        [("recall_plan", {}), ("why_shortest", {"artifact": "short"})],
        [("requeue_tainted", {})],
        [("draft_recall_memo", {"owner": "Reel", "text": "Fix the Short first (27,400 est.)"}), ("draft_recall_memo", {"owner": "Quill", "text": "Landing hero first"})],
        [("remember_episode", {"agent": "RecallAgent", "text": "Corrected c-battery; 10 tainted", "session": "s1"})],
        "Done."]), log=lambda *_: None))
    tools = [x["tool"] for x in s1["trace"]]
    assert tools[:3] == ["check_receipts", "claim_risk", "correct_claim"] and tools.count("draft_recall_memo") == 2
    assert next(x for x in s1["trace"] if x["tool"] == "recall_plan")["result"]["items"][0]["id"] == "short"
    s2 = asyncio.run(agent.run("session", "Reel", scripted([
        [("start_session", {"agent": "Reel"})],
        [("complete_task", {"task": "redo-captions"}), ("hand_off", {"from_agent": "Reel", "to_agent": "Quill", "task": "redo-script", "note": "script copy says 35 h"})],
        [("remember_episode", {"agent": "Reel", "text": "Fixed captions, handed script to Quill", "session": "s2"})],
        "Done."]), log=lambda *_: None))
    brief = s2["trace"][0]["result"]
    assert {x["task"] for x in brief["tasks"]} == {"redo-short", "redo-script", "redo-captions"}
    assert "Short first" in brief["memos"][0]["text"]
    s3 = asyncio.run(agent.run("session", "Quill", scripted([
        [("start_session", {"agent": "Quill"})],
        [("hand_off", {"from_agent": "Quill", "to_agent": "Reel", "task": "redo-script", "note": "yours"})],
        [("complete_task", {"task": "redo-script"})], "Done."]), log=lambda *_: None))
    b3 = s3["trace"][0]["result"]
    assert any(x["task"] == "redo-script" and x["from_agent"] == "Reel" for x in b3["tasks"])
    assert "error" in s3["trace"][1]["result"]                     # ping-pong refused by the graph rule
    g = t.g
    assert g.query("MATCH (t:Task {id:'redo-script'}) RETURN t.status").result_set[0][0] == "done"
    assert g.query("MATCH (t:Task {id:'redo-captions'}) RETURN t.status").result_set[0][0] == "done"
