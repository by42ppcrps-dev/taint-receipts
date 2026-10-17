import { Falkor } from "./falkor.js";
import { run } from "./cypher.js";
import { TOOLS, rpc, receipts, Refusal } from "./tools.js";
import { runAgent, redact } from "./agent.js";
// Public demo sandbox graph (synthetic, shared, reset often). Override with the DEMO_GRAPH var; never point it at agent memory.
let G = "taint_demo";
const NUM = /\d+(?:\.\d+)?/g;
async function seed(db) {
  const q = (k, p) => run(db, G, k, p), now = Date.now() / 1000;
  await run(db, G, "wipe");
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
  await run(db, "taint_meta", "cap_reset");
  return { ok: 1 };
}
async function snapshot(db) {
  return { nodes: (await run(db, G, "nodes")).map(r => ({ id: r[0], label: r[1], name: r[2], status: r[3], key: r[4] })),
           edges: (await run(db, G, "edges")).map(r => ({ source: r[0], target: r[1], type: r[2] })) };
}
const T = (name, args) => async (db, b) => TOOLS[name].f(db, G, args ? args(b) : b);
const A = {
  reset: seed, receipts: db => receipts(db, G),
  correct: T("correct_claim", b => ({ claim: b.claim || "c-battery", value: b.value || "3.5", reason: b.reason || "decimal dropped" })),
  requeue: T("requeue_tainted"), recall: T("recall_plan"), trust: T("trust_ledger"),
  risk: T("claim_risk"), chokepoints: T("chokepoints", b => ({ k: Math.min(10, Math.max(1, Math.trunc(Number(b.k)) || 5)) })),
  why: T("why_shortest", b => ({ artifact: b.artifact || "short" })),
  why_all: T("why_tainted", b => ({ artifact: b.artifact || "short" })),
  briefing: T("start_session", b => ({ agent: b.agent || "Reel" })),
  agent: (db, b, env) => runAgent(db, G, env, "recall", b.correction ? String(b.correction).slice(0, 300) : undefined),
  session: (db, b, env) => runAgent(db, G, env, "session", ["Reel", "Quill", "Scout", "Lens"].includes(b.agent) ? b.agent : "Reel"),
};
// ---- hardening (see docs/SECURITY-REVIEW.md) ----
const MAX_BODY = 4096;
const SEC = { "x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "x-frame-options": "DENY", "cache-control": "no-store",
  "content-security-policy": "default-src 'none'; frame-ancestors 'none'" };
const J = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json", ...SEC } });
// Read-only tools exposed to anonymous MCP clients. Writes happen only through the rate-limited /api routes.
export const PUBLIC_MCP = ["claim_risk", "chokepoints", "recall_plan", "why_shortest", "why_tainted", "trust_ledger", "start_session", "recall"];
const WRITES = new Set(["reset", "receipts", "correct", "requeue", "agent", "session"]);
async function cooldown(db, key, secs, now = Date.now() / 1000) {  // global cooldown kept in the meta graph (Reset never touches it)
  const r = await run(db, "taint_meta", "cooldown", { k: key, t: now, s: secs });
  return now - Number(r[0][0]) <= secs;
}
async function readBody(req) {
  const code = badLength(req.headers.get("content-length")); if (code) throw new Error(String(code));
  const txt = await req.text(); if (txt.length > MAX_BODY) throw new Error("413");
  if (!txt) return {};
  const v = JSON.parse(txt); if (typeof v !== "object" || v === null) throw new Error("400"); return v;
}
const clip = (v, n = 200) => (v == null ? undefined : String(v).slice(0, n));
// Only the edge-set CF-Connecting-IP. X-Forwarded-For and any client visitor id are not a rate-limit key.
export function clientIp(req) {
  const raw = (req.headers.get("cf-connecting-ip") || "").trim();
  if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(raw) && raw.split(".").every(n => Number(n) <= 255)) return raw;
  if (/^[0-9a-fA-F:]{2,39}$/.test(raw) && raw.includes(":") && !raw.includes(":::")) return raw.toLowerCase();
  return "anon";
}
// Only an actual zero count seeds. A failed or malformed count must not look empty: seed() wipes the graph.
export function graphIsEmpty(rows) {
  const n = rows && rows[0] && rows[0][0];
  return n === 0 || n === "0";
}
export function badLength(header) {
  const len = Number(header || 0);
  if (!Number.isFinite(len) || len < 0) return 400;
  if (len > MAX_BODY) return 413;
  return 0;
}
// Missing binding (local tests) is unlimited. A failing limiter fails closed so it cannot be tripped into a bypass.
export async function rateLimited(env, binding, key) {
  if (!env[binding]) return false;
  try { return !(await env[binding].limit({ key })).success; }
  catch { return true; }
}
export async function writeGate(db, name, ip, now = Date.now() / 1000) {
  // Per-IP first. Checking the global reset slot first would burn it when this IP is already in its write cooldown.
  if (WRITES.has(name) && await cooldown(db, "w:" + ip, 1, now)) return "slow down";
  if (name === "reset" && await cooldown(db, "reset", 15, now)) return "the demo was just reset; try again in a few seconds";
  return null;
}
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    G = env.DEMO_GRAPH || "taint_demo";
    if (!url.pathname.startsWith("/api/") && url.pathname !== "/mcp") return env.ASSETS.fetch(req);
    if (!env.FALKORDB_URL) return J({ error: "demo database not configured" }, 503);
    const ip = clientIp(req), name = url.pathname === "/mcp" ? "mcp" : url.pathname.slice(5);
    if (await rateLimited(env, "RL_API", ip)) return J({ error: "rate limited, try again in a minute" }, 429);
    let body = {};
    if (req.method === "POST") {
      // JSON only: a cross-site form/text POST can't trigger writes (non-simple content type needs a CORS preflight, which we never grant).
      if (!(req.headers.get("content-type") || "").startsWith("application/json")) return J({ error: "content-type must be application/json" }, 415);
      try { body = await readBody(req); } catch (e) {
        if (e.message === "413") return J({ error: "request too large" }, 413);
        if (e.message === "400") return J({ error: "invalid request" }, 400);
        return J({ error: "invalid JSON" }, 400);
      }
    }
    if ((name === "agent" || name === "session") && await rateLimited(env, "RL_AGENT", ip)) return J({ error: "agent runs are limited to a few per minute per visitor" }, 429);
    const db = new Falkor(env.FALKORDB_URL);
    try {
      await db.open();
      if (name === "mcp") {
        if (req.method !== "POST") return J({ info: "Taint + Receipts MCP server (stateless JSON-RPC 2.0 over HTTP POST). Read-only tools on a shared sandbox demo graph; synthetic data.", tools: PUBLIC_MCP });
        const msgs = Array.isArray(body) ? body.slice(0, 10) : [body];
        const out = [];
        for (const m of msgs) {
          if (m && m.method === "tools/call" && !PUBLIC_MCP.includes(m.params?.name)) { out.push({ jsonrpc: "2.0", id: m.id ?? null, error: { code: -32601, message: "tool not available on the public endpoint" } }); continue; }
          let r = await rpc(db, G, m || {});
          if (r && m.method === "tools/list") r = { ...r, result: { tools: r.result.tools.filter(t => PUBLIC_MCP.includes(t.name)) } };
          if (r) out.push(r);
        }
        if (!out.length) return new Response(null, { status: 202, headers: SEC });
        return J(Array.isArray(body) ? out : out[0]);
      }
      if (req.method === "GET" && name === "graph") {
        if (graphIsEmpty(await run(db, G, "count_all"))) await seed(db);
        return J(await snapshot(db));
      }
      const f = A[name]; if (!f || req.method !== "POST") return J({ error: "not found" }, 404);
      const gate = await writeGate(db, name, ip); if (gate) return J({ error: gate }, 429);
      const b = { claim: clip(body.claim, 64), value: clip(body.value, 32), reason: clip(body.reason), artifact: clip(body.artifact, 64), agent: clip(body.agent, 16), correction: clip(body.correction, 300), k: Math.min(10, Math.max(1, Math.trunc(Number(body.k)) || 5)) };
      const result = await f(db, b, env);
      return J({ result, graph: await snapshot(db) });
    } catch (e) {
      if (e instanceof Refusal) return J({ error: e.message }, 400);
      console.log("error", name, redact(e && e.message || e, env.GEMINI_API_KEY, env.FALKORDB_URL));   // details stay in Worker logs; never echo internals
      return J({ error: "internal error" }, 500);
    }
    finally { db.close(); }
  },
};
