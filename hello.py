try:
    from redislite.falkordb_client import FalkorDB; db=FalkorDB('/tmp/gh.db')
except ImportError:
    from falkordb import FalkorDB; db=FalkorDB(host='localhost',port=6379)
g=db.select_graph('team')
g.query("MERGE (a:Agent{name:'Nova'})-[:OWNS]->(t:Task{title:'Graph Hacks entry'}) MERGE (b:Agent{name:'Pika'})-[:HANDED_OFF]->(t)")
for r in g.query("MATCH (a:Agent)-[r]->(t:Task) RETURN a.name,type(r),t.title").result_set: print(r)
