# Our bot read 3.5 as 35. A graph found every place it was published, biggest audience first.

*Draft for the Graph Hacks blog prize. The story and data are redacted or synthetic.*

We run a small team of AI agents that research, write, edit video and check each other's work. Last month a researcher bot read "3.5 hours" as "35 hours". Nothing crashed. The number just quietly became a brief, then a blog post, a landing-page hero, a link-preview image, a Short, its captions, and an email.

Fixing the number took one second. Finding everywhere it had been *published*, who owned each piece, and which ones the most people had seen was the real problem. That's a recall, so we built a recall system.

## The shape of the problem is a graph
Every output our agents make is built from earlier outputs, and those come from claims, which come from sources. "Everything downstream of this claim, at any depth" is a variable-length path query. That's a single Cypher pattern in FalkorDB, instead of a recursive query we'd have to write and tune ourselves.

So in Taint + Receipts, FalkorDB is the system of record for what our agents have claimed:
- `(:Agent)-[:ASSERTED]->(:Claim)-[:CITES {quote}]->(:Source)`
- `(:Artifact)-[:DERIVED_FROM]->(:Artifact|:Claim)`

## Receipts
Before anything ships, a QA agent checks receipts: the number in a claim must literally appear in the quote it cites. "35" doesn't appear in "Battery life: 3.5 hours", so the claim is refuted. "Trusted by 10,000 teams" cites nothing, so it's refuted too.

## Taint
```cypher
MATCH (bad:Claim {id:$id}) SET bad.status='corrected'
WITH bad MATCH p=(x:Artifact)-[:DERIVED_FROM*1..10]->(bad)
SET x.status='tainted' RETURN x.title, length(p)
```
Ten artifacts, up to four hops away, get tainted in one query. The FAQ, which never touched the claim, stays clean. Having no path counts as proof it's clean, not just a weaker similarity score.

## The recall plan: fix the most-viewed first
Every artifact node carries its owner, live URL and an estimated reach. After the cascade, one query returns the tainted items sorted by reach:
```cypher
MATCH (x:Artifact {status:'tainted'})<-[:PRODUCED]-(a:Agent)
RETURN x.title, x.reach, x.url, coalesce(x.owner, a.name) ORDER BY x.reach DESC
```
In the demo, the Short (~27k est. views) comes first and the X reply thread (~1.8k) comes last, and the plan totals the estimated audience that saw the wrong number.

## Does it hold up at scale?
We seeded 1,000 claims and 25,000 published artifacts (26,004 nodes, 51,099 edges, chains up to 10 hops) into embedded FalkorDB. The cascade query ran at about 0.55 ms median, and correcting a claim plus building the full recall plan took about 15 ms. That's one run on a shared box, and the script is in the repo so you can rerun it.

## Prior art
We're not the first to propagate corrections. **Memorant** flags everything derived from a corrected claim in agent memory. **Lattice** runs a "revocation waterfall" over a signed claim DAG. There's academic work on retraction propagation too. Our angle is narrower and more practical: shipped content across media, with owners, URLs and audience size, so a team knows what to fix first.

## Agents act on the graph
Tainted artifacts become redo tasks owned by the agent that produced them, and each agent's next step comes from the graph. "Why is the Short wrong?" returns the whole chain back to the source line. A trust ledger scores each agent on how often its claims hold up.

## Lessons
- Make claims atomic and give them their own nodes. Provenance at the artifact level is too coarse.
- Store the quote on the CITES edge. It turns "trust me" into a receipt you can check.
- Variable-length traversal is the feature, and FalkorDB is fast enough to run it on every agent step.
- Put reach on the node. A correction list sorted by audience is far more useful than an alphabetical one.
- Check prior art before claiming novelty. Naming Memorant and Lattice made our pitch sharper, not weaker.

Repo: _(link at submission)_. Tracks: Company Brain; Agent Memory and Coordination; Agents That Act on Connected Data.
