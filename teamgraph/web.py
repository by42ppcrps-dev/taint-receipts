"""Demo UI server: every button runs a real Cypher operation against FalkorDB."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .taint import connect
from .demo_seed import seed
T = connect("taint_demo")
HTML = open(os.path.join(os.path.dirname(__file__), "..", "web", "index.html")).read()
ACTIONS = {
 "/api/reset": lambda b: (seed(T), {"ok": 1})[1],
 "/api/receipts": lambda b: T.receipts(),
 "/api/correct": lambda b: T.correct(b.get("claim","c-battery"), b.get("value","3.5"), b.get("reason","decimal dropped")),
 "/api/cascade": lambda b: T.cascade_refuted(),
 "/api/requeue": lambda b: T.requeue(),
 "/api/recall": lambda b: T.recall(),
 "/api/why": lambda b: T.why(b.get("artifact","short")),
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
        n = int(self.headers.get("Content-Length") or 0); b = json.loads(self.rfile.read(n) or b"{}")
        f = ACTIONS.get(self.path)
        if not f: return self._send(404, {"error": "no"})
        self._send(200, {"result": f(b), "graph": T.snapshot()})
    def log_message(self, *a): pass
if __name__ == "__main__":
    seed(T); port = int(os.environ.get("PORT", 8787)); print(f"http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
