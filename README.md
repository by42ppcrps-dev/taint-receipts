# Taint + Receipts — a recall system for published content

> One wrong number. Every post, Short, email and link-preview image it reached, who owns each one, and roughly how many people saw it. Fix the most-viewed first.

Content teams (human or AI agents) ship posts, Shorts, emails, landing pages and link-preview images built on top of each other. When one researcher misreads "3.5 hours" as "35 hours", the number spreads into everything downstream, and some of it is already live. **Taint + Receipts** stores every claim, source quote and published artifact in **FalkorDB** and treats a correction like a product recall:

1. **Receipts.** A QA agent checks that each claim's number actually appears in the source quote it cites, and refutes claims with no source.
2. **Taint.** Correcting one claim runs a bounded variable-length `DERIVED_FROM*1..10` traversal that marks every downstream artifact up to ten hops away as tainted, with its hop distance.
3. **Recall plan (impact-weighted).** Every tainted *published* item comes back with its owner, live URL and estimated reach, sorted most-viewed first, plus the total estimated audience. In the demo the YouTube Short (~27k views) is fixed first and the FAQ is untouched.
4. **Re-queue.** Each tainted artifact becomes a redo task with a stable id (`redo-<artifact id>`), owned by whoever produced it. Re-running it is idempotent.
5. **Why.** "Why is the Short wrong?" returns the full path Short → script → blog → brief → claim → source quote.
6. **Trust ledger.** Each agent's share of refuted or corrected claims, computed from the graph.

## Scale: measured on embedded FalkorDB (FalkorDBLite, this box)
`python -m teamgraph.scale 1000 25` seeds 1,000 claims and 25,000 synthetic published artifacts with chains up to 10 hops deep, then times the cascade query.

| Graph | Nodes | Edges | Cascade query p50 / max | Correct + recall plan |
|---|---|---|---|---|
| 200 claims × 25 | 5,204 | 10,219 | 0.50 ms / 3.2 ms | 4.1 ms |
| 1,000 claims × 25 | 26,004 | 51,099 | 0.55 ms / 7.5 ms | 14.9 ms |

Numbers are from one run on a shared Linux box (14 Oct 2026). The demo video's terminal panel shows a later run of the same command (p50 0.62 ms, max 9.01 ms, correct + recall 14.93 ms). Your hardware will differ; rerun the script to check.

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
.venv/bin/python -m pytest -q          # 20 tests (incl. MCP integration over stdio)
.venv/bin/python -m teamgraph.scale 1000 25   # seed ~26k nodes and time the cascade
.venv/bin/python -m teamgraph.web      # demo UI at http://localhost:8787
.venv/bin/python -m teamgraph.mcp_server   # MCP server (stdio) for agents
```
- With no `FALKORDB_URL` set, it uses embedded FalkorDB (FalkorDBLite) at `$TEAMGRAPH_DB` (default `/tmp/teamgraph.db`).
- To use Docker or FalkorDB Cloud instead, run `docker run -p 6379:6379 falkordb/falkordb` and set `FALKORDB_URL=redis://localhost:6379` (or your Cloud URL).

### Graphs (explicit configuration)
| Process | Graph name | Set with | Contents |
|---|---|---|---|
| MCP server (`teamgraph.mcp_server`): memory, handoff **and** taint tools | `teamgraph` | `TEAMGRAPH_GRAPH` | the agents' real working graph; one graph object shared by all tools |
| Local demo UI (`teamgraph.web`) | `taint_demo` | `TAINT_DEMO_GRAPH` | synthetic Acme Notes story; **Reset wipes it** |
| Public Worker demo (`worker/`) | `taint_demo` | `DEMO_GRAPH` (wrangler var) | same synthetic story, on FalkorDB Cloud |
| Benchmark (`teamgraph.scale`) | `taint_scale` | (argument) | 26k synthetic nodes |

The demo graphs are sandboxes on purpose: their Reset deletes everything in the graph, so never point `TAINT_DEMO_GRAPH`/`DEMO_GRAPH` at the agents' graph. `teamgraph.taint.connect()` and `teamgraph.graph.connect()` with no argument both resolve to `$TEAMGRAPH_GRAPH` (default `teamgraph`).

MCP client config:
```json
{"mcpServers":{"taint":{"command":".venv/bin/python","args":["-m","teamgraph.mcp_server"],"env":{"TEAMGRAPH_DB":"/tmp/taint.db","TEAMGRAPH_GRAPH":"teamgraph"}}}}
```
MCP tools (all on the one `$TEAMGRAPH_GRAPH` graph):
- Taint tools: `assert_claim`, `register_artifact(agent, id, kind, title, derived_from, url, reach, owner)`, `check_receipts`, `correct_claim`, `recall_plan`, `requeue_tainted`, `why_tainted`, `trust_ledger`
- Shared memory and handoff tools: `add_source(id, title, url, text)`, `remember_episode`, `learn_fact`, `save_procedure`, `create_task`, `hand_off`, `record_decision`, `why_did_we`, `recall`, `how_do_we`, `start_session`, `complete_task`
- `add_source` stores the source **text** as well as its URL; `check_receipts` verifies each claim's quote and number against that text, so a URL-only source can't pass a receipt check. Empty `url`/`text` never wipes a stored value.
- `requeue_tainted` returns `[{agent, title, task}]`; `task` is `redo-<artifact id>`, the id `start_session`, `hand_off` and `complete_task` use.

## Graph data model
```
(:Agent {name, role})-[:ASSERTED]->(:Claim {id, text, value, status: ok|refuted|corrected, reason, fixed_value})
(:Claim)-[:CITES {quote}]->(:Source {id, title, url, text})
(:Agent)-[:PRODUCED]->(:Artifact {id, kind, title, status: live|tainted, url, reach, owner})
(:Artifact)-[:DERIVED_FROM]->(:Artifact | :Claim)
(:Agent)-[:OWNS]->(:Task {id: 'redo-<artifact id>', artifact, title, status})
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
Re-queue to producer (stable task id; never re-assigns a task that was handed off):
```cypher
MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
MERGE (t:Task {id:'redo-' + x.id}) ON CREATE SET t.artifact=x.id, t.status='open', t.title='Redo ' + x.title
WITH x, a, t OPTIONAL MATCH (t)<-[:OWNS]-(o:Agent)
WITH x, a, t, count(o) AS owners
FOREACH (_ IN CASE WHEN owners = 0 THEN [1] ELSE [] END | MERGE (a)-[:OWNS]->(t))
RETURN a.name, x.title, t.id ORDER BY t.id
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
- re-queueing to the producing agent, with stable, idempotent `redo-<artifact>` task ids
- the trust ledger (agents with zero claims show `unrated`, not 1.0)
- the recall plan (most-viewed first, owner, reach, live-URL count)
- seeding over 1,000 nodes and benchmarking the cascade
- persistence across sessions

`tests/test_teamgraph.py` covers handoffs, decision tracing with superseding, recall, procedure-driven next steps, and persistence.

`tests/test_mcp_integration.py` runs the MCP tool functions on one configured graph: source (URL, then text) → claim → artifact (url/reach/owner) → receipts → correction → recall plan → requeue (twice, same ids) → `start_session` → `hand_off` → `complete_task`, plus memory `recall` and `why_tainted`. A second test starts `python -m teamgraph.mcp_server` as a real stdio MCP server and drives the same path through an MCP client.

## Why a graph
"Everything downstream of this claim, up to 10 hops" is a bounded variable-length traversal (`DERIVED_FROM*1..10`): one Cypher pattern instead of a recursive query you'd have to write and tune yourself. A vector store finds similar text, not dependency paths. The negative result matters too: the FAQ isn't tainted because no path exists.

Built new during Graph Hacks (build window opened Oct 14, 2026 12:31 PM MDT / 18:31 UTC). The first file (`.venv`) was created at 2:00 PM MDT and the first commit is 2:06:57 PM MDT (20:06:57 UTC) in our original local history. This public repo is a clean export of that history made at 10:55 PM MDT, so its first commit shows 22:55. `docs/HISTORY.md` maps the original commits to the export and lists the evidence and its limits.

## Live demo
**https://taint-receipts.lumegridai.workers.dev** — click *Receipts*, *Mark 35 h claim corrected → taint downstream*, *Recall plan*, *Why*, *Trust*. All demo data is synthetic. It is a **shared public demo, for demonstration only**: one sandbox graph (`taint_demo`), no login and no per-visitor isolation, so anyone's Reset/Correct/Re-queue affects everyone and it resets often. `POST /api/reset` re-seeds it. It is not a multi-tenant service; run it locally (`python -m teamgraph.web`) for a private copy.

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
- 16:9: **pending**. The YouTube link will be added here once the final video is uploaded and checked; until then there is no public link.
- 9:16: **pending**, same as above.

The UI clips are real screen recordings of the app running against FalkorDB. The rendered MP4s aren't committed (size). Everything that goes into a render is: `video/rm/src` (Remotion composition, captions, timing marks, durations), `video/rm/public/ui.mp4` (the exact screen recording used), `video/audio/s01.wav`–`s13.wav` (the exact voice segments), `video/lines.json` (the narration text) and `video/RENDER-INPUTS.sha256` (hashes of all of them). See `video/REBUILD.md` for how to re-render from these files byte-for-byte inputs, or to recreate them from scratch.

## AI tool use disclosure
- **Code, docs and video pipeline:** written by AI agents. The build agent was LumeGrid's Grok Bot agent, working on a Linux box at the direction of LumeGrid's founder, Matt Brady, who chose the hackathon, approved the scope and controls publication. A second AI agent (Pika) did QA review of the code, bundle and videos. We are not claiming a line-by-line human code review.
- **Voiceover:** Google Gemini TTS (`gemini-3.8-flash-tts`, prebuilt voice Puck), composed with Remotion and loudness-normalized to -14 LUFS. Evidence in this repo: `video/tts.py` (the exact request), `video/lines.json` (the text that was voiced), the `video/audio/*.wav` segments, and `video/tts-calls.public.jsonl`, a sanitized copy of our local TTS call log that keeps only the UTC time and scene id of each call (no keys, request bodies or responses). The raw local log stays out of the repo.
- **Demo data:** every agent, claim, source, URL (`*.example`) and reach number in the demo is synthetic. Nothing in the demo is customer or real-campaign data.
- **The product itself** makes no LLM calls: receipts, taint, recall and trust are deterministic Cypher over FalkorDB.

## License
MIT — see `LICENSE`.
