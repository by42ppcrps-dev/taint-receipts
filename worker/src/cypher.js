// The ONLY place the Worker sends Cypher (enforced by test/invariants.test.mjs): every query is a registered
// constant (teamgraph/*.py via queries.js, plus the Worker-only ones below) and every value is a parameter.
import { Q, M } from "./queries.js";
// FalkorDB's verbose RESP mode returns lists as strings, so list-valued columns are joined in Cypher and split by callers.
export const SEP = "|~|";
const join = e => `reduce(s='', n IN nodes(p) | s + ${e} + '${SEP}')`;
// Budget times are integer milliseconds. One query both checks and takes the slot, so concurrent
// requests cannot all pass a check-then-act. `token` is stable for the run; `beat` is the heartbeat.
export const BUDGET_ACQUIRE = `MERGE (b:Budget {id:'llm'}) ON CREATE SET b.usd=0.0, b.runs=0, b.last=0, b.token=0, b.beat=0
WITH b, coalesce(b.usd,0) AS usd, coalesce(b.last,0) AS last, coalesce(b.beat,0) AS beat, coalesce(b.token,0) AS token
WITH b, usd, last, beat, token, CASE WHEN usd < $cap AND ($t - last) > $gap AND ($t - beat) > $lease THEN 1 ELSE 0 END AS ok
WITH b, usd, last, beat, token, ok, CASE WHEN usd >= $cap THEN 'cap' WHEN ($t - last) <= $gap THEN 'cooldown' WHEN ($t - beat) <= $lease THEN 'busy' ELSE 'ok' END AS why
SET b.token = CASE WHEN ok = 1 THEN $t ELSE token END, b.beat = CASE WHEN ok = 1 THEN $t ELSE beat END, b.last = CASE WHEN ok = 1 THEN $t ELSE last END, b.runs = coalesce(b.runs,0) + ok
RETURN ok, why, usd`;
export const BUDGET_TOUCH = "MATCH (b:Budget {id:'llm'}) WHERE b.token=$token SET b.beat=$t RETURN b.token";
export const BUDGET_FINISH = `MATCH (b:Budget {id:'llm'})
WITH b, CASE WHEN b.token=$token THEN 1 ELSE 0 END AS mine
SET b.usd=coalesce(b.usd,0) + CASE WHEN $u > 0 THEN $u ELSE 0 END, b.token=CASE WHEN mine=1 THEN 0 ELSE b.token END, b.beat=CASE WHEN mine=1 THEN 0 ELSE b.beat END, b.last=CASE WHEN coalesce(b.last,0) <= $t THEN $t ELSE b.last END
RETURN b.usd, b.token`;
// Admit one memo/episode/handoff. floor is the current graph count, so a fresh counter cannot reset the cap.
export const ADMIT = `MERGE (c:Counter {id:'writes'}) ON CREATE SET c.n=0
WITH c, CASE WHEN c.n < $floor THEN $floor ELSE c.n END AS base
WITH c, base WHERE base < 300
SET c.n = base + 1
RETURN c.n`;
export const CAP_RESET = "MERGE (c:Counter {id:'writes'}) SET c.n=0";
const W = {
 "count_all": "MATCH (n) RETURN count(n)",
 "room": "MATCH (n) WHERE n:Memo OR n:Episode OR n:Handoff RETURN count(n)",
 "cooldown": "MERGE (c:Cooldown {id:$k}) ON CREATE SET c.t=0 WITH c, c.t AS prev SET c.t = CASE WHEN $t - prev > $s THEN $t ELSE prev END RETURN prev",
 "claim_sources": "MATCH (c:Claim {id:$id})-[r:CITES]->(s:Source) RETURN r.quote, s.text",
 "owns": "MATCH (:Agent {name:$agent})-[:OWNS]->(t:Task {id:$task}) RETURN t.id",
 "task_open": "MATCH (:Agent {name:$agent})-[:OWNS]->(t:Task {id:$task}) WHERE coalesce(t.status,'open') <> 'done' RETURN t.id",
 "named_agent": "MATCH (a:Agent {name:$name}) RETURN a.name",
 "budget_acquire": BUDGET_ACQUIRE,
 "budget_touch": BUDGET_TOUCH,
 "budget_finish": BUDGET_FINISH,
 "admit": ADMIT,
 "cap_reset": CAP_RESET
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
