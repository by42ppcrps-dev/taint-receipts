"""Taint + Receipts: provenance and correction propagation for published content, on FalkorDB."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterable
from typing import Any

from .cypher import register, run
from .graph import TeamGraph
from .graph import connect as _connect


def _id(p: str) -> str:
    return f"{p}-{uuid.uuid4().hex[:6]}"


NUM = re.compile(r"\d+(?:\.\d+)?")

Q = register(
    {
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
        # Taint: correcting a claim taints every artifact reachable via DERIVED_FROM, up to 10 hops (the *1..10 bound)
        "correct": """MATCH (bad:Claim {id:$id}) SET bad.status='corrected', bad.fixed_value=$value, bad.reason=$reason
   WITH bad MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(bad)
   SET x.status='tainted' RETURN DISTINCT x.id, x.kind, x.title, length(p) ORDER BY length(p)""",
        # Requeue: one redo Task per tainted artifact with a STABLE id 'redo-<artifact id>' (what briefing,
        # hand_off and complete_task use). Re-running is idempotent and never re-adds the producer as owner
        # of a task that was already handed off.
        "requeue": """MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
   MERGE (t:Task {id:'redo-' + x.id}) ON CREATE SET t.artifact=x.id, t.status='open', t.title='Redo ' + x.title
   WITH x, a, t OPTIONAL MATCH (t)<-[:OWNS]-(o:Agent)
   WITH x, a, t, count(o) AS owners
   FOREACH (_ IN CASE WHEN owners = 0 THEN [1] ELSE [] END | MERGE (a)-[:OWNS]->(t))
   RETURN a.name, x.title, t.id ORDER BY t.id""",
        "why_tainted": """MATCH p=(x:Artifact {id:$id})-[:DERIVED_FROM*1..10]->(c:Claim) WHERE c.status IN ['corrected','refuted']
   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)
   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], c.reason, s.title, r.quote""",
        # Graph algorithms as agent tools.
        # Risk: PageRank over DERIVED_FROM (edges point child -> parent, so rank flows to the claims everything is built on),
        # combined with the published audience downstream of each claim. High score = most load-bearing claim to audit first.
        "risk": """CALL algo.pageRank(NULL, 'DERIVED_FROM') YIELD node, score
   WITH node, score WHERE node:Claim
   OPTIONAL MATCH (x:Artifact)-[:DERIVED_FROM*1..10]->(node)
   WITH node, score, collect(DISTINCT x) AS xs
   RETURN node.id, node.text, node.status, score, size(xs), reduce(s = 0, a IN xs | s + coalesce(a.reach, 0)) AS exposed
   ORDER BY exposed DESC, score DESC""",
        # Chokepoints: betweenness centrality on the provenance graph. Artifacts many dependency paths run through.
        "chokepoints": """CALL algo.betweenness({relationshipTypes: ['DERIVED_FROM']}) YIELD node, score
   WITH node, score WHERE node:Artifact AND score > 0
   RETURN node.id, node.title, node.status, score ORDER BY score DESC LIMIT $lim""",
        # Why (shortest): the shortest DERIVED_FROM path from an artifact to each bad claim, plus the source quote.
        "why_shortest": """MATCH (x:Artifact {id:$id}), (c:Claim) WHERE c.status IN ['corrected','refuted']
   WITH x, c, shortestPath((x)-[:DERIVED_FROM*1..10]->(c)) AS p WHERE p IS NOT NULL
   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)
   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], [n IN nodes(p) | n.id], c.reason, s.title, r.quote, length(p) ORDER BY length(p)""",
        "trust": """MATCH (a:Agent) OPTIONAL MATCH (a)-[:ASSERTED]->(c:Claim)
   WITH a, count(c) AS total, sum(CASE WHEN c.status IN ['refuted','corrected'] THEN 1 ELSE 0 END) AS bad
   RETURN a.name, total, bad, CASE WHEN total=0 THEN null ELSE toFloat(total-bad)/total END AS trust ORDER BY trust DESC""",
        "nodes": "MATCH (n) RETURN id(n), labels(n)[0], coalesce(n.title, n.text, n.name, n.id), coalesce(n.status,''), coalesce(n.id, n.name)",
        "edges": "MATCH (a)-[r]->(b) RETURN id(a), id(b), type(r)",
        "wipe": "MATCH (n) DETACH DELETE n",
        "refuted_ids": "MATCH (c:Claim {status:'refuted'}) RETURN c.id",
        "cascade_one": """MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(:Claim {id:$id}) SET x.status='tainted'
   RETURN DISTINCT x.id, length(p)""",
        # Quote first: a number elsewhere in the source document is not a receipt for this claim.
        "claim_quotes": """MATCH (c:Claim {id:$id}) OPTIONAL MATCH (c)-[r:CITES]->(s:Source) RETURN r.quote, s.text""",
    }
)

Row = dict[str, Any]


class Taint:
    def __init__(self, tg: TeamGraph) -> None:
        self.g = tg.g

    def q(self, k: str, **p: Any) -> list[list[Any]]:
        return run(self.g, Q[k], p)

    def wipe(self) -> None:
        self.q("wipe")

    def agent(self, name: str, role: str = "") -> None:
        self.q("agent", name=name, role=role)

    def source(self, id: str, title: str, text: str) -> None:
        self.q("source", id=id, title=title, text=text)

    def claim(self, agent: str, text: str, value: str | float, sources: Iterable[str] = (), quote: str = "", id: str | None = None) -> str:
        cid = id or _id("c")
        srcs = list(sources)
        self.q("claim" if srcs else "claim_nosrc", agent=agent, id=cid, text=text, value=str(value), sources=srcs, quote=quote, ts=time.time())
        return cid

    def artifact(
        self,
        agent: str,
        id: str,
        kind: str,
        title: str,
        derived_from: Iterable[str] = (),
        url: str | None = None,
        reach: int = 0,
        owner: str | None = None,
    ) -> str:
        self.q("artifact", agent=agent, id=id, kind=kind, title=title, url=url, reach=int(reach), owner=owner or agent)
        for parent in derived_from:
            self.q("derive", child=id, parent=parent)
        return id

    def receipts(self) -> list[Row]:
        """QA pass: each claim's number must literally appear in its cited quote AND the quote in the source."""
        out: list[Row] = []
        for cid, text, value, agent, sid, stext, quote in self.q("receipts"):
            if sid is None:
                why = "no source cited"
            elif quote and quote not in (stext or ""):
                why = f"quote not found in {sid}"
            elif value not in NUM.findall(quote or stext or ""):
                why = f"said {value}, source says {', '.join(NUM.findall(quote or stext)) or 'nothing numeric'}"
            else:
                continue
            self.q("flag", id=cid, status="refuted", reason=why)
            out.append({"claim": cid, "agent": agent, "text": text, "reason": why})
        return out

    def correct(self, claim: str, value: str | float, reason: str) -> list[Row]:
        """Refuse a new value that is not a number in this claim's cited quote (the source body is not enough)."""
        quotes = self.q("claim_quotes", id=claim)
        if quotes:
            nums: list[str] = []
            for quote, text in quotes:
                nums.extend(NUM.findall(quote or text or ""))
            if str(value).strip() not in nums:
                raise ValueError(f"refused: no cited quote for claim {claim} contains the value {value}")
        return [{"id": r[0], "kind": r[1], "title": r[2], "hops": r[3]} for r in self.q("correct", id=claim, value=str(value).strip(), reason=reason)]

    def cascade_refuted(self) -> dict[str, int]:
        """Taint everything downstream of every refuted claim."""
        hit: dict[str, int] = {}
        for (cid,) in self.q("refuted_ids"):
            for r in self.q("cascade_one", id=cid):
                hit[r[0]] = r[1]
        return hit

    def recall(self) -> Row:
        """Recall plan for published content: tainted artifacts, most-viewed first, with owner, live URL and est. reach."""
        rows = [{"id": r[0], "kind": r[1], "title": r[2], "reach": r[3], "url": r[4], "owner": r[5], "agent": r[6]} for r in self.q("recall")]
        return {"items": rows, "total_reach": sum(r["reach"] for r in rows), "live_urls": sum(1 for r in rows if r["url"])}

    def requeue(self) -> list[Row]:
        return [{"agent": r[0], "title": r[1], "task": r[2]} for r in self.q("requeue")]

    def why(self, artifact: str) -> list[Row]:
        return [{"path": r[0], "reason": r[1], "source": r[2], "quote": r[3]} for r in self.q("why_tainted", id=artifact)]

    def risk(self) -> list[Row]:
        """PageRank + downstream published reach per claim: which claims are most load-bearing."""
        return [{"claim": r[0], "text": r[1], "status": r[2], "pagerank": round(r[3], 4), "downstream": r[4], "exposed_reach": r[5]} for r in self.q("risk")]

    def chokepoints(self, k: int = 5) -> list[Row]:
        """Betweenness centrality: artifacts that the most dependency paths run through."""
        return [{"id": r[0], "title": r[1], "status": r[2], "betweenness": r[3]} for r in self.q("chokepoints", lim=k)]

    def why_shortest(self, artifact: str) -> list[Row]:
        """Shortest DERIVED_FROM path from an artifact to each corrected/refuted claim, with the source quote."""
        return [{"path": r[0], "ids": r[1], "reason": r[2], "source": r[3], "quote": r[4], "hops": r[5]} for r in self.q("why_shortest", id=artifact)]

    def trust(self) -> list[Row]:
        return [{"agent": r[0], "claims": r[1], "bad": r[2], "trust": ("unrated" if r[3] is None else round(r[3], 2))} for r in self.q("trust")]

    def snapshot(self) -> Row:
        return {
            "nodes": [{"id": r[0], "label": r[1], "name": r[2], "status": r[3], "key": r[4]} for r in self.q("nodes")],
            "edges": [{"source": r[0], "target": r[1], "type": r[2]} for r in self.q("edges")],
        }


def connect(name: str | None = None) -> Taint:
    """Taint view over a graph. Default: $TEAMGRAPH_GRAPH or 'teamgraph', the same graph the MCP memory tools use."""
    return Taint(_connect(name))
