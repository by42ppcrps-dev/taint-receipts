"""Regenerate worker/src/queries.js from the Cypher in teamgraph/taint.py (single source of truth).
Run from the repo root:  python3 worker/gen_queries.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from teamgraph.taint import Q
out = os.path.join(os.path.dirname(__file__), "src", "queries.js")
body = ",\n".join(f" {json.dumps(k)}: {json.dumps(v)}" for k, v in Q.items())
open(out, "w").write(f"// generated from teamgraph/taint.py\nexport const Q = {{\n{body}\n}};\n")
print(f"wrote {len(Q)} queries to {out}")
