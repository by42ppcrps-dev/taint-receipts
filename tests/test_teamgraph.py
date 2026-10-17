import os

import pytest

from teamgraph.graph import connect
from teamgraph.seed import seed


@pytest.fixture
def tg(tmp_path):
    os.environ.pop("FALKORDB_URL", None)
    os.environ["TEAMGRAPH_DB"] = str(tmp_path / "t.db")
    t = connect("t")
    seed(t)
    return t


def test_handoff_moves_ownership(tg):
    assert tg.briefing("Atlas") == []
    b = tg.briefing("Birch")
    assert b[0]["task"] == "T1" and b[0]["from_agent"] == "Atlas"


def test_bad_handoff_rejected(tg):
    with pytest.raises(ValueError):
        tg.handoff("Cobalt", "Atlas", "T1", "x")


def test_why_returns_sources_and_supersedes(tg):
    r = tg.why("discount")
    latest = r[0]
    assert latest["by"] == "Cobalt"
    assert "up to 20% off" in latest["replaced"][0] and "ftc.gov" in latest["sources"][0]


def test_semantic_and_episodic_recall(tg):
    kinds = {x["kind"] for x in tg.recall("newsletter") + tg.recall("draft")}
    assert kinds == {"fact", "episode"}


def test_procedure_drives_next_step(tg):
    assert tg.next_step("Birch")["step"] == "check claims against sources"
    tg.episode("Birch", "check claims against sources done", "s2", "T1")
    assert tg.next_step("Birch")["step"] == "accessibility check"


def test_persistence_across_sessions(tmp_path):
    os.environ["TEAMGRAPH_DB"] = str(tmp_path / "p.db")
    a = connect("p")
    seed(a)
    del a
    b = connect("p")
    assert b.briefing("Birch")[0]["task"] == "T1"


def test_complete(tg):
    tg.complete("T1")
    assert tg.briefing("Birch") == []
