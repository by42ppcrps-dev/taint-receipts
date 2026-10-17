"""MCP server: agents read/write TeamGraph memory over stdio."""
from mcp.server.mcpserver import MCPServer as FastMCP
import os
from .graph import connect
# ONE graph for memory, handoffs and taint/receipts, so requeued redo tasks show up in start_session.
# Configure with $TEAMGRAPH_GRAPH (default "teamgraph"); FalkorDB via $FALKORDB_URL, else embedded at $TEAMGRAPH_DB.
GRAPH = os.environ.get("TEAMGRAPH_GRAPH", "teamgraph")
tg = connect(GRAPH); tg.setup()
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
def add_source(id: str, title: str, url: str = "", text: str = "") -> str:
    """Add/update a Source in the shared graph. Keep `text` (the source wording): check_receipts verifies each
    claim's quote and number against it. A URL alone cannot be checked. Empty url/text never wipes a stored value."""
    tg.source(id, title, url, text); return id
@mcp.tool()
def create_task(id: str, title: str, owner: str) -> str:
    tg.agent(owner); tg.task(id, title, owner); return id
@mcp.tool()
def hand_off(from_agent: str, to_agent: str, task: str, note: str) -> str:
    """Move task ownership and record the handoff note."""
    tg.agent(to_agent)
    try: return tg.handoff(from_agent, to_agent, task, note)
    except ValueError as e: return f"refused: {e}"   # the reason reaches the agent, so it can change course
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
    """Briefing from the graph for a fresh session: owned open tasks, last handoff notes, recall memos addressed
    to this agent, its own recent episodes from earlier sessions, and the next procedure step."""
    return dict(tasks=tg.briefing(agent), memos=tg.memos(agent), episodes=tg.episodes(agent), next=tg.next_step(agent))
@mcp.tool()
def complete_task(task: str) -> str:
    """Mark a task (e.g. 'redo-short') done; it drops out of start_session briefings."""
    if not tg.complete(task): raise ValueError(f"no task {task}")
    return task

from .taint import Taint
tt = Taint(tg)  # same graph as the memory tools

@mcp.tool()
def assert_claim(agent: str, text: str, value: str, sources: list[str] = [], quote: str = "") -> str:
    """Record an atomic claim (with the exact number) and the source quote it relies on. Sources must already
    exist (add_source); check_receipts later verifies the quote against the stored source text."""
    tt.agent(agent); return tt.claim(agent, text, value, sources, quote)
@mcp.tool()
def register_artifact(agent: str, id: str, kind: str, title: str, derived_from: list[str], url: str = "", reach: int = 0, owner: str = "") -> str:
    """Record an output, which claims/artifacts it was built from (DERIVED_FROM), and its recall metadata: public url, estimated reach, owner."""
    tt.agent(agent); return tt.artifact(agent, id, kind, title, derived_from, url=url or None, reach=reach, owner=owner or None)
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
def requeue_tainted() -> list[dict]:
    """Create redo tasks for tainted artifacts, owned by the agent that produced them. Task id is stable:
    'redo-<artifact id>', usable with start_session, hand_off and complete_task. Idempotent."""
    return tt.requeue()
@mcp.tool()
def claim_risk() -> list[dict]:
    """Graph algorithm (PageRank over DERIVED_FROM): rank claims by how load-bearing they are, with how many
    artifacts and how much published reach sit downstream. Audit the top ones first."""
    return tt.risk()
@mcp.tool()
def chokepoints(k: int = 5) -> list[dict]:
    """Graph algorithm (betweenness centrality): artifacts that the most dependency paths run through."""
    return tt.chokepoints(k)
@mcp.tool()
def why_shortest(artifact: str) -> list[dict]:
    """Shortest DERIVED_FROM path from an artifact back to each corrected/refuted claim, with the exact source quote."""
    return tt.why_shortest(artifact)
@mcp.tool()
def draft_recall_memo(owner: str, text: str, author: str = "RecallAgent") -> str:
    """Store a recall memo for one owner in the graph, linked to the open redo tasks they own."""
    return tg.memo(owner, text, author)
@mcp.tool()
def why_tainted(artifact: str) -> list[dict]:
    return tt.why(artifact)
@mcp.tool()
def trust_ledger() -> list[dict]:
    return tt.trust()

if __name__ == "__main__": mcp.run()
