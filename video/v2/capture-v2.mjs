// Records the LIVE demo (real Gemini agent runs over MCP against FalkorDB Cloud) for the v2 video.
// x11grab of a kiosk Chrome on Xvfb :91 -> raw/ui.mkv (30 fps, wall-clock timestamps); marks (seconds since start) -> marks.json; add marks.offset for video time.
import puppeteer from "puppeteer-core"; import fs from "fs";
const BASE = process.env.BASE || "https://taint-receipts.lumegridai.workers.dev";
import { spawn } from "child_process";
const b = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome", headless: false, defaultViewport: null, ignoreDefaultArgs: ["--enable-automation"],
  args: ["--no-sandbox", "--hide-scrollbars", "--kiosk", "--window-position=0,0", "--window-size=1920,1080", "--no-first-run", "--disable-infobars", "--force-device-scale-factor=1"], env: { ...process.env, DISPLAY: ":91" } });
const p = (await b.pages())[0] || await b.newPage();
const errs = []; p.on("pageerror", e => errs.push(String(e))); p.on("console", m => m.type() === "error" && errs.push(m.text()));

await p.goto(BASE, { waitUntil: "networkidle0" });
await p.addStyleTag({ content: `#side{width:640px;font-size:18px;padding:22px}#side h1{font-size:32px}#side small{font-size:15px}#banner{font-size:14px}
 #side button{font-size:17px;padding:12px}#trace{font-size:16px;max-height:56vh}#trace .res{max-height:2.8em}#side h2{font-size:15px}pre{font-size:14px;max-height:30vh;overflow:hidden}#gtext{display:none}#recall{font-size:15px}#recall table{font-size:15px}` });
await new Promise(r => setTimeout(r, 1500));
const ff = spawn("ffmpeg", ["-y", "-loglevel", "info", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "30", "-video_size", "1920x1080", "-use_wallclock_as_timestamps", "1", "-i", ":91.0+0,0",
  "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p", "raw/ui.mkv"], { stdio: ["pipe", "ignore", "pipe"] });
let fflog = ""; ff.stderr.on("data", d => fflog += d); await new Promise(r => setTimeout(r, 1500));
const W = ms => new Promise(r => setTimeout(r, ms)); const marks = {}; const t = () => (Date.now() - start) / 1000; const start = Date.now(); const startEpoch = start / 1000;
const btn = async txt => { const [el] = await p.$$(`xpath/.//button[contains(., "${txt}")]`); await el.hover(); await W(350); await el.click(); };
const idle = async () => { await p.waitForFunction(() => ![...document.querySelectorAll("#side button")].some(b => b.disabled), { timeout: 90000, polling: 100 }); };
async function agentRun(label, txt) {
  await p.evaluate(() => { document.getElementById("trace").innerHTML = ""; }); marks[label] = t(); await btn(txt); await p.evaluate(() => document.getElementById("h2a")?.scrollIntoView());
  const steps = []; let n = 0;
  while (true) { const s = await p.evaluate(() => ({ n: document.querySelectorAll("#tl li").length, done: ![...document.querySelectorAll("#side button")].some(b => b.disabled), tag: document.querySelector("#trace .tag")?.textContent || "", tools: [...document.querySelectorAll("#tl li code")].map(c => c.textContent) }));
    if (s.n > n) { for (let i = n; i < s.n; i++) steps.push([s.tools[i], t()]); n = s.n; }
    if (s.done) { marks[label + "_steps"] = steps; marks[label + "_tag"] = s.tag; break; } await W(100); }
  marks[label + "_done"] = t();
}
await W(1500); marks.load = t();
await btn("1 · Reset"); await idle(); marks.reset = t(); await W(9000);
marks.correct = t(); await btn("Correct “35 h”"); await idle(); await W(7000);
marks.why = t(); await btn("Why is the Short"); await idle(); await W(5000);
marks.recallbtn = t(); await btn("Recall plan (most"); await idle(); await p.evaluate(() => document.getElementById("recall").scrollIntoView({ block: "center" })); await W(6000);
await W(Math.max(0, 16500 - (Date.now() - start - marks.reset * 1000)));
await p.evaluate(() => document.getElementById("side").scrollTop = 0);
marks.reset2 = t(); await btn("1 · Reset"); await idle(); await W(2500);
await p.evaluate(() => { const h = [...document.querySelectorAll("#side h2")][0]; h.id = "h2a"; });
await agentRun("agent", "2 · Run RecallAgent"); await W(6000);
await W(17000); await p.evaluate(() => document.getElementById("side").scrollTop = 0); await W(1500);
await agentRun("reel", "3 · New session: Reel"); await W(6000);
await W(17000); await p.evaluate(() => document.getElementById("side").scrollTop = 0); await W(1500);
await agentRun("quill", "4 · New session: Quill"); await W(7000);
marks.end = t();
ff.stdin.write("q"); await new Promise(r => ff.on("close", r));
const m = fflog.match(/start: ([0-9.]+)/); marks.ff_start_epoch = m ? Number(m[1]) : null; marks.start_epoch = startEpoch;
marks.offset = m ? startEpoch - Number(m[1]) : null; // add to every mark to get video time
fs.writeFileSync("marks.json", JSON.stringify(marks, null, 1)); console.log(JSON.stringify(marks).slice(0, 1500)); console.log("ERRORS", JSON.stringify(errs)); await b.close();
