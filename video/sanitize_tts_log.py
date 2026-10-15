"""Write tts-calls.public.jsonl from the local tts-calls.log, keeping ONLY each call's UTC time and scene id.
The local log is written by tts.py (one line per Gemini TTS call); it is kept out of the repo."""
import json, datetime as dt
rows = [json.loads(l) for l in open("tts-calls.log") if l.strip()]
with open("tts-calls.public.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps({"utc": dt.datetime.fromtimestamp(r["ts"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "scene": r["sid"]}) + "\n")
print(len(rows), "calls")
