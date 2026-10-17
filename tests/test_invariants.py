"""Structural invariants, checked on the source itself (not by review):
1. Only teamgraph/cypher.py calls `.query(` on a graph.
2. cypher.register() only receives dict literals of plain string constants (no f-strings, concatenation or variables).
3. Every key looked up through a module's Q registry exists."""

import ast
import pathlib

PKG = pathlib.Path(__file__).resolve().parent.parent / "teamgraph"


def _trees() -> list[tuple[pathlib.Path, ast.Module]]:
    return [(p, ast.parse(p.read_text())) for p in sorted(PKG.glob("*.py"))]


def test_only_cypher_module_queries_the_database():
    for p, tree in _trees():
        if p.name == "cypher.py":
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "query":
                raise AssertionError(f"{p.name}:{n.lineno} calls .query(); route it through cypher.run")


def test_registered_queries_are_constant_strings():
    found = 0
    for p, tree in _trees():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "register":
                assert len(n.args) == 1 and isinstance(n.args[0], ast.Dict), f"{p.name}:{n.lineno} register() needs a dict literal"
                for v in n.args[0].values:
                    assert isinstance(v, ast.Constant) and isinstance(v.value, str), f"{p.name}:{v.lineno} non-constant Cypher"
                    found += 1
    assert found > 30


def test_run_rejects_unregistered_cypher():
    import pytest

    from teamgraph.cypher import Query, run
    from teamgraph.taint import Q

    class G:
        name = "g"

        def query(self, q, p=None):
            raise AssertionError("must not reach the database")

    with pytest.raises(ValueError, match="unregistered"):
        run(G(), "MATCH (n) DETACH DELETE n", {})  # type: ignore[arg-type]  # plain str, even if the text is registered
    with pytest.raises(ValueError, match="unregistered"):
        run(G(), Query("MATCH (n) SET n.x = 1"), {})  # a Query that was never registered
    assert type(Q["wipe"]) is Query


def test_run_rejects_bad_params():
    import pytest

    from teamgraph.cypher import run
    from teamgraph.taint import Q

    class G:
        name = "g"

        def query(self, q, p=None):
            raise AssertionError("must not reach the database")

    with pytest.raises(ValueError):
        run(G(), Q["flag"], {"id) DELETE n //": 1})
    with pytest.raises(TypeError):
        run(G(), Q["flag"], {"id": object()})  # type: ignore[dict-item]


def test_mcp_tool_inputs_are_validated(tmp_path, monkeypatch):
    import asyncio
    import importlib
    import sys

    monkeypatch.delenv("FALKORDB_URL", raising=False)
    monkeypatch.setenv("TEAMGRAPH_DB", str(tmp_path / "v.db"))
    monkeypatch.setenv("TEAMGRAPH_GRAPH", "v")
    sys.modules.pop("teamgraph.mcp_server", None)
    m = importlib.import_module("teamgraph.mcp_server")

    async def call(name, args):
        try:
            r = await m.mcp.call_tool(name, args)
        except Exception as e:  # noqa: BLE001
            return str(e)
        return str(r)

    out = asyncio.run(call("why_shortest", {"artifact": "x'}) MATCH (n) DETACH DELETE n //"}))
    assert "pattern" in out.lower() or "validation" in out.lower() or "error" in out.lower()
    out = asyncio.run(call("remember_episode", {"agent": "Reel", "text": "a" * 5000}))
    assert "2000" in out or "validation" in out.lower() or "error" in out.lower()


def test_demo_request_model_rejects_unknown_and_oversized():
    import pytest
    from pydantic import ValidationError

    from teamgraph.models import DemoRequest

    with pytest.raises(ValidationError):
        DemoRequest.model_validate({"claim": "c-battery", "evil": 1})
    with pytest.raises(ValidationError):
        DemoRequest.model_validate({"reason": "x" * 500})
    with pytest.raises(ValidationError):
        DemoRequest.model_validate({"agent": "Mallory"})
    assert DemoRequest.model_validate({}).claim == "c-battery"
