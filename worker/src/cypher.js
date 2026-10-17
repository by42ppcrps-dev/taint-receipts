// The ONLY place the Worker sends Cypher (enforced by test/invariants.test.mjs): every query is a registered
// constant (teamgraph/*.py via queries.js, plus the Worker-only ones below) and every value is a parameter.
import { Q, M } from "./queries.js";
// FalkorDB's verbose RESP mode returns lists as strings, so list-valued columns are joined in Cypher and split by callers.
export const SEP = "|~|";
const join = e => `reduce(s='', n IN nodes(p) | s + ${e} + '${SEP}')`;
const W = {
 "count_all": "MATCH (n) RETURN count(n)",
 "room": "MATCH (n) WHERE n:Memo OR n:Episode OR n:Handoff RETURN count(n)",
 "cooldown": "MERGE (c:Cooldown {id:$k}) ON CREATE SET c.t=0 WITH c, c.t AS prev SET c.t = CASE WHEN $t - prev > $s THEN $t ELSE prev END RETURN prev",
 "claim_sources": "MATCH (c:Claim {id:$id})-[:CITES]->(s:Source) RETURN s.text",
 "budget_get": "MERGE (b:Budget {id:'llm'}) ON CREATE SET b.usd=0.0, b.runs=0, b.last=0 RETURN b.usd, b.runs, b.last",
 "budget_start": "MATCH (b:Budget {id:'llm'}) SET b.last=$t, b.runs=b.runs+1",
 "budget_add": "MATCH (b:Budget {id:'llm'}) SET b.usd=b.usd+$u"
};
const REG = new Map([
  ...Object.entries(Q),
  ...Object.entries(M).map(([k, v]) => ["m_" + k, v]),
  ...Object.entries(W),
  ["why_shortest_flat", Q.why_shortest.replace("[n IN nodes(p) | coalesce(n.title, n.text)]", join("coalesce(n.title, n.text)")).replace("[n IN nodes(p) | n.id]", join("n.id"))],
  ["why_tainted_flat", Q.why_tainted.replace("[n IN nodes(p) | coalesce(n.title, n.text)]", join("coalesce(n.title, n.text)"))],
]);
export const QUERY_KEYS = [...REG.keys()];
export function run(db, graph, key, params) {
  const q = REG.get(key);
  if (q === undefined) throw new Error(`unregistered query ${key}`);
  return db.query(graph, q, params);
}
