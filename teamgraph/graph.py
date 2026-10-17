"""TeamGraph core: all memory, handoffs and decision tracing live in FalkorDB."""
import os, time, uuid

DEFAULT_GRAPH = "teamgraph"   # override with $TEAMGRAPH_GRAPH (see README "Graphs")

def connect(graph=None):
    graph = graph or os.environ.get("TEAMGRAPH_GRAPH", DEFAULT_GRAPH)
    url = os.environ.get("FALKORDB_URL")
    if url:
        from falkordb import FalkorDB
        db = FalkorDB.from_url(url)
    else:
        from redislite.falkordb_client import FalkorDB
        db = FalkorDB(os.environ.get("TEAMGRAPH_DB", "/tmp/teamgraph.db"))
    return TeamGraph(db.select_graph(graph))

def _id(): return uuid.uuid4().hex[:10]

Q = {
 "agent": "MERGE (a:Agent {name:$name}) ON CREATE SET a.role=$role RETURN a.name",
 "episode": """MATCH (a:Agent {name:$agent}) CREATE (e:Episode {id:$id, text:$text, session:$session, ts:$ts})
   CREATE (a)-[:EXPERIENCED]->(e)
   WITH e OPTIONAL MATCH (t:Task {id:$task}) FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (e)-[:ABOUT]->(t)) RETURN e.id""",
 "fact": """MERGE (c:Concept {name:$subject}) MERGE (o:Concept {name:$object})
   CREATE (f:Fact {id:$id, predicate:$predicate, ts:$ts}) CREATE (c)-[:SUBJECT_OF]->(f)-[:OBJECT]->(o)
   WITH f OPTIONAL MATCH (s:Source {id:$source}) FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END | CREATE (f)-[:CITES]->(s)) RETURN f.id""",
 "procedure": """MERGE (p:Procedure {name:$name}) SET p.trigger=$trigger WITH p
   OPTIONAL MATCH (p)-[:STEP]->(old:Step) DETACH DELETE old WITH DISTINCT p
   UNWIND range(0, size($steps)-1) AS i CREATE (p)-[:STEP {order:i}]->(:Step {text:$steps[i], order:i}) RETURN p.name""",
 # One Source node per id. url and text are kept (an empty argument never wipes an earlier value),
 # so the taint tools' check_receipts can verify quotes against s.text in the same graph.
 "source": """MERGE (s:Source {id:$id}) SET s.title=$title,
   s.url=CASE WHEN $url = '' THEN s.url ELSE $url END, s.text=CASE WHEN $text = '' THEN s.text ELSE $text END
   RETURN s.id, s.url, s.text""",
 "task": """MERGE (t:Task {id:$id}) SET t.title=$title, t.status=coalesce(t.status,'open')
   WITH t MATCH (a:Agent {name:$owner}) MERGE (a)-[:OWNS]->(t) RETURN t.id""",
 "handoff": """MATCH (f:Agent {name:$from_agent})-[o:OWNS]->(t:Task {id:$task}) MATCH (to:Agent {name:$to_agent})
   DELETE o CREATE (to)-[:OWNS]->(t)
   CREATE (h:Handoff {id:$id, note:$note, ts:$ts}) CREATE (f)-[:GAVE]->(h)-[:TO]->(to) CREATE (h)-[:FOR]->(t) RETURN h.id""",
 "decision": """MATCH (a:Agent {name:$agent}) CREATE (d:Decision {id:$id, what:$what, why:$why, ts:$ts}) CREATE (a)-[:DECIDED]->(d)
   WITH d OPTIONAL MATCH (t:Task {id:$task}) FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (d)-[:FOR]->(t))
   WITH d UNWIND $sources AS sid MATCH (s:Source {id:sid}) CREATE (d)-[:BASED_ON]->(s) RETURN DISTINCT d.id""",
 "decision_nosrc": """MATCH (a:Agent {name:$agent}) CREATE (d:Decision {id:$id, what:$what, why:$why, ts:$ts}) CREATE (a)-[:DECIDED]->(d)
   WITH d OPTIONAL MATCH (t:Task {id:$task}) FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (d)-[:FOR]->(t)) RETURN d.id""",
 "supersede": "MATCH (n:Decision {id:$new}), (o:Decision {id:$old}) CREATE (n)-[:SUPERSEDES]->(o)",
 "why": """MATCH (a:Agent)-[:DECIDED]->(d:Decision) WHERE toLower(d.what) CONTAINS toLower($q)
   OPTIONAL MATCH (d)-[:BASED_ON]->(s:Source) OPTIONAL MATCH (d)-[:FOR]->(t:Task) OPTIONAL MATCH (d)-[:SUPERSEDES*1..5]->(prev:Decision)
   RETURN d.what, d.why, a.name, d.ts, collect(DISTINCT s.title + ' <' + s.url + '>'), t.title, collect(DISTINCT prev.what) ORDER BY d.ts DESC""",
 "recall": """MATCH (a:Agent)-[:EXPERIENCED]->(e:Episode) WHERE toLower(e.text) CONTAINS toLower($q)
   RETURN 'episode' AS kind, a.name AS who, e.text AS text, e.ts AS ts ORDER BY ts DESC LIMIT $k
   UNION MATCH (c:Concept)-[:SUBJECT_OF]->(f:Fact)-[:OBJECT]->(o:Concept)
   WHERE toLower(c.name) CONTAINS toLower($q) OR toLower(o.name) CONTAINS toLower($q)
   RETURN 'fact' AS kind, c.name AS who, f.predicate + ' ' + o.name AS text, f.ts AS ts ORDER BY ts DESC LIMIT $k""",
 "how": "MATCH (p:Procedure)-[r:STEP]->(s:Step) WHERE toLower(p.name) CONTAINS toLower($q) OR toLower(p.trigger) CONTAINS toLower($q) RETURN p.name, s.text ORDER BY p.name, r.order",
 "briefing": """MATCH (a:Agent {name:$agent})-[:OWNS]->(t:Task) WHERE t.status <> 'done'
   OPTIONAL MATCH (h:Handoff)-[:FOR]->(t) OPTIONAL MATCH (g:Agent)-[:GAVE]->(h)
   WITH t, h, g ORDER BY h.ts DESC WITH t, collect({from:g.name, note:h.note})[0] AS last
   RETURN t.id, t.title, t.status, last.from, last.note""",
 # Recall memo for one owner: linked to every open redo task that owner holds, so the next session finds it.
 "memo": """MATCH (a:Agent {name:$owner}) CREATE (m:Memo {id:$id, text:$text, author:$author, ts:$ts}) CREATE (a)-[:RECEIVED]->(m)
   WITH a, m OPTIONAL MATCH (a)-[:OWNS]->(t:Task) WHERE t.status <> 'done'
   FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | CREATE (m)-[:COVERS]->(t)) RETURN DISTINCT m.id""",
 "memos_for": "MATCH (a:Agent {name:$agent})-[:RECEIVED]->(m:Memo) RETURN m.author, m.text, m.ts ORDER BY m.ts DESC LIMIT 3",
 "episodes_for": "MATCH (a:Agent {name:$agent})-[:EXPERIENCED]->(e:Episode) RETURN e.session, e.text, e.ts ORDER BY e.ts DESC LIMIT 5",
 # Last agent who handed this task off (used to refuse hand-back ping-pong).
 "last_giver": "MATCH (g:Agent)-[:GAVE]->(h:Handoff)-[:FOR]->(:Task {id:$task}) RETURN g.name ORDER BY h.ts DESC LIMIT 1",
 "done": "MATCH (t:Task {id:$id}) SET t.status='done' RETURN t.id",
 "next_step": """MATCH (a:Agent {name:$agent})-[:OWNS]->(t:Task) WHERE t.status <> 'done'
   MATCH (p:Procedure)-[r:STEP]->(s:Step) WHERE toLower(t.title) CONTAINS toLower(p.trigger)
   OPTIONAL MATCH (t)<-[:ABOUT]-(e:Episode) WHERE toLower(e.text) CONTAINS toLower(s.text)
   WITH t, p, r, s, count(e) AS doneCount WHERE doneCount = 0
   RETURN t.title, p.name, s.text ORDER BY t.title, r.order LIMIT 1""",
}

class TeamGraph:
    def __init__(self, g): self.g = g
    def q(self, key, **p): return self.g.query(Q[key], p).result_set
    def setup(self):
        for lbl, prop in [("Agent","name"),("Task","id"),("Source","id"),("Decision","id"),("Concept","name"),("Procedure","name")]:
            try: self.g.query(f"CREATE INDEX FOR (n:{lbl}) ON (n.{prop})")
            except Exception: pass
    def agent(self, name, role=""): return self.q("agent", name=name, role=role)
    def episode(self, agent, text, session="s1", task=""): return self.q("episode", agent=agent, text=text, session=session, task=task, id=_id(), ts=time.time())[0][0]
    def fact(self, subject, predicate, obj, source=""): return self.q("fact", subject=subject, predicate=predicate, object=obj, source=source, id=_id(), ts=time.time())[0][0]
    def procedure(self, name, trigger, steps): return self.q("procedure", name=name, trigger=trigger, steps=steps)
    def source(self, id, title, url="", text=""): return self.q("source", id=id, title=title, url=url or "", text=text or "")
    def task(self, id, title, owner): return self.q("task", id=id, title=title, owner=owner)
    def handoff(self, from_agent, to_agent, task, note):
        if from_agent == to_agent: raise ValueError("cannot hand a task to yourself")
        last = self.q("last_giver", task=task)
        if last and last[0][0] == to_agent: raise ValueError(f"{to_agent} just handed {task} to you; complete it instead of handing it back")
        r = self.q("handoff", from_agent=from_agent, to_agent=to_agent, task=task, note=note, id=_id(), ts=time.time())
        if not r: raise ValueError(f"{from_agent} does not own task {task}")
        return r[0][0]
    def decide(self, agent, what, why, sources=(), task="", supersedes=""):
        did = _id(); key = "decision" if sources else "decision_nosrc"
        self.q(key, agent=agent, what=what, why=why, sources=list(sources), task=task, id=did, ts=time.time())
        if supersedes: self.q("supersede", new=did, old=supersedes)
        return did
    def why(self, q):
        return [dict(what=r[0], why=r[1], by=r[2], sources=[s for s in r[4] if s], task=r[5], replaced=r[6]) for r in self.q("why", q=q)]
    def recall(self, q, k=5): return [dict(kind=r[0], who=r[1], text=r[2]) for r in self.q("recall", q=q, k=k)]
    def how(self, q): return [r[1] for r in self.q("how", q=q)]
    def briefing(self, agent): return [dict(task=r[0], title=r[1], status=r[2], from_agent=r[3], note=r[4]) for r in self.q("briefing", agent=agent)]
    def memo(self, owner, text, author="RecallAgent"):
        r = self.q("memo", owner=owner, text=text, author=author, id=_id(), ts=time.time())
        if not r: raise ValueError(f"no agent {owner}")
        return r[0][0]
    def memos(self, agent): return [dict(author=r[0], text=r[1]) for r in self.q("memos_for", agent=agent)]
    def episodes(self, agent): return [dict(session=r[0], text=r[1]) for r in self.q("episodes_for", agent=agent)]
    def complete(self, task): return self.q("done", id=task)
    def next_step(self, agent):
        r = self.q("next_step", agent=agent)
        return dict(task=r[0][0], procedure=r[0][1], step=r[0][2]) if r else None
