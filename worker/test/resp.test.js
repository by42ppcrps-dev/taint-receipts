import assert from "node:assert";
// stub cloudflare:sockets for node
import { register } from "node:module";
const { encode, parse, withParams } = await import("../src/falkor.js").catch(async () => {
  const src = (await import("node:fs")).readFileSync(new URL("../src/falkor.js", import.meta.url), "utf8").replace(/^import .*cloudflare:sockets.*$/m, "const connect=null;");
  return import("data:text/javascript," + encodeURIComponent(src));
});
const e = new TextEncoder();
assert.deepEqual(parse(e.encode("*2\r\n$3\r\nfoo\r\n:42\r\n"))[0], ["foo", 42]);
assert.equal(parse(e.encode("*2\r\n$3\r\nfoo\r\n")), null);
assert.equal(new TextDecoder().decode(encode(["PING"])), "*1\r\n$4\r\nPING\r\n");
assert.equal(withParams("RETURN $a", { a: 'x"y', b: ["s", 1] }), 'CYPHER a="x\\"y" b=["s",1] RETURN $a');
console.log("resp ok");
