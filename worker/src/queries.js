// generated from teamgraph/taint.py and teamgraph/graph.py (memory)
export const Q = {
 "agent": "MERGE (a:Agent {name:$name}) ON CREATE SET a.role=$role, a.verified=0, a.refuted=0",
 "source": "MERGE (s:Source {id:$id}) SET s.title=$title, s.text=$text",
 "claim": "MATCH (a:Agent {name:$agent}) CREATE (c:Claim {id:$id, text:$text, value:$value, status:'ok', ts:$ts})\n   CREATE (a)-[:ASSERTED]->(c)\n   WITH c UNWIND $sources AS sid MATCH (s:Source {id:sid}) CREATE (c)-[:CITES {quote:$quote}]->(s) RETURN DISTINCT c.id",
 "claim_nosrc": "MATCH (a:Agent {name:$agent}) CREATE (c:Claim {id:$id, text:$text, value:$value, status:'ok', ts:$ts})\n   CREATE (a)-[:ASSERTED]->(c) RETURN c.id",
 "artifact": "MATCH (a:Agent {name:$agent}) MERGE (x:Artifact {id:$id}) SET x.kind=$kind, x.title=$title, x.status='live',\n   x.url=$url, x.reach=$reach, x.owner=$owner\n   MERGE (a)-[:PRODUCED]->(x)",
 "recall": "MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)\n   RETURN x.id, x.kind, x.title, coalesce(x.reach,0), x.url, coalesce(x.owner, a.name), a.name\n   ORDER BY coalesce(x.reach,0) DESC, x.id",
 "derive": "MATCH (x {id:$child}), (y {id:$parent}) MERGE (x)-[:DERIVED_FROM]->(y)",
 "receipts": "MATCH (a:Agent)-[:ASSERTED]->(c:Claim) WHERE c.status='ok'\n   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)\n   RETURN c.id, c.text, c.value, a.name, s.id, s.text, r.quote",
 "flag": "MATCH (c:Claim {id:$id}) SET c.status=$status, c.reason=$reason",
 "correct": "MATCH (bad:Claim {id:$id}) SET bad.status='corrected', bad.fixed_value=$value, bad.reason=$reason\n   WITH bad MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(bad)\n   SET x.status='tainted' RETURN DISTINCT x.id, x.kind, x.title, length(p) ORDER BY length(p)",
 "requeue": "MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)\n   MERGE (t:Task {id:'redo-' + x.id}) ON CREATE SET t.artifact=x.id, t.status='open', t.title='Redo ' + x.title\n   WITH x, a, t OPTIONAL MATCH (t)<-[:OWNS]-(o:Agent)\n   WITH x, a, t, count(o) AS owners\n   FOREACH (_ IN CASE WHEN owners = 0 THEN [1] ELSE [] END | MERGE (a)-[:OWNS]->(t))\n   RETURN a.name, x.title, t.id ORDER BY t.id",
 "why_tainted": "MATCH p=(x:Artifact {id:$id})-[:DERIVED_FROM*1..10]->(c:Claim) WHERE c.status IN ['corrected','refuted']\n   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)\n   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], c.reason, s.title, r.quote",
 "risk": "CALL algo.pageRank(NULL, 'DERIVED_FROM') YIELD node, score\n   WITH node, score WHERE node:Claim\n   OPTIONAL MATCH (x:Artifact)-[:DERIVED_FROM*1..10]->(node)\n   WITH node, score, collect(DISTINCT x) AS xs\n   RETURN node.id, node.text, node.status, score, size(xs), reduce(s = 0, a IN xs | s + coalesce(a.reach, 0)) AS exposed\n   ORDER BY exposed DESC, score DESC",
 "chokepoints": "CALL algo.betweenness({relationshipTypes: ['DERIVED_FROM']}) YIELD node, score\n   WITH node, score WHERE node:Artifact AND score > 0\n   RETURN node.id, node.title, node.status, score ORDER BY score DESC LIMIT $lim",
 "why_shortest": "MATCH (x:Artifact {id:$id}), (c:Claim) WHERE c.status IN ['corrected','refuted']\n   WITH x, c, shortestPath((x)-[:DERIVED_FROM*1..10]->(c)) AS p WHERE p IS NOT NULL\n   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)\n   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], [n IN nodes(p) | n.id], c.reason, s.title, r.quote, length(p) ORDER BY length(p)",
 "trust": "MATCH (a:Agent) OPTIONAL MATCH (a)-[:ASSERTED]->(c:Claim)\n   WITH a, count(c) AS total, sum(CASE WHEN c.status IN ['refuted','corrected'] THEN 1 ELSE 0 END) AS bad\n   RETURN a.name, total, bad, CASE WHEN total=0 THEN null ELSE toFloat(total-bad)/total END AS trust ORDER BY trust DESC",
 "nodes": "MATCH (n) RETURN id(n), labels(n)[0], coalesce(n.title, n.text, n.name, n.id), coalesce(n.status,''), coalesce(n.id, n.name)",
 "edges": "MATCH (a)-[r]->(b) RETURN id(a), id(b), type(r)"
};
export const M = {
 "episode": "MATCH (a:Agent {name:$agent}) CREATE (e:Episode {id:$id, text:$text, session:$session, ts:$ts})\n   CREATE (a)-[:EXPERIENCED]->(e)\n   WITH e OPTIONAL MATCH (t:Task {id:$task}) FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (e)-[:ABOUT]->(t)) RETURN e.id",
 "handoff": "MATCH (f:Agent {name:$from_agent})-[o:OWNS]->(t:Task {id:$task}) MATCH (to:Agent {name:$to_agent})\n   DELETE o CREATE (to)-[:OWNS]->(t)\n   CREATE (h:Handoff {id:$id, note:$note, ts:$ts}) CREATE (f)-[:GAVE]->(h)-[:TO]->(to) CREATE (h)-[:FOR]->(t) RETURN h.id",
 "briefing": "MATCH (a:Agent {name:$agent})-[:OWNS]->(t:Task) WHERE t.status <> 'done'\n   OPTIONAL MATCH (h:Handoff)-[:FOR]->(t) OPTIONAL MATCH (g:Agent)-[:GAVE]->(h)\n   WITH t, h, g ORDER BY h.ts DESC WITH t, collect({from:g.name, note:h.note})[0] AS last\n   RETURN t.id, t.title, t.status, last.from, last.note",
 "done": "MATCH (t:Task {id:$id}) SET t.status='done' RETURN t.id",
 "memo": "MATCH (a:Agent {name:$owner}) CREATE (m:Memo {id:$id, text:$text, author:$author, ts:$ts}) CREATE (a)-[:RECEIVED]->(m)\n   WITH a, m OPTIONAL MATCH (a)-[:OWNS]->(t:Task) WHERE t.status <> 'done'\n   FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (m)-[:COVERS]->(t)) RETURN DISTINCT m.id",
 "memos_for": "MATCH (a:Agent {name:$agent})-[:RECEIVED]->(m:Memo) RETURN m.author, m.text, m.ts ORDER BY m.ts DESC LIMIT 3",
 "episodes_for": "MATCH (a:Agent {name:$agent})-[:EXPERIENCED]->(e:Episode) RETURN e.session, e.text, e.ts ORDER BY e.ts DESC LIMIT 5",
 "recall": "MATCH (a:Agent)-[:EXPERIENCED]->(e:Episode) WHERE toLower(e.text) CONTAINS toLower($q)\n   RETURN 'episode' AS kind, a.name AS who, e.text AS text, e.ts AS ts ORDER BY ts DESC LIMIT $k\n   UNION MATCH (c:Concept)-[:SUBJECT_OF]->(f:Fact)-[:OBJECT]->(o:Concept)\n   WHERE toLower(c.name) CONTAINS toLower($q) OR toLower(o.name) CONTAINS toLower($q)\n   RETURN 'fact' AS kind, c.name AS who, f.predicate + ' ' + o.name AS text, f.ts AS ts ORDER BY ts DESC LIMIT $k",
 "last_giver": "MATCH (g:Agent)-[:GAVE]->(h:Handoff)-[:FOR]->(:Task {id:$task}) RETURN g.name ORDER BY h.ts DESC LIMIT 1"
};
