"""MCP server: agents read/write TeamGraph memory over stdio."""
from mcp.server.mcpserver import MCPServer as FastMCP
from .graph import connect
tg = connect(); tg.setup()
mcp = FastMCP("teamgraph")

@mcp.tool()
def remember_episode(agent: str, text: str, session: str = "s1", task: str = "") -> str:
    """Episodic memory: log what an agent did/saw."""
    tg.agent(agent); return tg.episode(agent, text, session, task)
@mcp.tool()
def learn_fact(subject: str, predicate: str, object: str, source: str = "") -> str:
    """Semantic memory: store a subject-predicate-object fact, optionally citing a Source id."""
    return tg.fact(subject, predicate, object, source)
@mcp.tool()
def save_procedure(name: str, trigger: str, steps: list[str]) -> str:
    """Procedural memory: ordered steps used when a task title contains `trigger`."""
    tg.procedure(name, trigger, steps); return name
@mcp.tool()
def add_source(id: str, title: str, url: str) -> str:
    tg.source(id, title, url); return id
@mcp.tool()
def create_task(id: str, title: str, owner: str) -> str:
    tg.agent(owner); tg.task(id, title, owner); return id
@mcp.tool()
def hand_off(from_agent: str, to_agent: str, task: str, note: str) -> str:
    """Move task ownership and record the handoff note."""
    tg.agent(to_agent); return tg.handoff(from_agent, to_agent, task, note)
@mcp.tool()
def record_decision(agent: str, what: str, why: str, sources: list[str] = [], task: str = "", supersedes: str = "") -> str:
    return tg.decide(agent, what, why, sources, task, supersedes)
@mcp.tool()
def why_did_we(question: str) -> list[dict]:
    """Decision trace: who decided, why, sources, and what it replaced."""
    return tg.why(question)
@mcp.tool()
def recall(query: str, k: int = 5) -> list[dict]:
    return tg.recall(query, k)
@mcp.tool()
def how_do_we(query: str) -> list[str]:
    return tg.how(query)
@mcp.tool()
def start_session(agent: str) -> dict:
    """Briefing from the graph: owned open tasks, last handoff notes, and the next procedure step."""
    return dict(tasks=tg.briefing(agent), next=tg.next_step(agent))
@mcp.tool()
def complete_task(task: str) -> str:
    tg.complete(task); return task

from .taint import Taint
tt = Taint(connect("taint"))

@mcp.tool()
def assert_claim(agent: str, text: str, value: str, sources: list[str] = [], quote: str = "") -> str:
    """Record an atomic claim (with the exact number) and the source quote it relies on."""
    tt.agent(agent); return tt.claim(agent, text, value, sources, quote)
@mcp.tool()
def register_artifact(agent: str, id: str, kind: str, title: str, derived_from: list[str]) -> str:
    """Record an output and which claims/artifacts it was built from (DERIVED_FROM)."""
    tt.agent(agent); return tt.artifact(agent, id, kind, title, derived_from)
@mcp.tool()
def check_receipts() -> list[dict]:
    """QA: refute claims whose number is not in the cited source, or that cite nothing."""
    return tt.receipts()
@mcp.tool()
def correct_claim(claim: str, value: str, reason: str) -> list[dict]:
    """Fix a claim and taint every downstream artifact (multi-hop). Returns the blast radius."""
    return tt.correct(claim, value, reason)
@mcp.tool()
def recall_plan() -> dict:
    """Recall plan for published content: tainted posts/Shorts/emails/images, most-viewed first, with owner, live URL, est. reach."""
    return tt.recall()

@mcp.tool()
def requeue_tainted() -> list:
    """Create redo tasks for tainted artifacts, owned by the agent that produced them."""
    return tt.requeue()
@mcp.tool()
def why_tainted(artifact: str) -> list[dict]:
    return tt.why(artifact)
@mcp.tool()
def trust_ledger() -> list[dict]:
    return tt.trust()

if __name__ == "__main__": mcp.run()
