# Rebuilding the demo videos (v5)

Every input to the v5 render is committed, and `RENDER-INPUTS.sha256` lists their hashes (`cd video && sha256sum -c RENDER-INPUTS.sha256`).

| Input | File(s) | Where it came from |
|---|---|---|
| Composition | `rm/src/Root.tsx`, `rm/src/Demo.tsx`, `rm/src/index.ts`, `rm/package.json`, `rm/tsconfig.json` | Remotion 4.0.535 (`Demo` 1920×1080, `Vertical` 1080×1920, 30 fps) |
| Narration text | `lines.json` (13 lines, s01–s13) | the text that was voiced |
| Voice segments | `audio/s01.wav` … `audio/s13.wav` (copied to `rm/public/`) | Gemini TTS via `tts.py` (voice Puck). s06 was re-voiced for v5 with "up to ten hops deep" |
| Segment lengths | `rm/src/durations.json` (= `durations.json`) | each WAV's duration in seconds |
| Captions | `rm/src/captions.json` (= `captions.json`) | word timings from faster-whisper `small.en` on the WAVs (`asr.py`) |
| Screen recording | `rm/public/ui.mp4` | `capture.cjs` (Playwright + Chrome) clicking the real UI against FalkorDB, converted from `raw/ui.webm` |
| Click timing | `rm/src/marks.json` (= `marks.json`) | written by `capture.cjs` during the recording |

## Re-render from the committed inputs
```bash
cd video
cp audio/s*.wav rm/public/                      # ui.mp4 is already in rm/public/
sha256sum -c RENDER-INPUTS.sha256
cd rm && npm i                                  # remotion / @remotion/cli 4.0.535, react 18
npx remotion render src/index.ts Demo out/h.mp4 --browser-executable=/usr/bin/google-chrome --timeout=120000
npx remotion render src/index.ts Vertical out/v.mp4 --browser-executable=/usr/bin/google-chrome --timeout=120000
```
Then normalize loudness (video stream copied, audio re-encoded):
```bash
ffmpeg -i out/h.mp4 -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null -     # pass 1: note measured_* values
ffmpeg -i out/h.mp4 -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=..:measured_TP=..:measured_LRA=..:measured_thresh=..:linear=true \
       -c:a aac -b:a 160k -ar 48000 h-final.mp4                                       # pass 2
```
The v5 finals measure -14.2 LUFS integrated and -1.7 dBFS peak (ffmpeg `ebur128=peak=true`), 93.0 s.

A re-render uses the same inputs, but the MP4 bytes won't be identical: Chrome frame capture and the x264/AAC encoders aren't bit-for-bit deterministic. To check a render, compare it with the inputs above, not the MP4 hash.

## Re-render the 9:16 cut (Shorts caption safe zone)

`Vertical` (1080×1920) burns captions in at `bottom: 386`, so the caption plate ends at or above y=1536. That is the bottom of the YouTube Shorts safe area (384px up, plus 2px so the rounded corner's antialiasing stays inside the line). The previous `bottom: 110` put the caption box at about y=1810, under the Shorts chrome. Callouts on that cut sit above the caption band. The 16:9 composition is unchanged (`bottom: 40`, full 7-row recall card).

The 9:16 recall card shows the **top 5** rows only: 73,700 synthetic est. reach, and 4 synthetic example URLs. It is not the full 7-row plan (that card is the 16:9 cut: 79,700 est. reach, 6 synthetic example URLs).

Re-render 9:16 from the committed inputs (voice, captions, and the screen recording are unchanged; only the composition moved):

```bash
cd video
cp audio/s*.wav rm/public/                      # ui.mp4 is already in rm/public/
sha256sum -c RENDER-INPUTS.sha256
cd rm && npm i                                  # remotion / @remotion/cli 4.0.535, react 18
npx remotion render src/index.ts Vertical out/v.mp4 --browser-executable=/usr/bin/google-chrome --timeout=120000
```

Then run the same two-pass `loudnorm` as above on `out/v.mp4`. A 16:9 file rendered before this change does not need a new render.

## Recreate the inputs from scratch (optional)
1. Voice: `export LUMEGRID_GEMINI_API_KEY=...` (your own key), delete the `audio/sNN.wav` you want to redo, then `python3 tts.py`. It voices each missing line of `lines.json` and appends `{ts, sid}` to the local `tts-calls.log` (not committed; `sanitize_tts_log.py` writes the committed `tts-calls.public.jsonl`, UTC time and scene id only). TTS output differs per call, so new WAVs won't match the committed ones.
2. Durations: write each WAV's duration (seconds, 2 dp) to `durations.json` and copy to `rm/src/`.
3. Captions: `python3 asr.py` (faster-whisper `small.en`) writes `words.json`; `captions.json` holds the per-scene word timings and is copied to `rm/src/`.
4. Screen recording: start the UI (`python -m teamgraph.web`, or `npx wrangler dev` in `worker/`, or set `BASE=` to the demo URL), then `node capture.cjs`. It resets the synthetic graph, clicks each button in time with the narration, and writes `raw/ui.webm` and `marks.json`. Convert with `ffmpeg -i raw/ui.webm -r 30 -c:v libx264 -crf 14 -pix_fmt yuv420p rm/public/ui.mp4` and copy `marks.json` to `rm/src/`. Call `POST /api/reset` on the demo afterwards.
