# Cloudflare Workers deploy (free tier)
The Worker serves `web/` as static assets and runs `/api/*` against FalkorDB over TCP (RESP via `cloudflare:sockets`).
Cypher is generated from `teamgraph/taint.py` into `src/queries.js`, so there's one source of truth.

```bash
cd worker && npm i            # needs Node >= 22 (box: ~/.local/opt/node22)
npx wrangler login            # Cloudflare account
npx wrangler secret put FALKORDB_URL   # e.g. rediss://default:<password>@<host>:<port>  (FalkorDB Cloud)
npx wrangler deploy
```
- The first `GET /api/graph` seeds the synthetic demo if the graph is empty.
- Local check (tested): run FalkorDB on :6390, put `FALKORDB_URL=redis://127.0.0.1:6390` in `.dev.vars`, then `npx wrangler dev`.
- If FalkorDB Cloud requires TLS, use `rediss://`. Plain `redis://` connects without TLS.
- After editing the Cypher in `teamgraph/taint.py`, regenerate `src/queries.js` from the repo root with `python3 worker/gen_queries.py`, then redeploy. The Worker seed in `src/index.js` mirrors `teamgraph/demo_seed.py` (including url/reach), so update both together.
- Live: https://taint-receipts.lumegridai.workers.dev (deployed 14 Oct 2026 with `npx wrangler deploy`; the `FALKORDB_URL` secret is set on the Worker).
