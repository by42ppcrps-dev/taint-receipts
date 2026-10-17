// Gemini agent loop. Every tool call is an MCP tools/call through rpc() (the same handler POST /mcp serves),
// i.e. a Cypher read/write on FalkorDB. Spend guard: token usage is priced and stored in a separate meta graph
// (Reset never wipes it). When the cap is reached, the Gemini key is missing, a live run happened <20 s ago, or
// Gemini errors, the agent REPLAYS a recorded Gemini run: the same tool calls, executed live against the graph,
// and clearly labelled as a replay in the response and the UI.
import { rpc } from "./tools.js";
import P from "./prompts.json";
import REC from "./recorded.json";
const ROLES = { Scout: "research", Quill: "copywriting", Reel: "video and captions", Lens: "QA" };
const ALLOW = { recall: ["check_receipts", "claim_risk", "chokepoints", "correct_claim", "recall_plan", "why_shortest", "requeue_tainted", "draft_recall_memo", "remember_episode", "trust_ledger"],
  session: ["start_session", "complete_task", "hand_off", "remember_episode", "recall"] };
const PRICE_IN = 0.30e-6, PRICE_OUT = 2.50e-6, META = "taint_meta";

async function call(db, G, name, args) {
  const r = (await rpc(db, G, { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } })).result;
  return r.isError ? { error: r.content[0].text } : r.structuredContent.result;
}
async function budget(db) {
  const r = await db.query(META, "MERGE (b:Budget {id:'llm'}) ON CREATE SET b.usd=0.0, b.runs=0, b.last=0 RETURN b.usd, b.runs, b.last");
  return { usd: Number(r[0][0]), runs: Number(r[0][1]), last: Number(r[0][2]) };
}
export async function runAgent(db, G, env, mode, who) {
  const cap = Number(env.LLM_CAP_USD || 0.5), b = await budget(db);
  if (env.GEMINI_API_KEY && b.usd < cap && Date.now() / 1000 - b.last > 20)
    try { return await liveRun(db, G, env, mode, who); } catch (e) { return replay(db, G, mode, who, "Gemini error: " + String(e.message || e).slice(0, 120)); }
  return replay(db, G, mode, who, !env.GEMINI_API_KEY ? "no Gemini key configured" : b.usd >= cap ? "demo LLM budget used up" : "another live run just happened (20 s cooldown)");
}
async function replay(db, G, mode, who, why) {
  const rec = mode === "recall" ? REC.recall : (REC.session[who] || { summary: "(replay) briefing only", trace: [{ tool: "start_session", args: { agent: who } }] });
  const trace = [];
  for (const s of rec.trace) trace.push({ tool: s.tool, args: s.args, result: await call(db, G, s.tool, s.args) });
  return { mode, live: false, replay_reason: why, model: REC.model, summary: rec.summary, trace, usage: null };
}
async function liveRun(db, G, env, mode, who) {
  await db.query(META, "MATCH (b:Budget {id:'llm'}) SET b.last=$t, b.runs=b.runs+1", { t: Date.now() / 1000 });
  const model = env.GEMINI_MODEL || P.model;
  const prompt = mode === "recall" ? P.recall.replace("{correction}", who || "Support says battery life is 3.5 hours, not 35")
    : P.session.replaceAll("{agent}", who).replaceAll("{role}", ROLES[who] || "team");
  const tl = (await rpc(db, G, { jsonrpc: "2.0", id: 1, method: "tools/list" })).result.tools.filter(t => ALLOW[mode].includes(t.name));
  const decls = tl.map(t => Object.keys(t.inputSchema.properties).length ? { name: t.name, description: t.description, parameters: t.inputSchema } : { name: t.name, description: t.description });
  const contents = [{ role: "user", parts: [{ text: prompt }] }], trace = [], usage = { in: 0, out: 0 };
  let summary = "(stopped: turn limit)";
  try {
    for (let turn = 0; turn < P.max_turns; turn++) {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, { method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
        body: JSON.stringify({ contents, tools: [{ functionDeclarations: decls }], generationConfig: { temperature: 0 } }) });
      const j = await res.json(); if (!res.ok) throw new Error(j.error?.message || res.status);
      const um = j.usageMetadata || {}; usage.in += um.promptTokenCount || 0; usage.out += (um.candidatesTokenCount || 0) + (um.thoughtsTokenCount || 0);
      const msg = j.candidates[0].content; contents.push(msg);
      const calls = (msg.parts || []).filter(p => p.functionCall).map(p => p.functionCall);
      if (!calls.length) { summary = (msg.parts || []).map(p => p.text || "").join("").trim(); break; }
      const parts = [];
      for (const c of calls) {
        const out = ALLOW[mode].includes(c.name) ? await call(db, G, c.name, c.args || {}) : { error: "tool not allowed" };
        trace.push({ tool: c.name, args: c.args || {}, result: out });
        parts.push({ functionResponse: { name: c.name, response: out && typeof out === "object" && !Array.isArray(out) ? out : { result: out } } });
      }
      contents.push({ role: "user", parts });
    }
  } finally {
    await db.query(META, "MATCH (b:Budget {id:'llm'}) SET b.usd=b.usd+$u", { u: usage.in * PRICE_IN + usage.out * PRICE_OUT });
  }
  return { mode, live: true, model, summary, trace, usage: { ...usage, usd: Math.round((usage.in * PRICE_IN + usage.out * PRICE_OUT) * 1e5) / 1e5 } };
}
