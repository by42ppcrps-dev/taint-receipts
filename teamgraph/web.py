"""Demo UI server: every button runs a real Cypher operation against FalkorDB."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pydantic import ValidationError

from .demo_seed import seed
from .graph import TeamGraph
from .models import DemoRequest
from .taint import connect

# The local demo UI uses its own sandbox graph (reset wipes it), never the agents' memory graph.
DEMO_GRAPH = os.environ.get("TAINT_DEMO_GRAPH", "taint_demo")
T = connect(DEMO_GRAPH)
TG = TeamGraph(T.g)
with open(os.path.join(os.path.dirname(__file__), "..", "web", "index.html")) as fh:
    HTML = fh.read()
MAX_BODY = 4096


def _reset(b: DemoRequest) -> dict[str, int]:
    seed(T)
    return {"ok": 1}


ACTIONS: dict[str, Callable[[DemoRequest], Any]] = {
    "/api/reset": _reset,
    "/api/receipts": lambda b: T.receipts(),
    "/api/correct": lambda b: T.correct(b.claim, b.value, b.reason),
    "/api/cascade": lambda b: T.cascade_refuted(),
    "/api/requeue": lambda b: T.requeue(),
    "/api/recall": lambda b: T.recall(),
    "/api/why": lambda b: T.why_shortest(b.artifact),
    "/api/why_all": lambda b: T.why(b.artifact),
    "/api/risk": lambda b: T.risk(),
    "/api/chokepoints": lambda b: T.chokepoints(b.k),
    "/api/briefing": lambda b: {"tasks": TG.briefing(b.agent), "memos": TG.memos(b.agent)},
    "/api/trust": lambda b: T.trust(),
    "/api/graph": lambda b: T.snapshot(),
}


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: Any, ctype: str = "application/json") -> None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/api/graph":
            return self._send(200, T.snapshot())
        self._send(200, HTML, "text/html")

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "request too large"})
        if self.path in ("/api/agent", "/api/session"):
            return self._send(501, {"error": "The local UI has no LLM key. Run the agent from a terminal: python -m teamgraph.agent recall / session Reel"})
        f = ACTIONS.get(self.path)
        if not f:
            return self._send(404, {"error": "not found"})
        try:
            b = DemoRequest.model_validate(json.loads(self.rfile.read(n) or b"{}"))
        except (ValueError, ValidationError):
            return self._send(400, {"error": "invalid request"})
        self._send(200, {"result": f(b), "graph": T.snapshot()})

    def log_message(self, *a: Any) -> None:
        pass


if __name__ == "__main__":
    seed(T)
    port = int(os.environ.get("PORT", "8787"))
    print(f"http://localhost:{port}")  # noqa: T201
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), port), H).serve_forever()
