# Development history and provenance

## Short version
- Graph Hacks build window opened **2026-10-14 18:31 UTC** (12:31 PM MDT; WeMakeDevs rules).
- Matt Brady approved entering at 13:58 MDT (team chat #2452, 19:58 UTC).
- First project file: `.venv/pyvenv.cfg`, created **14:00:13 MDT** (20:00:13 UTC). First commit **b22a141, 14:06:57 MDT (20:06:57 UTC)**. Both are about 1.5 hours after the window opened.
- The public repo is a **clean export** of our original local history. Its first commit (1ad5d7c) is dated **22:55:50 MDT** because that's when the export was made. It doesn't replay the earlier commits.

## Original local history (private repo, branch `master`)
Times are the commit times recorded by the box clock (MDT = UTC-6).

| Commit | MDT | UTC | What |
|---|---|---|---|
| b22a141 | 10-14 14:06:57 | 20:06:57 | First commit: FalkorDB provenance + correction cascade, MCP server, demo UI, 13 tests (14 files, 537 lines) |
| d761941 | 10-14 14:07:07 | 20:07:07 | Video plan + blog draft |
| b2e33e6 | 10-14 14:19:00 | 20:19:00 | Recall-plan framing: reach/owner/URL, 26k-node benchmark, related work |
| ec90cc8 | 10-14 14:26:24 | 20:26:24 | Fit graph view; Cloudflare Worker (RESP over TCP); video pipeline |
| 7688ce4 | 10-14 14:44:57 | 20:44:57 | Worker recall endpoint; deployed to taint-receipts.lumegridai.workers.dev |
| 91e2d94 | 10-14 14:45:02 | 20:45:02 | Recall-plan panel in UI; v2 videos |
| fb8e619 | 10-14 14:55:12 | 20:55:12 | v2 video retake |
| 46477a3 | 10-14 22:55:50 | 10-15 04:55:50 | README, MIT license, end card (v3 videos) |
| 39e0119 | 10-14 23:35:52 | 05:35:52 | QA fixes (Pika #2487/#2488) |
| 64f1ddf | 10-15 00:19:04 | 06:19:04 | v4 videos |
| c99510f | 10-15 00:39:51 | 06:39:51 | One MCP graph, artifact metadata, MCP integration test, hop-limit wording, v5 VO s06 |
| c864153 | 10-15 00:41:51 | 06:41:51 | Pika #2522 items 1–5: source text, stable task ids, graph config, stdio MCP test |
| (later) | | | Pika #2522 items 6–10: render inputs, rebuild doc, sanitized TTS log, this file |

`git log --format='%h %ad %cd %s' --date=iso-strict master` in the private history bundle (shared privately with QA) shows the same list. The reflog has one entry per commit, starting with `commit (initial)` for b22a141 at 14:06:57 -0600.

## How the public export maps to the original history
The public branch is a squash of `master`, made so the public repo doesn't carry the local TTS call log. Tree comparison (`git diff --stat <master> <public>`):

| Public commit | Original commit | Difference |
|---|---|---|
| 1ad5d7c (22:55:50) | 46477a3 | only `video/tts-calls.log` (left out) and one `.gitignore` line for it |
| e1eeae3 (23:35:52) | 39e0119 | same two files only |
| 09e0212 (00:39:51) | c99510f | the log, the `.gitignore` line, and four voice WAVs (s01/s02/s06/s07) that the export missed. It shipped the v3 takes, which don't match the v4/v5 render |
| next export | current `master` | none: the tree is identical (the local log is now untracked in `master` too, and the WAVs are fixed) |

## Other evidence, and its limits
- **Filesystem birth times** (ext4 `stat %w`): `.venv/pyvenv.cfg` 14:00:13, `hello.py` 14:00:57, `teamgraph/__init__.py` and `tests/test_teamgraph.py` 14:02:30, `.git/description` 14:06:57 MDT. No project file is older than 14:00 MDT.
- **Team chat (server timestamps, outside the box clock):** #2452 19:58 UTC, Matt approves entering. #2453 20:08 UTC, the build agent reports a FalkorDBLite prototype, MCP tools, demo UI and 13 tests under `ventures/hackathons/graph-hacks/`. That matches b22a141's 13 tests at 20:06:57 UTC. #2459 20:29 UTC, QA asks for timestamp checks. #2466 20:45 UTC, the earliest commit is reported as 20:06:57 UTC.
- **Gemini TTS calls:** `video/tts-calls.public.jsonl` puts the first voice call at 2026-10-14 20:10:24 UTC.
- **Limits:** git and file times come from the box's own clock and could in principle be set by whoever controls the box. Nothing was pushed to a public forge before the export, so no third-party commit timestamp exists for 14:06. The team-chat timestamps are the only evidence recorded off the box, and they bound the start to before 20:08 UTC.

## Who did what (provenance, narrowed to what we can show)
- **Build:** LumeGrid's Grok Bot agent (an AI agent) wrote the code, tests, docs, Worker and video pipeline on a Linux box. The local git history and the team-chat log record this.
- **Human role:** Matt Brady (LumeGrid founder) decided to enter, approved scope and the open-source licence, and controls publication (public push, submission). We **don't claim** a line-by-line human code review.
- **QA:** Pika, a second AI agent on the team, reviewed the bundle, UI, videos and docs in the team chat (#2487–#2522) and found the issues fixed in c99510f and later.
- **Voice:** Google Gemini TTS (`gemini-3.8-flash-tts`, voice Puck) via `video/tts.py`. **Captions:** faster-whisper. **Composition:** Remotion.
- Earlier README wording ("Cursor- and Grok-based agents", "a human reviewed the architecture, security and correctness") was broader than this evidence supports, and has been replaced.
