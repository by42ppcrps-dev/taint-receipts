"""Gemini TTS (paid key, env LUMEGRID_GEMINI_API_KEY). Style is a separate speech_metadata field, never in the spoken text."""
import json, os, sys, base64, urllib.request, wave, io, time
KEY = os.environ["LUMEGRID_GEMINI_API_KEY"]; API = "https://generativelanguage.googleapis.com/v1beta/interactions"
STYLE = "calm, confident product-demo narrator; clear and warm, slight urgency on reveals"
for sid, text in json.load(open("lines.json")):
    out = f"audio/{sid}.wav"
    if os.path.exists(out): continue
    body = {"model": "gemini-3.8-flash-tts", "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": STYLE}]}]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": "Puck"}]}}
    r = urllib.request.Request(API, json.dumps(body).encode(), {"x-goog-api-key": KEY, "Content-Type": "application/json"})
    try: j = json.load(urllib.request.urlopen(r, timeout=300))
    except urllib.error.HTTPError as e: sys.exit(f"{sid} HTTP {e.code} {e.read().decode()[:300]}")
    a = [c for s in j.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
    if not a: sys.exit(f"{sid} no audio")
    raw = base64.b64decode(a[-1]["data"]); mime = a[-1].get("mime_type", a[-1].get("mimeType", ""))
    if raw[:4] == b"RIFF": open(out, "wb").write(raw)
    else:
        with wave.open(out, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(raw)
    print(sid, mime, len(raw), flush=True); open("tts-calls.log", "a").write(json.dumps({"ts": time.time(), "sid": sid}) + "\n")
