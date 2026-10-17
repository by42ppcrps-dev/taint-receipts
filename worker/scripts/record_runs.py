"""Record one live Gemini run of each agent mode (via teamgraph.agent over MCP stdio) into worker/src/recorded.json.
The Worker replays these tool calls live on FalkorDB when the demo LLM budget is used up. Run from the repo root:
  GEMINI_API_KEY=... TEAMGRAPH_DB=/tmp/rec.db TEAMGRAPH_GRAPH=rec python worker/scripts/record_runs.py"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from teamgraph import agent
from teamgraph.demo_seed import seed
from teamgraph.taint import connect

seed(connect())
runs = {"recall": asyncio.run(agent.run("recall", "Support says battery life is 3.5 hours, not 35"))}
for a in ["Reel", "Quill"]:
    runs[a] = asyncio.run(agent.run("session", a))


def strip(r):
    return {"summary": r["summary"], "trace": [{"tool": x["tool"], "args": x["args"]} for x in r["trace"]]}


with open("worker/src/recorded.json", "w") as fh:
    json.dump(
        {"model": agent.P["model"], "recall": strip(runs["recall"]), "session": {a: strip(runs[a]) for a in ["Reel", "Quill"]}},
        fh,
        indent=1,
    )
print("USAGE", json.dumps({k: v["usage"] for k, v in runs.items()}))
