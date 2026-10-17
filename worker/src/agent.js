// Gemini agent loop. Every tool call is an MCP tools/call through rpc() (the same handler POST /mcp serves),
// i.e. a Cypher read/write on FalkorDB. Spend guard: one atomic query in taint_meta both checks and takes
// the live-run slot (Reset never wipes that graph). When the cap is reached, the slot is busy, the Gemini
// key is missing, or Gemini errors, the agent REPLAYS a recorded Gemini run: the same tool calls, executed
// live against the graph, and clearly labelled as a replay in the response and the UI.
import { rpc, needsReceipt, untrustedText, scrub } from "./tools.js";
import { run } from "./cypher.js";
import P from "./prompts.json";
import REC from "./recorded.json";
export { needsReceipt, untrustedText, scrub };
const ROLES = { Scout: "research", Quill: "copywriting", Reel: "video and captions", Lens: "QA" };
const ALLOW = { recall: ["check_receipts", "claim_risk", "chokepoints", "correct_claim", "recall_plan", "why_shortest", "requeue_tainted", "draft_recall_memo", "remember_episode", "trust_ledger"],
  session: ["start_session", "complete_task", "hand_off", "remember_episode", "recall"] };
const PRICE_IN = 0.30e-6, PRICE_OUT = 2.50e-6, META = "taint_meta";
const GAP_MS = 20000, LEASE_MS = 45000;
const MAX_CALLS = 30;

export function priced(usage) {
  const n = v => { const x = Number(v); return Number.isFinite(x) && x > 0 ? x : 0; };
  const inn = n(usage && usage.in), out = n(usage && usage.out);
  return { in: inn, out, usd: inn * PRICE_IN + out * PRICE_OUT };
}
export function redact(s, ...secrets) {
  let out = String(s == null ? "" : s);
  for (const k of secrets) if (k && String(k).length >= 6) out = out.split(String(k)).join("[redacted]");
  return out.replace(/rediss?:\/\/\S+/gi, "redis://redacted").replace(/AIza[0-9A-Za-z_-]{20,}/g, "[redacted]").slice(0, 200);
}
// A function replacer so correction text is literal: String.replace would expand $', $& and $`.
export function recallPrompt(correction) {
  const text = untrustedText(correction || "Support says battery life is 3.5 hours, not 35", 300);
  return P.recall.replace("{correction}", () => text);
}
export function sessionPrompt(who) {
  const agent = Object.hasOwn(ROLES, who) ? who : "Reel";
  return P.session.replaceAll("{agent}", () => agent).replaceAll("{role}", () => ROLES[agent]);
}
// Narrow scoping: whatever the model was talked into, it may only use its mode's tools, and act as itself.
export function guard(mode, who, name, a) {
  if (!ALLOW[mode].includes(name)) return { error: "tool not allowed" };
  if (typeof a !== "object" || a === null || Array.isArray(a)) return { error: "bad arguments" };
  if (mode === "session") {
    if (name === "start_session" && a.agent !== who) return { error: `you are ${who}` };
    if (name === "hand_off" && a.from_agent !== who) return { error: `you can only hand off your own tasks (${who})` };
    if (name === "hand_off" && !Object.hasOwn(ROLES, a.to_agent)) return { error: "you can only hand off to Scout, Quill, Reel, or Lens" };
    if (name === "remember_episode" && a.agent !== who) return { error: `log episodes as ${who}` };
  }
  if (mode === "recall" && name === "remember_episode" && a.agent !== "RecallAgent") return { error: "log episodes as RecallAgent" };
  return null;
}
async function call(db, G, name, args) {
  const r = (await rpc(db, G, { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } })).result;
  return r.isError ? { error: r.content[0].text } : r.structuredContent.result;
}
// Live and replay share this path: allow-list, ownership, and the receipt rule.
export async function act(db, G, mode, who, name, args) {
  const a = args && typeof args === "object" && !Array.isArray(args) ? args : {};
  const g = guard(mode, who, name, a);
  if (g) return g;
  if (mode === "session" && name === "complete_task") {
    const rows = await run(db, G, "owns", { agent: who, task: String(a.task || "") });
    if (!rows.length) return { error: `you do not own task ${a.task}` };
  }
  if (name === "correct_claim") {
    const rec = await needsReceipt(db, G, a);
    if (rec) return rec;
  }
  return call(db, G, name, a);
}
function modelResponse(out) {
  const clean = scrub(out);
  return clean && typeof clean === "object" && !Array.isArray(clean) ? clean : { result: clean };
}
export async function runAgent(db, G, env, mode, who) {
  if (!env.GEMINI_API_KEY) return replay(db, G, mode, who, "no Gemini key configured");
  const cap = Number(env.LLM_CAP_USD || 0.5), t = Date.now();
  let row;
  try { row = (await run(db, META, "budget_acquire", { cap, t, gap: GAP_MS, lease: LEASE_MS }))[0]; }
  catch (e) { console.log("budget", redact(e && e.message || e, env.GEMINI_API_KEY)); return replay(db, G, mode, who, "budget check failed"); }
  if (!row || Number(row[0]) !== 1) {
    const why = row && row[1];
    const msg = why === "cap" ? "demo LLM budget used up" : why === "busy" ? "another live run is in progress" : "another live run just happened (20 s cooldown)";
    return replay(db, G, mode, who, msg);
  }
  try { return await liveRun(db, G, env, mode, who, t); }
  catch (e) { console.log("gemini", redact(e && e.message || e, env.GEMINI_API_KEY)); return replay(db, G, mode, who, "the model call failed"); }
}
async function replay(db, G, mode, who, why) {
  const rec = mode === "recall" ? REC.recall : (REC.session[who] || { summary: "(replay) briefing only", trace: [{ tool: "start_session", args: { agent: who } }] });
  const trace = [];
  for (const s of rec.trace) trace.push({ tool: s.tool, args: s.args, result: await act(db, G, mode, who, s.tool, s.args) });
  return { mode, live: false, replay_reason: why, model: REC.model, summary: rec.summary, trace, usage: null };
}
async function liveRun(db, G, env, mode, who, token) {
  const model = env.GEMINI_MODEL || P.model;
  if (!/^[A-Za-z0-9._-]+$/.test(model)) throw new Error("bad model");
  const prompt = mode === "recall" ? recallPrompt(who) : sessionPrompt(who);
  const tl = (await rpc(db, G, { jsonrpc: "2.0", id: 1, method: "tools/list" })).result.tools.filter(t => ALLOW[mode].includes(t.name));
  const decls = tl.map(t => Object.keys(t.inputSchema.properties).length ? { name: t.name, description: t.description, parameters: t.inputSchema } : { name: t.name, description: t.description });
  const contents = [{ role: "user", parts: [{ text: prompt }] }], trace = [], usage = { in: 0, out: 0 };
  let summary = "(stopped: turn limit)", cost = priced(usage);
  try {
    for (let turn = 0; turn < P.max_turns; turn++) {
      const beat = await run(db, META, "budget_touch", { token, t: Date.now() });
      if (!beat.length) throw new Error("lost budget lock");
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, { method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY }, signal: AbortSignal.timeout(20000),
        body: JSON.stringify({ contents, tools: [{ functionDeclarations: decls }], generationConfig: { temperature: 0 } }) });
      const j = await res.json(); if (!res.ok) throw new Error("model HTTP " + res.status);
      const um = j.usageMetadata || {};
      const n = v => { const x = Number(v); return Number.isFinite(x) && x > 0 ? x : 0; };
      usage.in += n(um.promptTokenCount);
      usage.out += n(um.candidatesTokenCount) + n(um.thoughtsTokenCount);
      const msg = j.candidates[0].content; contents.push(msg);
      const calls = (msg.parts || []).filter(p => p.functionCall).map(p => p.functionCall);
      if (!calls.length) { summary = (msg.parts || []).map(p => p.text || "").join("").trim(); break; }
      const parts = [];
      for (const c of calls) {
        if (trace.length >= MAX_CALLS) throw new Error("tool-call limit");
        const out = await act(db, G, mode, who, c.name, c.args || {});
        trace.push({ tool: c.name, args: c.args || {}, result: out });
        parts.push({ functionResponse: { name: c.name, response: modelResponse(out) } });
      }
      contents.push({ role: "user", parts });
    }
  } finally {
    cost = priced(usage);
    await run(db, META, "budget_finish", { u: cost.usd, token, t: Date.now() });
  }
  return { mode, live: true, model, summary, trace, usage: { in: cost.in, out: cost.out, usd: Math.round(cost.usd * 1e5) / 1e5 } };
}
