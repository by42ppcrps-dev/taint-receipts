// Syntax-check the demo page's inline script (a broken page would otherwise only show up in a browser).
import { readFileSync } from "node:fs";
const s = readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");
const js = s.slice(s.lastIndexOf("<script>") + 8, s.lastIndexOf("</script>"));
new Function(js); console.log("html script ok");
