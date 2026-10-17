"""Regenerate worker/src/queries.js from the Cypher in teamgraph/taint.py (single source of truth).
Run from the repo root:  python3 worker/gen_queries.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from teamgraph.taint import Q
from teamgraph.graph import Q as GQ
MEM = ["episode", "handoff", "briefing", "done", "memo", "memos_for", "episodes_for", "recall", "last_giver"]
out = os.path.join(os.path.dirname(__file__), "src", "queries.js")
body = ",\n".join(f" {json.dumps(k)}: {json.dumps(v)}" for k, v in Q.items())
mem = ",\n".join(f" {json.dumps(k)}: {json.dumps(GQ[k])}" for k in MEM)
open(out, "w").write(f"// generated from teamgraph/taint.py and teamgraph/graph.py (memory)\nexport const Q = {{\n{body}\n}};\nexport const M = {{\n{mem}\n}};\n")
import shutil; shutil.copy(os.path.join(os.path.dirname(__file__), "..", "teamgraph", "prompts.json"), os.path.join(os.path.dirname(__file__), "src", "prompts.json"))
print(f"wrote {len(Q)} queries to {out}")
