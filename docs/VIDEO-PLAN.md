# Demo video plan (target 2:00, 1920x1080, plus a 9:16 cut)
Pipeline:
- Screen-capture the real UI with headless Chrome. Each button press is a real Cypher call.
- Composite in Remotion.
- Voice: Gemini TTS via LUMEGRID_GEMINI_API_KEY, voice Puck, with the style ("calm, confident product demo, slight urgency on the reveal") in its own field and never in the spoken text.
- Captions burned in.
- All data is synthetic.

Framing (14 Oct review panel): a **recall system for published content**. Lead with audience and fix order, not "first ever". Name no competitor on screen; the README covers related work honestly.

| t | Visual | VO |
|---|---|---|
| 0:00 | Black. "35 hours" types out, then a hard cut to "3.5". | "Our research bot read three point five as thirty-five." |
| 0:06 | Wall of live items: Short, X post, landing page, link-preview image, email, each with a view count. | "By the time anyone noticed, it was in a Short, two posts, the landing page, its preview image, and a waitlist email. Tens of thousands of people had seen it." |
| 0:15 | Title: Taint + Receipts. A recall system for published content, on FalkorDB. | "So we treat a wrong claim like a product recall." |
| 0:21 | UI graph: green sources, purple claims, blue artifacts. | "Every source, every claim quoted from it, and everything we shipped on top of it." |
| 0:31 | Click "QA bot: check receipts". Two claims go red, with reasons. | "A QA agent checks receipts. The number has to be in the quote. Thirty-five isn't. Ten thousand teams has no source at all." |
| 0:45 | Click Correct. Red ripples hop by hop; hop counts appear. | "One correction. FalkorDB walks every DERIVED_FROM path, up to ten hops deep." |
| 0:55 | Recall plan panel: rows sorted by reach (Short 27,400 · landing 18,500 · X post 12,100 ...), owner and live URL per row, total reach at top. | "Then the recall plan. Every live item, who owns it, and about how many people saw it. Most-viewed first: fix the Short before the reply thread." |
| 1:09 | Zoom on the FAQ, still blue. | "The FAQ stays clean. No path, no recall." |
| 1:15 | Terminal: `python -m teamgraph.scale 1000 25` output: 26,004 nodes, 51,099 edges, p50 0.55 ms, recall in 15 ms. | "At twenty-six thousand nodes and ten hops, the cascade takes about half a millisecond, and the full recall plan under twenty." |
| 1:27 | Click Why. Path highlights back to the quote. | "Why is the Short wrong? Short, script, blog, brief, claim, and the exact source line." |
| 1:38 | Click Re-queue. Tasks appear under Reel and Quill. | "Each fix goes back to whoever made it." |
| 1:46 | Cypher cascade + recall query, MCP tool list incl. `recall_plan`. | "A few lines of Cypher, exposed over MCP to any agent." |
| 1:54 | End card: repo URL and tracks. | "Taint plus Receipts. One wrong number, every place it reached, biggest audience first." |

Notes:
- Benchmark numbers on screen must come from a fresh run of `teamgraph.scale` on recording day; replace the figures above if they differ.
- Reach numbers in the demo are synthetic estimates; the on-screen panel says "est."
- Recall plan is served by `POST /api/recall` (web.py and the Worker); the UI panel is button 4 in `web/index.html`.
- v2 rendered 14 Oct 2026: `video/taint-receipts-demo-v2.mp4`, `video/taint-receipts-9x16-v2.mp4`. Fresh bench used on screen: 26,004 nodes, 51,099 edges, p50 0.62 ms, max 9.01 ms, correct+recall 14.93 ms (VO says "about six tenths of a millisecond ... about fifteen").

Next steps:
1. Record UI clips (Chrome headless frame capture, or Playwright video).
2. Generate 13 TTS lines (≈12 Gemini requests on the paid key).
3. Build the Remotion comp, render, run QA, export the 9:16 cut.
