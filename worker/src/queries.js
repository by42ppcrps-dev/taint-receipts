// generated from teamgraph/taint.py
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
 "requeue": "MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)\n   MERGE (t:Task {artifact:x.id}) ON CREATE SET t.status='open', t.title='Redo '+x.title\n   MERGE (a)-[:OWNS]->(t) RETURN a.name, x.title",
 "why_tainted": "MATCH p=(x:Artifact {id:$id})-[:DERIVED_FROM*1..10]->(c:Claim) WHERE c.status IN ['corrected','refuted']\n   OPTIONAL MATCH (c)-[r:CITES]->(s:Source)\n   RETURN [n IN nodes(p) | coalesce(n.title, n.text)], c.reason, s.title, r.quote",
 "trust": "MATCH (a:Agent) OPTIONAL MATCH (a)-[:ASSERTED]->(c:Claim)\n   WITH a, count(c) AS total, sum(CASE WHEN c.status IN ['refuted','corrected'] THEN 1 ELSE 0 END) AS bad\n   RETURN a.name, total, bad, CASE WHEN total=0 THEN null ELSE toFloat(total-bad)/total END AS trust ORDER BY trust DESC",
 "nodes": "MATCH (n) RETURN id(n), labels(n)[0], coalesce(n.title, n.text, n.name, n.id), coalesce(n.status,'')",
 "edges": "MATCH (a)-[r]->(b) RETURN id(a), id(b), type(r)"
};
