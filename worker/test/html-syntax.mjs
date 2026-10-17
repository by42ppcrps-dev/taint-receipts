// Syntax-check the demo page's inline script (a broken page would otherwise only show up in a browser).
import { readFileSync } from "node:fs";
import assert from "node:assert";
const s = readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");
const js = s.slice(s.lastIndexOf("<script>") + 8, s.lastIndexOf("</script>"));
new Function(js);
const csp = readFileSync(new URL("../../web/_headers", import.meta.url), "utf8");
assert.match(csp, /object-src 'none'/);
assert.match(csp, /script-src 'self' 'unsafe-inline' https:\/\/unpkg.com\/vis-network@9\.1\.9\/standalone\/umd\/vis-network\.min\.js/);
assert.ok(!/script-src[^;]* https:\/\/unpkg\.com;/.test(csp), "unpkg must be the pinned file, not the whole origin");
console.log("html script ok");
