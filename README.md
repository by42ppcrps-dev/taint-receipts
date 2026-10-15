# Taint + Receipts — a recall system for published content

> One wrong number. Every post, Short, email and link-preview image it reached, who owns each one, and roughly how many people saw it. Fix the most-viewed first.

Content teams (human or AI agents) ship posts, Shorts, emails, landing pages and link-preview images built on top of each other. When one researcher misreads "3.5 hours" as "35 hours", the number spreads into everything downstream, and some of it is already live. **Taint + Receipts** stores every claim, source quote and published artifact in **FalkorDB** and treats a correction like a product recall:

1. **Receipts.** A QA agent checks that each claim's number actually appears in the source quote it cites, and refutes claims with no source.
2. **Taint.** Correcting one claim runs a variable-length `DERIVED_FROM*` traversal that marks every downstream artifact tainted, with its hop distance.
3. **Recall plan (impact-weighted).** Every tainted *published* item comes back with its owner, live URL and estimated reach, sorted most-viewed first, plus the total estimated audience. In the demo the YouTube Short (~27k views) is fixed first and the FAQ is untouched.
4. **Re-queue.** Each tainted artifact becomes a redo task owned by whoever produced it.
5. **Why.** "Why is the Short wrong?" returns the full path Short → script → blog → brief → claim → source quote.
6. **Trust ledger.** Each agent's share of refuted or corrected claims, computed from the graph.

## Scale: measured on embedded FalkorDB (FalkorDBLite, this box)
`python -m teamgraph.scale 1000 25` seeds 1,000 claims and 25,000 synthetic published artifacts with chains up to 10 hops deep, then times the cascade query.

| Graph | Nodes | Edges | Cascade query p50 / max | Correct + recall plan |
|---|---|---|---|---|
| 200 claims × 25 | 5,204 | 10,219 | 0.50 ms / 3.2 ms | 4.1 ms |
| 1,000 claims × 25 | 26,004 | 51,099 | 0.55 ms / 7.5 ms | 14.9 ms |

Numbers are from one run on a shared Linux box (14 Oct 2026). Your hardware will differ; rerun the script to check.

## Related work, and how this differs
This isn't the first system to propagate corrections through derived claims. We checked these on 14 Oct 2026:
- **Memorant** (github.com/tier4research/memorant): agent memory with a `correct_claim()` that flags everything derived from a claim for review. Its unit is the memory or claim inside an agent's knowledge store.
- **Lattice** (github.com/thunderstornX/lattice): a signed claim DAG with agent attribution and a "revocation waterfall" when a claim is revoked. Its strength is cryptographic provenance.
- Research on provenance-native audit (including retraction propagation), plus claim-to-source checkers such as ProvenanceGuard and TRACER.

What we focus on that we didn't see in those: **shipped artifacts across media** (posts, Shorts, captions, emails, link-preview images) as first-class nodes, each with an **owner, live URL and estimated reach**, and a **recall plan ordered by audience size**. We also run it on FalkorDB at tens of thousands of nodes and expose it over MCP. If you need signed provenance, Lattice does more there. If you need agent memory correction, look at Memorant.

All demo data is synthetic, and reach figures are made-up estimates: a fictional product, "Acme Notes", and fictional agents Scout, Quill, Reel and Lens.

## Tracks entered
- **Company Brain:** one graph of what the company has publicly claimed, which documents back it, and who made it.
- **Agent Memory and Coordination:** shared, persistent claim state across agents and sessions, with handoffs via re-queued tasks.
- **Agents That Act on Connected Data:** agents act (taint, re-queue) on multi-hop traversal results.

## Setup (local)
```bash
python3 -m venv .venv && .venv/bin/pip install falkordblite falkordb "mcp[cli]" pytest
.venv/bin/python -m pytest -q          # 16 tests (incl. MCP integration)
.venv/bin/python -m teamgraph.scale 1000 25   # seed ~26k nodes and time the cascade
.venv/bin/python -m teamgraph.web      # demo UI at http://localhost:8787
.venv/bin/python -m teamgraph.mcp_server   # MCP server (stdio) for agents
```
- With no `FALKORDB_URL` set, it uses embedded FalkorDB (FalkorDBLite) at `$TEAMGRAPH_DB` (default `/tmp/teamgraph.db`).
- To use Docker or FalkorDB Cloud instead, run `docker run -p 6379:6379 falkordb/falkordb` and set `FALKORDB_URL=redis://localhost:6379` (or your Cloud URL).

MCP client config:
```json
{"mcpServers":{"taint":{"command":".venv/bin/python","args":["-m","teamgraph.mcp_server"],"env":{"TEAMGRAPH_DB":"/tmp/taint.db","TEAMGRAPH_GRAPH":"teamgraph"}}}}
```
MCP tools:
- Taint tools: `assert_claim`, `register_artifact`, `check_receipts`, `correct_claim`, `recall_plan`, `requeue_tainted`, `why_tainted`, `trust_ledger`
- Shared memory and handoff tools: `remember_episode`, `learn_fact`, `save_procedure`, `create_task`, `hand_off`, `record_decision`, `why_did_we`, `recall`, `how_do_we`, `start_session`, `complete_task`

## Graph data model
```
(:Agent {name, role})-[:ASSERTED]->(:Claim {id, text, value, status: ok|refuted|corrected, reason, fixed_value})
(:Claim)-[:CITES {quote}]->(:Source {id, title, text})
(:Agent)-[:PRODUCED]->(:Artifact {id, kind, title, status: live|tainted, url, reach, owner})
(:Artifact)-[:DERIVED_FROM]->(:Artifact | :Claim)
(:Agent)-[:OWNS]->(:Task {artifact, title, status})
# shared-memory layer (teamgraph/graph.py)
(:Agent)-[:EXPERIENCED]->(:Episode)-[:ABOUT]->(:Task)
(:Concept)-[:SUBJECT_OF]->(:Fact {predicate})-[:OBJECT]->(:Concept); (:Fact)-[:CITES]->(:Source)
(:Procedure)-[:STEP {order}]->(:Step)
(:Agent)-[:GAVE]->(:Handoff)-[:TO]->(:Agent); (:Handoff)-[:FOR]->(:Task)
(:Agent)-[:DECIDED]->(:Decision)-[:BASED_ON]->(:Source); (:Decision)-[:SUPERSEDES]->(:Decision)
```

## Core Cypher
Taint cascade (correction blast radius):
```cypher
MATCH (bad:Claim {id:$id}) SET bad.status='corrected', bad.fixed_value=$value, bad.reason=$reason
WITH bad MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(bad)
SET x.status='tainted' RETURN DISTINCT x.id, x.kind, x.title, length(p) ORDER BY length(p)
```
Why is this artifact wrong (provenance path to the source quote):
```cypher
MATCH p=(x:Artifact {id:$id})-[:DERIVED_FROM*1..10]->(c:Claim) WHERE c.status IN ['corrected','refuted']
OPTIONAL MATCH (c)-[r:CITES]->(s:Source)
RETURN [n IN nodes(p) | coalesce(n.title, n.text)], c.reason, s.title, r.quote
```
Receipts input (each claim with its cited quote; the number check runs in `taint.py`):
```cypher
MATCH (a:Agent)-[:ASSERTED]->(c:Claim) WHERE c.status='ok'
OPTIONAL MATCH (c)-[r:CITES]->(s:Source) RETURN c.id, c.text, c.value, a.name, s.id, s.text, r.quote
```
Recall plan, most-viewed first:
```cypher
MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
RETURN x.id, x.kind, x.title, coalesce(x.reach,0), x.url, coalesce(x.owner, a.name)
ORDER BY coalesce(x.reach,0) DESC
```
Re-queue to producer:
```cypher
MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
MERGE (t:Task {artifact:x.id}) ON CREATE SET t.status='open', t.title='Redo '+x.title
MERGE (a)-[:OWNS]->(t) RETURN a.name, x.title
```
Trust ledger:
```cypher
MATCH (a:Agent) OPTIONAL MATCH (a)-[:ASSERTED]->(c:Claim)
WITH a, count(c) AS total, sum(CASE WHEN c.status IN ['refuted','corrected'] THEN 1 ELSE 0 END) AS bad
RETURN a.name, total, bad, CASE WHEN total=0 THEN null ELSE toFloat(total-bad)/total END AS trust
```
The procedure-driven next step, episodic and semantic recall, and handoff queries are in `teamgraph/graph.py` (dict `Q`).

## Tests
`tests/test_taint.py` covers:
- receipts catching a dropped decimal and an unsourced claim
- a 10-artifact multi-hop cascade, with the FAQ correctly untouched
- the why-path back to the source quote
- re-queueing to the producing agent
- the trust ledger (agents with zero claims show `unrated`, not 1.0)
- the recall plan (most-viewed first, owner, reach, live-URL count)
- seeding over 1,000 nodes and benchmarking the cascade
- persistence across sessions

`tests/test_teamgraph.py` covers handoffs, decision tracing with superseding, recall, procedure-driven next steps, and persistence.

## Why a graph
"Everything downstream of this claim, up to 10 hops" is a bounded variable-length traversal (`DERIVED_FROM*1..10`): one Cypher pattern instead of a recursive query you'd have to write and tune yourself. A vector store finds similar text, not dependency paths. The negative result matters too: the FAQ isn't tainted because no path exists.

Built new during Graph Hacks (event opened Oct 14, 2026 12:31 PM MDT; first commit Oct 14 2:06 PM MDT).

## Live demo
**https://taint-receipts.lumegridai.workers.dev** — click *Receipts*, *Mark 35 h claim corrected → taint downstream*, *Recall plan*, *Why*, *Trust*. All demo data is synthetic. It is a **shared public demo**: one sandbox graph (`taint_demo`), no login, so anyone's Reset/Correct/Re-queue affects everyone and it resets often. `POST /api/reset` re-seeds it. It is a demo only, not a multi-tenant service.

## Architecture
```
browser (web/, vis-network graph view + text equivalent)
   │  fetch /api/{graph,reset,receipts,correct,recall,why,trust,requeue}
   ▼
Cloudflare Worker (worker/src) ── RESP over TCP (cloudflare:sockets) ──▶ FalkorDB Cloud
   (GRAPH.QUERY with the Cypher in teamgraph/)

agents ── MCP server (teamgraph/mcp_server.py) ──▶ one graph: $TEAMGRAPH_GRAPH (default "teamgraph")
local dev / tests ── FalkorDBLite (embedded) or falkordb/falkordb Docker
```
In the MCP server, the memory/handoff tools and the taint tools use **one graph** (`$TEAMGRAPH_GRAPH`, default `teamgraph`): `add_source` (with `text`) feeds `check_receipts`, `register_artifact` takes `url`, `reach` and `owner` for the recall plan, and `requeue_tainted` creates `redo-<artifact>` tasks that `start_session` and `hand_off` see. `tests/test_mcp_integration.py` exercises that path end to end. The public Worker demo deliberately uses a separate sandbox graph (`taint_demo`) seeded with the synthetic story; it runs the same Cypher (generated from `teamgraph/taint.py`) but does not expose the memory tools. Every agent action is a Cypher write; every answer (taint set, recall plan, why-path, trust) is a Cypher read.

## Deploy
See `worker/DEPLOY.md`: `cd worker && npm i && npx wrangler secret put FALKORDB_URL && npx wrangler deploy`. The only secret is `FALKORDB_URL`; it is never committed.

## Demo video
- 16:9: TODO: YouTube URL, added once uploaded (not yet public)
- 9:16: TODO: YouTube URL, added once uploaded (not yet public)

The UI clips are real recordings of the app running against FalkorDB. Rendered files are not committed (size); the Remotion source is in `video/rm`.

Rebuilding the videos (rendered MP4s, the screen recording and the voice WAVs are not committed, for size):
1. Voice: `export LUMEGRID_GEMINI_API_KEY=...` (your own Gemini key), then `cd video && python3 tts.py`. It voices each line of `lines.json` with Gemini TTS (voice Puck) into `audio/sNN.wav`, skipping existing files, and appends one line per call to `tts-calls.log`. Copy `audio/s*.wav` to `rm/public/`, and put each WAV's duration in seconds into `durations.json` and `rm/src/durations.json`.
2. Captions: word timings from faster-whisper (`asr.py`, `small.en`), written to `captions.json` / `rm/src/captions.json`.
3. Screen recording: run the UI (`npx wrangler dev` in `worker/`, or `BASE=<demo URL>`), then `node capture.cjs`. Playwright (system Chrome) clicks each button in time with the narration and writes `raw/ui.webm` and `marks.json`. Convert with `ffmpeg -i raw/ui.webm -r 30 -c:v libx264 -crf 14 -pix_fmt yuv420p rm/public/ui.mp4` and copy `marks.json` to `rm/src/`. Call `POST /api/reset` afterwards.
4. Render: `cd rm && npx remotion render src/index.ts Demo out/h.mp4` and `... Vertical out/v.mp4`, then two-pass `loudnorm` to -14 LUFS with a true-peak limiter at about -1.5 dBTP.

## AI tool use disclosure
- **Code:** written with AI coding agents (Cursor- and Grok-based agents) under human direction; a human reviewed the architecture, security and correctness and can explain every part.
- **Voiceover:** Google Gemini TTS (prebuilt voice), composed with Remotion and loudness-normalized to -14 LUFS. Evidence in this repo: `video/tts.py` (the exact Gemini TTS call), `video/lines.json` (the script that was voiced) and `video/tts-calls.log` (one timestamped line per TTS call, by scene id).
- **Demo data:** every agent, claim, source, URL (`*.example`) and reach number in the demo is synthetic. Nothing in the demo is customer or real-campaign data.
- **The product itself** makes no LLM calls: receipts, taint, recall and trust are deterministic Cypher over FalkorDB.

## License
MIT — see `LICENSE`.
