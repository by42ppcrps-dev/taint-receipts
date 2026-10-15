import json, glob
from faster_whisper import WhisperModel
m = WhisperModel("small.en", compute_type="int8"); out = {}
for f in sorted([f for f in glob.glob("audio/s*.wav") if "bad" not in f]):
    seg, _ = m.transcribe(f, word_timestamps=True)
    w = [{"w": x.word.strip(), "s": round(x.start, 2), "e": round(x.end, 2)} for s in seg for x in s.words]
    out[f.split("/")[-1][:3]] = w; print(f[-7:-4], " ".join(x["w"] for x in w))
json.dump(out, open("words.json", "w"))
