// Records the real UI (every click = a real Cypher call against FalkorDB) timed to the narration.
const { chromium } = require("playwright-core"); const fs = require("fs");
const D = require("./durations.json"); const PAD = 0.6;
const ACT = { s04: "reset", s05: "receipts", s06: "correct", s07: "recall", s08: null, s10: "why", s11: "requeue" };
(async () => {
  const b = await chromium.launch({ executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"] });
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: "raw", size: { width: 1920, height: 1080 } } });
  const p = await ctx.newPage(); const t0 = Date.now();
  await fetch("http://localhost:8787/api/reset", { method: "POST", body: "{}" });
  await p.goto("http://localhost:8787");
  await p.addStyleTag({ content: "#side{width:560px;font-size:20px}#side h1{font-size:34px}#side small{font-size:17px}button{font-size:19px;padding:15px}pre{font-size:16px}p{font-size:19px}" });
  await p.waitForTimeout(1500); const marks = {}; let t = 1.5;
  for (const s of Object.keys(ACT)) {
    marks[s] = (Date.now() - t0) / 1000;
    if (ACT[s]) { const btn = p.locator("button", { hasText: { reset: "Reset", receipts: "receipts", correct: "Correct", why: "Why", requeue: "Re-queue", recall: "Recall plan" }[ACT[s]] });
      await btn.hover(); await p.waitForTimeout(400); await btn.click(); }
    await p.waitForTimeout((D[s] + PAD) * 1000 - (ACT[s] ? 400 : 0));
  }
  marks.end = (Date.now() - t0) / 1000;
  const v = p.video(); await ctx.close(); fs.renameSync(await v.path(), "raw/ui.webm");
  fs.writeFileSync("marks.json", JSON.stringify(marks, null, 1)); await b.close(); console.log(marks);
})();
