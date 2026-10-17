"""Caption words = the display text below (script wording), timed from faster-whisper word timings (words.json) via difflib alignment."""
import json, re, difflib
DISPLAY = {
 "s01": "A research bot read 3.5 hours as 35.",
 "s02": "By the time anyone noticed, it was in a Short, two posts, the landing page, its preview image, and a waitlist email.",
 "s03": "Taint + Receipts keeps every claim, the source quote behind it, and everything shipped on top of it, in one FalkorDB graph.",
 "s04": "Then we hand it to an agent. Gemini only sees the world through MCP graph tools. It checks receipts, and uses PageRank to see how load-bearing the bad claim is.",
 "s05": "One correction, and FalkorDB walks every derived-from path, up to ten hops.",
 "s06": "It plans the recall, most-viewed first, and uses shortest path to show exactly why the Short is wrong, right down to the source line.",
 "s07": "Then it re-queues the fixes, and writes each owner a recall memo, stored in the graph.",
 "s08": "Next session. Reel starts with no memory but the graph. It finds its tasks and the memo, fixes the video and captions, and hands the script to Quill.",
 "s09": "Quill picks up Reel's handoff in its own fresh session. Memory and coordination live in the graph, not the chat.",
 "s10": "And the rules are enforced in code. Corrections need a receipt, the public MCP endpoint is read-only, and spend is capped.",
 "s11": "At 26,000 nodes and ten hops, the cascade takes under a millisecond.",
 "s12": "Taint + Receipts. One wrong number, every place it reached, fixed biggest audience first.",
}
norm = lambda w: re.sub(r"[^a-z0-9+]", "", w.lower().replace("plus", "+").replace("falcor", "falkor").replace("ten", "10"))
W = json.load(open("words.json")); out = {}
for sid, text in DISPLAY.items():
    asr = []
    for x in W[sid]:
        if asr and re.match(r"^[.,\-]", x["w"]): asr[-1] = {**asr[-1], "w": asr[-1]["w"] + x["w"], "e": x["e"]}
        else: asr.append(dict(x))
    disp = text.split()
    a = [norm(x["w"]) for x in asr]; d = [norm(x) for x in disp]
    t = [None] * len(disp)
    for blk in difflib.SequenceMatcher(None, d, a, autojunk=False).get_matching_blocks():
        for k in range(blk.size): t[blk.a + k] = (asr[blk.b + k]["s"], asr[blk.b + k]["e"])
    # unmatched display words: interpolate between neighbours
    t0, t1 = asr[0]["s"], asr[-1]["e"]
    for i in range(len(disp)):
        if t[i] is None:
            prev = next((t[j][1] for j in range(i - 1, -1, -1) if t[j]), t0)
            nj = next((j for j in range(i + 1, len(disp)) if t[j]), None)
            nxt = t[nj][0] if nj is not None else t1; gap = (nj if nj is not None else len(disp)) - i + 1
            s = prev + (nxt - prev) / gap; t[i] = (round(s, 2), round(s + (nxt - prev) / gap, 2))
    out[sid] = [{"w": w, "s": s, "e": e} for w, (s, e) in zip(disp, t)]
    miss = sum(1 for x in d if x not in a); print(sid, len(disp), "words,", miss, "interpolated-ish")
json.dump(out, open("captions.json", "w"), indent=0)
