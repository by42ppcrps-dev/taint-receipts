"""Scale seed + benchmark: thousands of synthetic published artifacts, then time the recall traversal in FalkorDB.
Run: .venv/bin/python -m teamgraph.scale [n_claims] [artifacts_per_claim]"""

from __future__ import annotations

import contextlib
import random
import sys
import time
from typing import Any

from .cypher import register, run
from .taint import Q as taint_q
from .taint import Taint, connect

KINDS = [("post", 1500), ("video", 20000), ("email", 5000), ("image", 8000), ("blog", 3000), ("page", 10000)]
Q = register(
    {
        "claims": """MATCH (a:Agent {name:'Scout'}) UNWIND $rows AS r
   CREATE (c:Claim {id:r.id, text:r.text, value:r.value, status:'ok'}) CREATE (a)-[:ASSERTED]->(c)""",
        "artifacts": """UNWIND $rows AS r MATCH (a:Agent {name:r.agent})
   CREATE (x:Artifact {id:r.id, kind:r.kind, title:r.title, status:'live', reach:r.reach, url:r.url, owner:r.agent})
   CREATE (a)-[:PRODUCED]->(x)""",
        "idx_artifact": "CREATE INDEX FOR (n:Artifact) ON (n.id)",
        "idx_claim": "CREATE INDEX FOR (n:Claim) ON (n.id)",
        "edges_to_claim": "UNWIND $rows AS e MATCH (x:Artifact {id:e.c}) MATCH (y:Claim {id:e.p}) CREATE (x)-[:DERIVED_FROM]->(y)",
        "edges_to_artifact": "UNWIND $rows AS e MATCH (x:Artifact {id:e.c}) MATCH (y:Artifact {id:e.a}) CREATE (x)-[:DERIVED_FROM]->(y)",
        "count_nodes": "MATCH (n) RETURN count(n)",
        "count_edges": "MATCH ()-[r]->() RETURN count(r)",
        "cascade_count": "MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(:Claim {id:$id}) RETURN count(DISTINCT x), max(length(p))",
    }
)


def seed_scale(t: Taint, n_claims: int = 200, per_claim: int = 25, seed: int = 7) -> int:
    rnd = random.Random(seed)  # noqa: S311  # synthetic benchmark data, not crypto
    g = t.g
    t.wipe()
    for n in ["Scout", "Quill", "Reel", "Lens"]:
        t.agent(n)
    claims = [{"id": f"c{i}", "text": f"Synthetic claim {i}", "value": str(i)} for i in range(n_claims)]
    run(g, Q["claims"], {"rows": claims})
    arts: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for i in range(n_claims):
        ids: list[str] = []
        for j in range(per_claim):
            k, base = rnd.choice(KINDS)
            aid = f"a{i}-{j}"
            arts.append(
                {
                    "id": aid,
                    "kind": k,
                    "title": f"{k} {i}-{j}",
                    "reach": int(base * rnd.random()),
                    "url": f"https://example.test/{aid}",
                    "agent": rnd.choice(["Quill", "Reel"]),
                }
            )
            # each artifact derives from the claim (roots) or an earlier artifact in the chain -> real multi-hop depth
            edges.append({"c": aid, "p": f"c{i}"} if j < 2 else {"c": aid, "a": rnd.choice(ids[-4:])})
            ids.append(aid)
        if i % 10 == 0 and i:  # cross-links between claim trees
            edges.append({"c": f"a{i}-{per_claim - 1}", "a": f"a{i - 1}-0"})
    for off in range(0, len(arts), 2000):
        run(g, Q["artifacts"], {"rows": arts[off : off + 2000]})
    for idx in ("idx_artifact", "idx_claim"):
        with contextlib.suppress(Exception):  # index survives DETACH DELETE on re-seed
            run(g, Q[idx])
    for qk, key in (("edges_to_claim", "p"), ("edges_to_artifact", "a")):
        rows = [e for e in edges if key in e]
        for off in range(0, len(rows), 2000):
            run(g, Q[qk], {"rows": rows[off : off + 2000]})
    return len(claims) + len(arts) + 4


def bench(t: Taint, claim: str = "c42", runs: int = 20) -> dict[str, Any]:
    n = run(t.g, Q["count_nodes"])[0][0]
    e = run(t.g, Q["count_edges"])[0][0]
    ts: list[float] = []
    r: list[Any] = []
    for _ in range(runs):
        s = time.perf_counter()
        r = run(t.g, Q["cascade_count"], {"id": claim})[0]
        ts.append((time.perf_counter() - s) * 1000)
    ts.sort()
    s = time.perf_counter()
    # Times the cascade query itself. Public correct() also requires a cited quote;
    # these synthetic claims have none, so the benchmark does not go through that gate.
    run(t.g, taint_q["correct"], {"id": claim, "value": "fixed", "reason": "bench"})
    plan = t.recall()
    corr = (time.perf_counter() - s) * 1000
    return {
        "nodes": n,
        "edges": e,
        "downstream": r[0],
        "max_hops": r[1],
        "traverse_ms_p50": round(ts[len(ts) // 2], 2),
        "traverse_ms_max": round(ts[-1], 2),
        "correct_plus_recall_ms": round(corr, 2),
        "recall_top": plan["items"][0] if plan["items"] else None,
        "total_reach": plan["total_reach"],
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    tt = connect("taint_scale")
    s0 = time.perf_counter()
    seed_scale(tt, int(a[0]) if a else 200, int(a[1]) if len(a) > 1 else 25)
    print(f"seeded in {time.perf_counter() - s0:.1f}s")  # noqa: T201
    print(bench(tt))  # noqa: T201
