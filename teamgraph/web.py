"""Demo UI server: every button runs a real Cypher operation against FalkorDB."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .taint import connect
from .demo_seed import seed
from .graph import TeamGraph
# The local demo UI uses its own sandbox graph (reset wipes it), never the agents' memory graph.
DEMO_GRAPH = os.environ.get("TAINT_DEMO_GRAPH", "taint_demo")
T = connect(DEMO_GRAPH)
TG = TeamGraph(T.g)
HTML = open(os.path.join(os.path.dirname(__file__), "..", "web", "index.html")).read()
ACTIONS = {
 "/api/reset": lambda b: (seed(T), {"ok": 1})[1],
 "/api/receipts": lambda b: T.receipts(),
 "/api/correct": lambda b: T.correct(b.get("claim","c-battery"), b.get("value","3.5"), b.get("reason","decimal dropped")),
 "/api/cascade": lambda b: T.cascade_refuted(),
 "/api/requeue": lambda b: T.requeue(),
 "/api/recall": lambda b: T.recall(),
 "/api/why": lambda b: T.why_shortest(str(b.get("artifact","short"))[:64]),
 "/api/why_all": lambda b: T.why(str(b.get("artifact","short"))[:64]),
 "/api/risk": lambda b: T.risk(),
 "/api/chokepoints": lambda b: T.chokepoints(5),
 "/api/briefing": lambda b: dict(tasks=TG.briefing(str(b.get("agent","Reel"))[:16]), memos=TG.memos(str(b.get("agent","Reel"))[:16])),
 "/api/trust": lambda b: T.trust(),
 "/api/graph": lambda b: T.snapshot(),
}
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/api/graph": return self._send(200, T.snapshot())
        self._send(200, HTML, "text/html")
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 4096: return self._send(413, {"error": "request too large"})
        if self.path in ("/api/agent", "/api/session"):
            return self._send(501, {"error": "The local UI has no LLM key. Run the agent from a terminal: python -m teamgraph.agent recall / session Reel"})
        f = ACTIONS.get(self.path)
        if not f: return self._send(404, {"error": "no"})
        try: b = json.loads(self.rfile.read(n) or b"{}"); assert isinstance(b, dict)
        except Exception: return self._send(400, {"error": "invalid JSON"})
        self._send(200, {"result": f(b), "graph": T.snapshot()})
    def log_message(self, *a): pass
if __name__ == "__main__":
    seed(T); port = int(os.environ.get("PORT", 8787)); print(f"http://localhost:{port}")
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), port), H).serve_forever()
