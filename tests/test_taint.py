import os, pytest
from teamgraph.taint import connect
from teamgraph.demo_seed import seed

@pytest.fixture
def t(tmp_path):
    os.environ.pop("FALKORDB_URL", None); os.environ["TEAMGRAPH_DB"] = str(tmp_path/"d.db")
    x = connect("d"); seed(x); return x

def test_receipts_catch_decimal_and_unsourced(t):
    bad = {r["claim"]: r["reason"] for r in t.receipts()}
    assert set(bad) == {"c-battery", "c-users"}
    assert "3.5" in bad["c-battery"] and "no source" in bad["c-users"]
def test_correction_cascades_multi_hop(t):
    hit = {r["id"]: r["hops"] for r in t.correct("c-battery", "3.5", "decimal dropped")}
    assert set(hit) == {"brief","blog","landing","og","script","short","captions","x1","x2","email"}
    assert hit["brief"] == 1 and hit["x2"] == 4
    assert "faq" not in hit   # FAQ never used the battery claim
def test_why_returns_path_and_source(t):
    t.correct("c-battery", "3.5", "decimal dropped")
    w = t.why("short")[0]
    assert w["path"][0] == "YouTube Short" and w["path"][-1].startswith("Records for 35")
    assert w["source"].startswith("Acme Notes spec") and "3.5" in w["quote"]
def test_requeue_goes_to_producer(t):
    t.correct("c-battery", "3.5", "x"); owners = {(r["agent"], r["title"]) for r in t.requeue()}
    assert ("Reel", "YouTube Short") in owners and ("Quill", "Launch blog post") in owners
def test_requeue_task_ids_are_stable_and_idempotent(t):
    t.correct("c-battery", "3.5", "x")
    first = {r["task"] for r in t.requeue()}; second = {r["task"] for r in t.requeue()}
    assert first == second and "redo-short" in first and all(x.startswith("redo-") for x in first)
    n = t.g.query("MATCH (k:Task) RETURN count(k), count(DISTINCT k.id)").result_set[0]
    assert n[0] == n[1] == len(first)            # one Task per artifact, every one with an id
def test_trust_ledger(t):
    t.receipts(); tr = {r["agent"]: r["trust"] for r in t.trust()}
    assert tr["Scout"] == pytest.approx(0.67, abs=.01) and tr["Quill"] == 0.0 and tr["Lens"] == "unrated"
def test_persists(tmp_path):
    os.environ["TEAMGRAPH_DB"] = str(tmp_path/"p.db"); a = connect("p"); seed(a); a.correct("c-battery","3.5","x"); del a
    b = connect("p"); assert any(n["status"] == "tainted" for n in b.snapshot()["nodes"])
def test_recall_most_viewed_first(t):
    t.correct("c-battery", "3.5", "decimal dropped"); r = t.recall()
    reach = [i["reach"] for i in r["items"]]
    assert r["items"][0]["id"] == "short" and reach == sorted(reach, reverse=True)
    assert r["items"][0]["owner"] == "Reel" and r["total_reach"] == sum(reach) and r["live_urls"] == 6
    assert "faq" not in {i["id"] for i in r["items"]}
def test_scale_seed_and_bench(tmp_path):
    from teamgraph.scale import seed_scale, bench
    os.environ["TEAMGRAPH_DB"] = str(tmp_path/"s.db"); x = connect("s")
    assert seed_scale(x, 40, 25) > 1000
    b = bench(x, "c7", runs=3)
    assert b["nodes"] > 1000 and b["downstream"] >= 25
    assert b["max_hops"] >= 3 and b["recall_top"]["reach"] == max(i["reach"] for i in x.recall()["items"])
