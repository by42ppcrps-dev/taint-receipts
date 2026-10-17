"""MCP server: agents read/write TeamGraph memory over stdio. Arguments are validated by the typed signatures
(pydantic constraints from teamgraph.models) before any tool body runs."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer as FastMCP

from .graph import connect
from .models import AgentName, Id, OptId, OptName, Short, Text, Value
from .taint import Taint

# ONE graph for memory, handoffs and taint/receipts, so requeued redo tasks show up in start_session.
# Configure with $TEAMGRAPH_GRAPH (default "teamgraph"); FalkorDB via $FALKORDB_URL, else embedded at $TEAMGRAPH_DB.
GRAPH = os.environ.get("TEAMGRAPH_GRAPH", "teamgraph")
tg = connect(GRAPH)
tg.setup()
mcp = FastMCP("teamgraph")


@mcp.tool()
def remember_episode(agent: AgentName, text: Text, session: str = "s1", task: OptId = "") -> str:
    """Episodic memory: log what an agent did/saw."""
    tg.agent(agent)
    return tg.episode(agent, text, session, task)


@mcp.tool()
def learn_fact(subject: Short, predicate: Short, object: Short, source: str = "") -> str:
    """Semantic memory: store a subject-predicate-object fact, optionally citing a Source id."""
    return tg.fact(subject, predicate, object, source)


@mcp.tool()
def save_procedure(name: Short, trigger: Short, steps: list[str]) -> str:
    """Procedural memory: ordered steps used when a task title contains `trigger`."""
    tg.procedure(name, trigger, steps)
    return name


@mcp.tool()
def add_source(id: Id, title: Short, url: str = "", text: Text = "") -> str:
    """Add/update a Source in the shared graph. Keep `text` (the source wording): check_receipts verifies each
    claim's quote and number against it. A URL alone cannot be checked. Empty url/text never wipes a stored value."""
    tg.source(id, title, url, text)
    return id


@mcp.tool()
def create_task(id: Id, title: Short, owner: AgentName) -> str:
    tg.agent(owner)
    tg.task(id, title, owner)
    return id


@mcp.tool()
def hand_off(from_agent: AgentName, to_agent: AgentName, task: Id, note: Text) -> str:
    """Move task ownership and record the handoff note."""
    tg.agent(to_agent)
    try:
        return tg.handoff(from_agent, to_agent, task, note)
    except ValueError as e:
        return f"refused: {e}"  # the reason reaches the agent, so it can change course


@mcp.tool()
def record_decision(agent: AgentName, what: Short, why: Text, sources: list[Id] | None = None, task: OptId = "", supersedes: str = "") -> str:
    return tg.decide(agent, what, why, sources or [], task, supersedes)


@mcp.tool()
def why_did_we(question: Short) -> list[dict[str, Any]]:
    """Decision trace: who decided, why, sources, and what it replaced."""
    return tg.why(question)


@mcp.tool()
def recall(query: Short, k: int = 5) -> list[dict[str, Any]]:
    return tg.recall(query, k)


@mcp.tool()
def how_do_we(query: Short) -> list[str]:
    return tg.how(query)


@mcp.tool()
def start_session(agent: AgentName) -> dict[str, Any]:
    """Briefing from the graph for a fresh session: owned open tasks, last handoff notes, recall memos addressed
    to this agent, its own recent episodes from earlier sessions, and the next procedure step."""
    return {"tasks": tg.briefing(agent), "memos": tg.memos(agent), "episodes": tg.episodes(agent), "next": tg.next_step(agent)}


@mcp.tool()
def complete_task(task: Id) -> str:
    """Mark a task (e.g. 'redo-short') done; it drops out of start_session briefings."""
    if not tg.complete(task):
        raise ValueError(f"no task {task}")
    return task


tt = Taint(tg)  # same graph as the memory tools


@mcp.tool()
def assert_claim(agent: AgentName, text: Text, value: Value, sources: list[Id] | None = None, quote: str = "") -> str:
    """Record an atomic claim (with the exact number) and the source quote it relies on. Sources must already
    exist (add_source); check_receipts later verifies the quote against the stored source text."""
    tt.agent(agent)
    return tt.claim(agent, text, value, sources or [], quote)


@mcp.tool()
def register_artifact(agent: AgentName, id: Id, kind: Short, title: Short, derived_from: list[Id], url: str = "", reach: int = 0, owner: OptName = "") -> str:
    """Record an output, which claims/artifacts it was built from (DERIVED_FROM), and its recall metadata: public url, estimated reach, owner."""
    tt.agent(agent)
    return tt.artifact(agent, id, kind, title, derived_from, url=url or None, reach=reach, owner=owner or None)


@mcp.tool()
def check_receipts() -> list[dict[str, Any]]:
    """QA: refute claims whose number is not in the cited source, or that cite nothing."""
    return tt.receipts()


@mcp.tool()
def correct_claim(claim: Id, value: Value, reason: Short) -> list[dict[str, Any]] | str:
    """Fix a claim and taint every downstream artifact (multi-hop). Returns the blast radius.
    The new value must appear in the claim's cited quote."""
    try:
        return tt.correct(claim, value, reason)
    except ValueError as e:
        return str(e)


@mcp.tool()
def recall_plan() -> dict[str, Any]:
    """Recall plan for published content: tainted posts/Shorts/emails/images, most-viewed first, with owner, live URL, est. reach."""
    return tt.recall()


@mcp.tool()
def requeue_tainted() -> list[dict[str, Any]]:
    """Create redo tasks for tainted artifacts, owned by the agent that produced them. Task id is stable:
    'redo-<artifact id>', usable with start_session, hand_off and complete_task. Idempotent."""
    return tt.requeue()


@mcp.tool()
def claim_risk() -> list[dict[str, Any]]:
    """Graph algorithm (PageRank over DERIVED_FROM): rank claims by how load-bearing they are, with how many
    artifacts and how much published reach sit downstream. Audit the top ones first."""
    return tt.risk()


@mcp.tool()
def chokepoints(k: int = 5) -> list[dict[str, Any]]:
    """Graph algorithm (betweenness centrality): artifacts that the most dependency paths run through."""
    return tt.chokepoints(k)


@mcp.tool()
def why_shortest(artifact: Id) -> list[dict[str, Any]]:
    """Shortest DERIVED_FROM path from an artifact back to each corrected/refuted claim, with the exact source quote."""
    return tt.why_shortest(artifact)


@mcp.tool()
def draft_recall_memo(owner: AgentName, text: Text, author: AgentName = "RecallAgent") -> str:
    """Store a recall memo for one owner in the graph, linked to the open redo tasks they own."""
    return tg.memo(owner, text, author)


@mcp.tool()
def why_tainted(artifact: Id) -> list[dict[str, Any]]:
    return tt.why(artifact)


@mcp.tool()
def trust_ledger() -> list[dict[str, Any]]:
    return tt.trust()


if __name__ == "__main__":
    mcp.run()
