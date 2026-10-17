// Unit checks for the hardening. Bundled with esbuild (see package.json "test").
import assert from "node:assert";
import { guard } from "../src/agent.js";
import { rpc, TOOLS } from "../src/tools.js";
import worker, { PUBLIC_MCP } from "../src/index.js";
import { withParams, lit } from "../src/falkor.js";

// Cypher literals: quotes/backslashes can't break out; non-finite numbers become null; param names are validated.
assert.equal(lit('a"}) MATCH (n) DETACH DELETE n //'), '"a\\"}) MATCH (n) DETACH DELETE n //"');
assert.equal(lit("x\\\"y"), '"x\\\\\\"y"');
assert.equal(lit(NaN), "null");
assert.throws(() => withParams("RETURN 1", { "a=1 MATCH (n) DELETE n //": 1 }), /bad param name/);

// Agent scoping
assert.ok(guard("session", "Reel", "correct_claim", {}).error);                       // not a session tool
assert.ok(guard("session", "Reel", "hand_off", { from_agent: "Quill", to_agent: "Reel", task: "t", note: "" }).error);
assert.ok(guard("session", "Reel", "start_session", { agent: "Quill" }).error);
assert.equal(guard("session", "Reel", "complete_task", { task: "redo-short" }), null);
assert.ok(guard("recall", "x", "hand_off", {}).error);
assert.ok(guard("recall", "x", "remember_episode", { agent: "Reel", text: "x" }).error);

// Public MCP is read-only
for (const t of PUBLIC_MCP) assert.ok(TOOLS[t], t);
for (const w of ["correct_claim", "requeue_tainted", "draft_recall_memo", "remember_episode", "hand_off", "complete_task", "check_receipts"]) assert.ok(!PUBLIC_MCP.includes(w), w);

// rpc: every query goes through parameters; hostile args never appear in the Cypher text
const seen = []; const db = { query: async (g, q, p) => { seen.push({ g, q, p }); return [["Reel"]]; } };
const evil = "x'}) MATCH (n) DETACH DELETE n //";
await rpc(db, "taint_demo", { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "why_shortest", arguments: { artifact: evil } } });
await rpc(db, "taint_demo", { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "complete_task", arguments: { task: evil } } });
assert.ok(seen.length >= 2 && seen.every(s => s.g === "taint_demo" && !s.q.includes(evil)));
const list = await rpc(db, "g", { jsonrpc: "2.0", id: 3, method: "tools/list" }); assert.ok(list.result.tools.length >= 10);

// Handler: JSON-only POSTs, body size cap, generic errors, security headers (no DB needed for these paths)
const env = { FALKORDB_URL: "redis://127.0.0.1:1", ASSETS: { fetch: () => new Response("asset") } };
const post = (path, body, ct = "application/json") => worker.fetch(new Request("https://x.test" + path, { method: "POST", headers: { "content-type": ct }, body }), env);
let r = await post("/api/reset", "{}", "text/plain"); assert.equal(r.status, 415);
r = await post("/api/agent", JSON.stringify({ correction: "a".repeat(5000) })); assert.equal(r.status, 413);
r = await post("/api/correct", "{not json"); assert.equal(r.status, 400);
r = await post("/api/recall", "{}"); assert.equal(r.status, 500); const j = await r.json();
assert.equal(j.error, "internal error"); assert.equal(r.headers.get("x-content-type-options"), "nosniff");
r = await worker.fetch(new Request("https://x.test/api/graph"), { ASSETS: env.ASSETS }); assert.equal(r.status, 503); assert.ok(!(await r.text()).includes("FALKORDB_URL"));
const rlEnv = { ...env, RL_API: { limit: async () => ({ success: false }) } };
r = await worker.fetch(new Request("https://x.test/api/graph"), rlEnv); assert.equal(r.status, 429);
console.log("security ok");
