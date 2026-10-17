import { Falkor } from "./falkor.js";
import { Q } from "./queries.js";
import { TOOLS, rpc, receipts } from "./tools.js";
import { runAgent } from "./agent.js";
// Public demo sandbox graph (synthetic, shared, reset often). Override with the DEMO_GRAPH var; never point it at agent memory.
let G = "taint_demo";
const NUM = /\d+(?:\.\d+)?/g;
async function seed(db) {
  const q = (k, p) => db.query(G, Q[k], p), now = Date.now() / 1000;
  await db.query(G, "MATCH (n) DETACH DELETE n");
  for (const [name, role] of [["Scout","researcher"],["Quill","writer"],["Reel","video"],["Lens","QA"]]) await q("agent", { name, role });
  await q("source", { id: "spec", title: "Acme Notes spec sheet (synthetic)", text: "Battery life: 3.5 hours of recording. Price: $29 per month. Supports 12 languages." });
  await q("source", { id: "pricing", title: "Pricing page v2 (synthetic)", text: "Starter plan $29/month. Pro plan $59/month." });
  const claim = (agent, id, text, value, sources, quote) =>
    q(sources.length ? "claim" : "claim_nosrc", { agent, id, text, value, sources, quote, ts: now });
  await claim("Scout", "c-battery", "Records for 35 hours on one charge", "35", ["spec"], "Battery life: 3.5 hours");
  await claim("Scout", "c-price", "Starts at $29/month", "29", ["pricing"], "Starter plan $29/month");
  await claim("Scout", "c-lang", "Supports 12 languages", "12", ["spec"], "Supports 12 languages");
  await claim("Quill", "c-users", "Trusted by 10000 teams", "10000", [], "");
  // [agent, id, kind, title, derived_from, url, est. reach]  (mirrors teamgraph/demo_seed.py; reach is synthetic)
  const arts = [["Quill","brief","brief","Launch brief",["c-battery","c-price","c-lang"],null,0],["Quill","blog","blog","Launch blog post",["brief","c-users"],"https://acme.example/blog/launch",4200],
    ["Quill","landing","page","Landing page hero",["brief"],"https://acme.example/",18500],["Quill","og","image","Link preview image",["landing"],"https://acme.example/og.png",9300],
    ["Reel","script","script","30s Short script",["blog"],null,0],["Reel","short","video","YouTube Short",["script"],"https://youtube.example/shorts/acme",27400],
    ["Reel","captions","captions","Short captions",["script"],null,0],["Quill","x1","post","X launch post",["blog"],"https://x.example/acme/1",12100],
    ["Quill","x2","post","X reply thread",["x1"],"https://x.example/acme/2",1800],["Quill","email","email","Waitlist email",["landing","c-price"],null,6400],
    ["Quill","faq","page","FAQ page",["c-lang","c-price"],"https://acme.example/faq",2100]];
  for (const [agent, id, kind, title, from, url, reach] of arts) { await q("artifact", { agent, id, kind, title, url, reach, owner: agent }); for (const parent of from) await q("derive", { child: id, parent }); }
  return { ok: 1 };
}
async function snapshot(db) {
  return { nodes: (await db.query(G, Q.nodes)).map(r => ({ id: r[0], label: r[1], name: r[2], status: r[3], key: r[4] })),
           edges: (await db.query(G, Q.edges)).map(r => ({ source: r[0], target: r[1], type: r[2] })) };
}
const T = (name, args) => async (db, b) => TOOLS[name].f(db, G, args ? args(b) : b);
const A = {
  reset: seed, receipts: db => receipts(db, G),
  correct: T("correct_claim", b => ({ claim: b.claim || "c-battery", value: b.value || "3.5", reason: b.reason || "decimal dropped" })),
  requeue: T("requeue_tainted"), recall: T("recall_plan"), trust: T("trust_ledger"),
  risk: T("claim_risk"), chokepoints: T("chokepoints", b => ({ k: b.k || 5 })),
  why: T("why_shortest", b => ({ artifact: b.artifact || "short" })),
  why_all: T("why_tainted", b => ({ artifact: b.artifact || "short" })),
  briefing: T("start_session", b => ({ agent: b.agent || "Reel" })),
  agent: (db, b, env) => runAgent(db, G, env, "recall", b.correction ? String(b.correction).slice(0, 300) : undefined),
  session: (db, b, env) => runAgent(db, G, env, "session", ["Reel", "Quill", "Scout", "Lens"].includes(b.agent) ? b.agent : "Reel"),
};
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    G = env.DEMO_GRAPH || "taint_demo";
    if (!url.pathname.startsWith("/api/") && url.pathname !== "/mcp") return env.ASSETS.fetch(req);
    if (!env.FALKORDB_URL) return Response.json({ error: "FALKORDB_URL secret not set" }, { status: 503 });
    const db = new Falkor(env.FALKORDB_URL);
    try {
      await db.open();
      if (url.pathname === "/mcp") {
        if (req.method !== "POST") return Response.json({ info: "Taint + Receipts MCP server (stateless JSON-RPC 2.0 over HTTP POST). Shared sandbox demo graph; synthetic data.", tools: Object.keys(TOOLS) });
        const msg = await req.json().catch(() => ({}));
        const out = Array.isArray(msg) ? (await Promise.all(msg.map(m => rpc(db, G, m)))).filter(Boolean) : await rpc(db, G, msg);
        return out ? Response.json(out) : new Response(null, { status: 202 });
      }
      const name = url.pathname.slice(5);
      if (req.method === "GET" && name === "graph") {
        if ((await db.query(G, "MATCH (n) RETURN count(n)").catch(() => [[0]]))[0][0] == 0) await seed(db);
        return Response.json(await snapshot(db));
      }
      const f = A[name]; if (!f || req.method !== "POST") return Response.json({ error: "not found" }, { status: 404 });
      const body = await req.json().catch(() => ({}));
      const result = await f(db, body, env);
      return Response.json({ result, graph: await snapshot(db) });
    } catch (e) { return Response.json({ error: String(e.message || e) }, { status: 500 }); }
    finally { db.close(); }
  },
};
