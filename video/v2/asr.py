import json, glob, subprocess
import numpy as np
from faster_whisper import WhisperModel
m = WhisperModel("small.en", compute_type="int8"); out = {}
for f in sorted(glob.glob("audio/s*.wav")):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    seg, _ = m.transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True)
    w = [{"w": x.word.strip(), "s": round(x.start, 2), "e": round(x.end, 2)} for s in seg for x in s.words]
    out[f.split("/")[-1][:3]] = w; print(f[-7:-4], " ".join(x["w"] for x in w))
json.dump(out, open("words.json", "w"))
