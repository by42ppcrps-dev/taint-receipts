"""Retake s01 (Puck) — several takes; key from env, never printed."""
import json, os, sys, base64, urllib.request, wave
KEY = os.environ["LUMEGRID_GEMINI_API_KEY"]; API = "https://generativelanguage.googleapis.com/v1beta/interactions"
STYLE = "calm, confident product-demo narrator; clear and warm; say the whole sentence in one continuous breath with no pause before the final number"
TEXT = "Our research bot read three point five hours as thirty-five."
for i in range(int(sys.argv[1])):
    body = {"model": "gemini-3.8-flash-tts", "input": [{"type": "user_input", "content": [{"type": "text", "text": TEXT,
            "annotations": [{"type": "speech_metadata", "style": STYLE}]}]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": "Puck"}]}}
    r = urllib.request.Request(API, json.dumps(body).encode(), {"x-goog-api-key": KEY, "Content-Type": "application/json"})
    try: j = json.load(urllib.request.urlopen(r, timeout=300))
    except urllib.error.HTTPError as e: sys.exit(f"HTTP {e.code} {e.read().decode()[:300]}")
    a = [c for s in j.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
    raw = base64.b64decode(a[-1]["data"]); out = f"audio/retake/s01.t{i}.wav"
    if raw[:4] == b"RIFF": open(out, "wb").write(raw)
    else:
        with wave.open(out, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(raw)
    print(out, flush=True)
