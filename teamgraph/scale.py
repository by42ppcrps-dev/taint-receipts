"""Scale seed + benchmark: thousands of synthetic published artifacts, then time the recall traversal in FalkorDB.
Run: .venv/bin/python -m teamgraph.scale [n_claims] [artifacts_per_claim]"""
import random, sys, time
from .taint import connect

KINDS = [("post", 1500), ("video", 20000), ("email", 5000), ("image", 8000), ("blog", 3000), ("page", 10000)]

def seed_scale(t, n_claims=200, per_claim=25, seed=7):
    rnd = random.Random(seed); g = t.g
    g.query("MATCH (n) DETACH DELETE n")
    for n in ["Scout", "Quill", "Reel", "Lens"]: t.agent(n)
    claims = [dict(id=f"c{i}", text=f"Synthetic claim {i}", value=str(i)) for i in range(n_claims)]
    g.query("""MATCH (a:Agent {name:'Scout'}) UNWIND $rows AS r
       CREATE (c:Claim {id:r.id, text:r.text, value:r.value, status:'ok'}) CREATE (a)-[:ASSERTED]->(c)""", {"rows": claims})
    arts, edges = [], []
    for i in range(n_claims):
        ids = []
        for j in range(per_claim):
            k, base = rnd.choice(KINDS); aid = f"a{i}-{j}"
            arts.append(dict(id=aid, kind=k, title=f"{k} {i}-{j}", reach=int(base * rnd.random()),
                             url=f"https://example.test/{aid}", agent=rnd.choice(["Quill", "Reel"])))
            # each artifact derives from the claim (roots) or an earlier artifact in the chain -> real multi-hop depth
            edges.append(dict(c=aid, p=f"c{i}") if j < 2 else dict(c=aid, a=rnd.choice(ids[-4:])))
            ids.append(aid)
        if i % 10 == 0 and i:  # cross-links between claim trees
            edges.append(dict(c=f"a{i}-{per_claim-1}", a=f"a{i-1}-0"))
    for k in range(0, len(arts), 2000):
        g.query("""UNWIND $rows AS r MATCH (a:Agent {name:r.agent})
           CREATE (x:Artifact {id:r.id, kind:r.kind, title:r.title, status:'live', reach:r.reach, url:r.url, owner:r.agent})
           CREATE (a)-[:PRODUCED]->(x)""", {"rows": arts[k:k+2000]})
    for lbl in ("Artifact", "Claim"):
        try: g.query(f"CREATE INDEX FOR (n:{lbl}) ON (n.id)")
        except Exception: pass  # index survives DETACH DELETE on re-seed
    for lbl, key in (("Claim", "p"), ("Artifact", "a")):
        rows = [e for e in edges if key in e]
        for k in range(0, len(rows), 2000):
            g.query(f"""UNWIND $rows AS e MATCH (x:Artifact {{id:e.c}}) MATCH (y:{lbl} {{id:e.{key}}}) CREATE (x)-[:DERIVED_FROM]->(y)""",
                    {"rows": rows[k:k+2000]})
    return len(claims) + len(arts) + 4

def bench(t, claim="c42", runs=20):
    n = t.g.query("MATCH (n) RETURN count(n)").result_set[0][0]
    e = t.g.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    q = "MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(:Claim {id:$id}) RETURN count(DISTINCT x), max(length(p))"
    ts = []
    for _ in range(runs):
        s = time.perf_counter(); r = t.g.query(q, {"id": claim}).result_set[0]; ts.append((time.perf_counter() - s) * 1000)
    ts.sort()
    s = time.perf_counter(); t.correct(claim, "fixed", "bench"); plan = t.recall(); corr = (time.perf_counter() - s) * 1000
    return dict(nodes=n, edges=e, downstream=r[0], max_hops=r[1], traverse_ms_p50=round(ts[len(ts)//2], 2),
                traverse_ms_max=round(ts[-1], 2), correct_plus_recall_ms=round(corr, 2),
                recall_top=plan["items"][0] if plan["items"] else None, total_reach=plan["total_reach"])

if __name__ == "__main__":
    a = sys.argv[1:]; t = connect("taint_scale")
    s = time.perf_counter(); seed_scale(t, int(a[0]) if a else 200, int(a[1]) if len(a) > 1 else 25)
    print(f"seeded in {time.perf_counter()-s:.1f}s"); print(bench(t))
