// MCP tool registry for the public Worker. The same tools are served to any MCP client at POST /mcp
// (JSON-RPC 2.0, stateless) and used by the in-Worker Gemini agent through the same rpc() handler.
import { run, SEP } from "./cypher.js";
const NUM = /\d+(?:\.\d+)?/g;
const S = (props = {}, req = []) => ({ type: "object", properties: props, required: req });
const str = d => ({ type: "string", description: d });
// FalkorDB's verbose RESP mode returns lists as strings, so list-valued columns are joined in Cypher and split here.
const split = v => String(v || "").split(SEP).slice(0, -1);
const id = () => Math.random().toString(16).slice(2, 12), now = () => Date.now() / 1000;

export async function receipts(db, G) {
  const out = [];
  for (const [cid, text, value, agent, sid, stext, quote] of await run(db, G, "receipts")) {
    let why = null; const nums = (quote || stext || "").match(NUM) || [];
    if (sid == null) why = "no source cited";
    else if (quote && !(stext || "").includes(quote)) why = `quote not found in ${sid}`;
    else if (!nums.includes(value)) why = `said ${value}, source says ${nums.join(", ") || "nothing numeric"}`;
    if (why) { await run(db, G, "flag", { id: cid, status: "refuted", reason: why }); out.push({ claim: cid, agent, text, reason: why }); }
  }
  return out;
}

// Growth cap so nobody can fill the shared demo graph with memos/episodes/handoffs between resets.
async function roomFor(db, G) { const r = await run(db, G, "room"); if (Number(r[0][0]) >= 300) throw new Error("demo graph is full; press Reset"); }
export const TOOLS = {
  check_receipts: { d: "QA: refute claims whose number is not in the cited source quote, or that cite nothing.", s: S(), f: receipts },
  claim_risk: { d: "Graph algorithm (PageRank over DERIVED_FROM): rank claims by how load-bearing they are, with how many artifacts and how much published reach sit downstream. Audit the top ones first.", s: S(),
    f: async (db, G) => (await run(db, G, "risk")).map(r => ({ claim: r[0], text: r[1], status: r[2], pagerank: Math.round(Number(r[3]) * 1e4) / 1e4, downstream: Number(r[4]), exposed_reach: Number(r[5]) })) },
  chokepoints: { d: "Graph algorithm (betweenness centrality): artifacts that the most dependency paths run through.", s: S({ k: { type: "integer", description: "how many (default 5)" } }),
    f: async (db, G, a) => (await run(db, G, "chokepoints", { lim: Number(a.k) || 5 })).map(r => ({ id: r[0], title: r[1], status: r[2], betweenness: Number(r[3]) })) },
  correct_claim: { d: "Fix a claim (by claim id) and taint every downstream artifact up to 10 hops (DERIVED_FROM*1..10). Returns the blast radius with hop distance.", s: S({ claim: str("claim id, e.g. from check_receipts"), value: str("the correct value"), reason: str("why") }, ["claim", "value", "reason"]),
    f: async (db, G, a) => (await run(db, G, "correct", { id: String(a.claim), value: String(a.value), reason: String(a.reason) })).map(r => ({ id: r[0], kind: r[1], title: r[2], hops: Number(r[3]) })) },
  recall_plan: { d: "Recall plan: tainted published items, most-viewed first, with owner, live URL and estimated reach.", s: S(),
    f: async (db, G) => { const items = (await run(db, G, "recall")).map(r => ({ id: r[0], kind: r[1], title: r[2], reach: Number(r[3]), url: r[4], owner: r[5], agent: r[6] }));
      return { items, total_reach: items.reduce((x, i) => x + i.reach, 0), live_urls: items.filter(x => x.url).length }; } },
  why_shortest: { d: "Shortest DERIVED_FROM path (shortestPath) from an artifact id back to each corrected/refuted claim, with the exact source quote.", s: S({ artifact: str("artifact id, e.g. 'short'") }, ["artifact"]),
    f: async (db, G, a) => (await run(db, G, "why_shortest_flat", { id: String(a.artifact) })).map(r => ({ path: split(r[0]), ids: split(r[1]), reason: r[2], source: r[3], quote: r[4], hops: Number(r[5]) })) },
  why_tainted: { d: "Every DERIVED_FROM path from an artifact to a bad claim.", s: S({ artifact: str("artifact id") }, ["artifact"]),
    f: async (db, G, a) => (await run(db, G, "why_tainted_flat", { id: String(a.artifact) })).map(r => ({ path: split(r[0]), reason: r[1], source: r[2], quote: r[3] })) },
  requeue_tainted: { d: "Create redo tasks (id 'redo-<artifact id>') for tainted artifacts, owned by the agent that produced them. Idempotent.", s: S(),
    f: async (db, G) => (await run(db, G, "requeue")).map(r => ({ agent: r[0], title: r[1], task: r[2] })) },
  draft_recall_memo: { d: "Store a recall memo for one owner (agent name) in the graph, linked to the open redo tasks they own.", s: S({ owner: str("agent name, e.g. Reel"), text: str("the memo") }, ["owner", "text"]),
    f: async (db, G, a) => { await roomFor(db, G); const r = await run(db, G, "m_memo", { owner: String(a.owner), text: String(a.text).slice(0, 2000), author: "RecallAgent", id: id(), ts: now() }); if (!r.length) throw new Error(`no agent ${a.owner}`); return r[0][0]; } },
  remember_episode: { d: "Episodic memory: log what an agent did, so later sessions can see it.", s: S({ agent: str("agent name"), text: str("what happened"), session: str("session id, e.g. s1"), task: str("optional task id") }, ["agent", "text"]),
    f: async (db, G, a) => { await roomFor(db, G); if (!["RecallAgent", "Scout", "Quill", "Reel", "Lens"].includes(a.agent)) throw new Error("unknown agent"); await run(db, G, "agent", { name: String(a.agent), role: "" }); return (await run(db, G, "m_episode", { agent: String(a.agent), text: String(a.text).slice(0, 1000), session: String(a.session || "s1"), task: String(a.task || ""), id: id(), ts: now() }))[0][0]; } },
  start_session: { d: "Briefing from the graph for a fresh session: owned open tasks, last handoff notes, recall memos addressed to this agent, and its recent episodes.", s: S({ agent: str("agent name") }, ["agent"]),
    f: async (db, G, a) => ({ tasks: (await run(db, G, "m_briefing", { agent: String(a.agent) })).map(r => ({ task: r[0], title: r[1], status: r[2], from_agent: r[3], note: r[4] })),
      memos: (await run(db, G, "m_memos_for", { agent: String(a.agent) })).map(r => ({ author: r[0], text: r[1] })),
      episodes: (await run(db, G, "m_episodes_for", { agent: String(a.agent) })).map(r => ({ session: r[0], text: r[1] })) }) },
  hand_off: { d: "Move task ownership to another agent and record the handoff note.", s: S({ from_agent: str("current owner"), to_agent: str("new owner"), task: str("task id"), note: str("note") }, ["from_agent", "to_agent", "task", "note"]),
    f: async (db, G, a) => { if (a.from_agent === a.to_agent) return "refused: cannot hand a task to yourself";
      await roomFor(db, G);
      const last = await run(db, G, "m_last_giver", { task: String(a.task) });
      if (last.length && last[0][0] === a.to_agent) return `refused: ${a.to_agent} just handed ${a.task} to you; complete it instead of handing it back`;
      const r = await run(db, G, "m_handoff", { from_agent: String(a.from_agent), to_agent: String(a.to_agent), task: String(a.task), note: String(a.note).slice(0, 1000), id: id(), ts: now() }); if (!r.length) throw new Error(`${a.from_agent} does not own task ${a.task}`); return r[0][0]; } },
  complete_task: { d: "Mark a task (e.g. 'redo-short') done.", s: S({ task: str("task id") }, ["task"]),
    f: async (db, G, a) => { const r = await run(db, G, "m_done", { id: String(a.task) }); if (!r.length) throw new Error(`no task ${a.task}`); return a.task; } },
  recall: { d: "Search episodic and semantic memory.", s: S({ query: str("text to search") }, ["query"]),
    f: async (db, G, a) => (await run(db, G, "m_recall", { q: String(a.query), k: 5 })).map(r => ({ kind: r[0], who: r[1], text: r[2] })) },
  trust_ledger: { d: "Each agent's share of refuted or corrected claims.", s: S(),
    f: async (db, G) => (await run(db, G, "trust")).map(r => ({ agent: r[0], claims: r[1], bad: Number(r[2]), trust: r[3] == null ? "unrated" : Math.round(Number(r[3]) * 100) / 100 })) },
};

// Validated input: arguments must match the tool's JSON schema (known keys, right types, bounded lengths).
const LIMITS = { text: 2000, note: 1000, reason: 200, query: 200 };
export function validate(schema, args) {
  if (typeof args !== "object" || args === null || Array.isArray(args)) throw new Error("arguments must be an object");
  for (const k of Object.keys(args)) if (!schema.properties[k]) throw new Error(`unknown argument ${k}`);
  for (const k of schema.required) if (args[k] === undefined || args[k] === null || args[k] === "") throw new Error(`missing argument ${k}`);
  const out = {};
  for (const [k, v] of Object.entries(args)) {
    const t = schema.properties[k].type;
    if (t === "integer") { const n = Number(v); if (!Number.isInteger(n) || n < 1 || n > 50) throw new Error(`${k} must be an integer 1-50`); out[k] = n; continue; }
    if (typeof v !== "string" && typeof v !== "number") throw new Error(`${k} must be a string`);
    const sv = String(v), max = LIMITS[k] || 64;
    if (sv.length > max) throw new Error(`${k} is too long (max ${max})`);
    out[k] = sv;
  }
  return out;
}

// Stateless MCP (JSON-RPC 2.0 over HTTP POST).
export async function rpc(db, G, msg) {
  const ok = result => ({ jsonrpc: "2.0", id: msg.id, result });
  if (msg.method === "initialize") return ok({ protocolVersion: msg.params?.protocolVersion || "2025-06-18", capabilities: { tools: {} }, serverInfo: { name: "taint-receipts", version: "2.0" } });
  if (msg.method?.startsWith("notifications/")) return null;
  if (msg.method === "ping") return ok({});
  if (msg.method === "tools/list") return ok({ tools: Object.entries(TOOLS).map(([name, t]) => ({ name, description: t.d, inputSchema: t.s })) });
  if (msg.method === "tools/call") {
    const t = TOOLS[msg.params?.name];
    if (!t) return { jsonrpc: "2.0", id: msg.id, error: { code: -32602, message: "unknown tool" } };
    try { const v = await t.f(db, G, validate(t.s, msg.params.arguments || {})); return ok({ content: [{ type: "text", text: JSON.stringify(v) }], structuredContent: { result: v }, isError: false }); }
    catch (e) { return ok({ content: [{ type: "text", text: String(e.message || e) }], isError: true }); }
  }
  return { jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: "method not found" } };
}
