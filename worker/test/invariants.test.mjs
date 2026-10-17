// Structural invariants: only cypher.js/falkor.js talk to the database; every run() key is registered.
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert";
const dir = new URL("../src/", import.meta.url);
const keys = new Set();
for (const f of readdirSync(dir).filter(f => f.endsWith(".js"))) {
  const s = readFileSync(new URL(f, dir), "utf8");
  if (!["cypher.js", "falkor.js"].includes(f)) assert.ok(!/\.query\(/.test(s), `${f} calls .query() directly; use run() from cypher.js`);
  for (const m of s.matchAll(/run\(db, [\w"]+, "(\w+)"/g)) keys.add(m[1]);
  if (f !== "cypher.js") assert.ok(!/`[^`]*\b(MATCH|MERGE|CREATE|DELETE)\b[^`]*\$\{/.test(s), `${f} builds Cypher with a template literal`);
}
const src = readFileSync(new URL("cypher.js", dir), "utf8").replace(/^import .*$/m, "");
const { QUERY_KEYS } = await import("data:text/javascript," + encodeURIComponent(readFileSync(new URL("queries.js", dir), "utf8") + src.replace(/export /g, "") + "\nexport { QUERY_KEYS };"));
for (const k of keys) assert.ok(QUERY_KEYS.includes(k), `unregistered query key ${k}`);
console.log(`invariants ok (${keys.size} query keys used)`);
