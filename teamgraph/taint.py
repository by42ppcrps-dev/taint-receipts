"""Taint + Receipts: provenance and correction propagation for an AI workforce, on FalkorDB."""
import re, time, uuid
from .graph import connect as _connect

def _id(p): return f"{p}-{uuid.uuid4().hex[:6]}"
NUM = re.compile(r"\d+(?:\.\d+)?")

Q = {
 "agent": "MERGE (a:Agent {name:$name}) ON CREATE SET a.role=$role, a.verified=0, a.refuted=0",
 "source": "MERGE (s:Source {id:$id}) SET s.title=$title, s.text=$text",
 # a Claim is an atomic statement an agent asserted, with the exact number it quoted
 "claim": """MATCH (a:Agent {name:$agent}) CREATE (c:Claim {id:$id, text:$text, value:$value, status:'ok', ts:$ts})
   CREATE (a)-[:ASSERTED]->(c)
   WITH c UNWIND $sources AS sid MATCH (s:Source {id:sid}) CREATE (c)-[:CITES {quote:$quote}]->(s) RETURN DISTINCT c.id""",
 "claim_nosrc": """MATCH (a:Agent {name:$agent}) CREATE (c:Claim {id:$id, text:$text, value:$value, status:'ok', ts:$ts})
   CREATE (a)-[:ASSERTED]->(c) RETURN c.id""",
 "artifact": """MATCH (a:Agent {name:$agent}) MERGE (x:Artifact {id:$id}) SET x.kind=$kind, x.title=$title, x.status='live',
   x.url=$url, x.reach=$reach, x.owner=$owner
   MERGE (a)-[:PRODUCED]->(x)""",
 # Recall plan: every tainted *published* artifact, biggest audience first (impact-weighted fix order)
 "recall": """MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
   RETURN x.id, x.kind, x.title, coalesce(x.reach,0), x.url, coalesce(x.owner, a.name), a.name
   ORDER BY coalesce(x.reach,0) DESC, x.id""",
 "derive": "MATCH (x {id:$child}), (y {id:$parent}) MERGE (x)-[:DERIVED_FROM]->(y)",
 # Receipts: number in claim must appear in the quoted source text
 "receipts": """MATCH (a:Agent)-[:ASSERTED]->(c:Claim) WHERE c.status='ok'
   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)
   RETURN c.id, c.text, c.value, a.name, s.id, s.text, r.quote""",
 "flag": "MATCH (c:Claim {id:$id}) SET c.status=$status, c.reason=$reason",
 # Taint: correcting a claim taints every artifact reachable via DERIVED_FROM (any depth)
 "correct": """MATCH (bad:Claim {id:$id}) SET bad.status='corrected', bad.fixed_value=$value, bad.reason=$reason
   WITH bad MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(bad)
   SET x.status='tainted' RETURN DISTINCT x.id, x.kind, x.title, length(p) ORDER BY length(p)""",
 "requeue": """MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
   MERGE (t:Task {artifact:x.id}) ON CREATE SET t.status='open', t.title='Redo '+x.title
   MERGE (a)-[:OWNS]->(t) RETURN a.name, x.title""",
 "why_tainted": """MATCH p=(x:Artifact {id:$id})-[:DERIVED_FROM*1..10]->(c:Claim) WHERE c.status IN ['corrected','refuted']
   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)
   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], c.reason, s.title, r.quote""",
 "trust": """MATCH (a:Agent) OPTIONAL MATCH (a)-[:ASSERTED]->(c:Claim)
   WITH a, count(c) AS total, sum(CASE WHEN c.status IN ['refuted','corrected'] THEN 1 ELSE 0 END) AS bad
   RETURN a.name, total, bad, CASE WHEN total=0 THEN 1.0 ELSE toFloat(total-bad)/total END AS trust ORDER BY trust DESC""",
 "nodes": "MATCH (n) RETURN id(n), labels(n)[0], coalesce(n.title, n.text, n.name, n.id), coalesce(n.status,'')",
 "edges": "MATCH (a)-[r]->(b) RETURN id(a), id(b), type(r)",
}

class Taint:
    def __init__(self, tg): self.g = tg.g
    def q(self, k, **p): return self.g.query(Q[k], p).result_set
    def agent(self, name, role=""): self.q("agent", name=name, role=role)
    def source(self, id, title, text): self.q("source", id=id, title=title, text=text)
    def claim(self, agent, text, value, sources=(), quote="", id=None):
        id = id or _id("c")
        self.q("claim" if sources else "claim_nosrc", agent=agent, id=id, text=text, value=str(value), sources=list(sources), quote=quote, ts=time.time())
        return id
    def artifact(self, agent, id, kind, title, derived_from=(), url=None, reach=0, owner=None):
        self.q("artifact", agent=agent, id=id, kind=kind, title=title, url=url, reach=int(reach), owner=owner or agent)
        for p in derived_from: self.q("derive", child=id, parent=p)
        return id
    def receipts(self):
        """QA pass: each claim's number must literally appear in its cited quote AND the quote in the source."""
        out = []
        for cid, text, value, agent, sid, stext, quote in self.q("receipts"):
            if sid is None: why = "no source cited"
            elif quote and quote not in (stext or ""): why = f"quote not found in {sid}"
            elif value not in NUM.findall(quote or stext or ""): why = f"said {value}, source says {', '.join(NUM.findall(quote or stext)) or 'nothing numeric'}"
            else: continue
            self.q("flag", id=cid, status="refuted", reason=why); out.append(dict(claim=cid, agent=agent, text=text, reason=why))
        return out
    def correct(self, claim, value, reason):
        return [dict(id=r[0], kind=r[1], title=r[2], hops=r[3]) for r in self.q("correct", id=claim, value=str(value), reason=reason)]
    def cascade_refuted(self):
        """Taint everything downstream of every refuted claim."""
        hit = {}
        for (cid,) in self.g.query("MATCH (c:Claim {status:'refuted'}) RETURN c.id").result_set:
            for r in self.g.query("""MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(:Claim {id:$id}) SET x.status='tainted'
                RETURN DISTINCT x.id, length(p)""", {"id": cid}).result_set: hit[r[0]] = r[1]
        return hit
    def recall(self):
        """Recall plan for published content: tainted artifacts, most-viewed first, with owner, live URL and est. reach."""
        rows = [dict(id=r[0], kind=r[1], title=r[2], reach=r[3], url=r[4], owner=r[5], agent=r[6]) for r in self.q("recall")]
        return dict(items=rows, total_reach=sum(r["reach"] for r in rows), live_urls=sum(1 for r in rows if r["url"]))
    def requeue(self): return self.q("requeue")
    def why(self, artifact): return [dict(path=r[0], reason=r[1], source=r[2], quote=r[3]) for r in self.q("why_tainted", id=artifact)]
    def trust(self): return [dict(agent=r[0], claims=r[1], bad=r[2], trust=round(r[3], 2)) for r in self.q("trust")]
    def snapshot(self):
        return dict(nodes=[dict(id=r[0], label=r[1], name=r[2], status=r[3]) for r in self.q("nodes")],
                    edges=[dict(source=r[0], target=r[1], type=r[2]) for r in self.q("edges")])

def connect(name="taint"): return Taint(_connect(name))
