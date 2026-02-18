# CLAUDE.md — Project Contract

**Purpose**: Follow this in every session for this repo. Keep memory sharp. Keep outputs concrete. Cut rework.

---

## What This App Is

Single-file drag-and-drop web app that converts video (MP4, MOV, WEBM) to GIF.
All logic lives in `app.py` — Python HTTP server with embedded HTML/CSS/JS frontend.

## How to Run

```bash
python3 "/Users/bradleytangonan/Desktop/my apps/gif-maker/app.py"
```
- Auto-opens browser at **http://localhost:7878**
- Stop with `Ctrl+C`
- Port conflict: `kill $(lsof -ti :7878)`

## File Structure

```
gif-maker/
├── app.py        — entire app (server + frontend in one file)
├── output/       — generated GIFs saved here (auto-created on first run)
├── CLAUDE.md     — this file
└── claudedocs/   — session notes and analysis
```

## Stack

| Layer | Technology |
|-------|-----------|
| Server | Python `http.server` + `socketserver` (stdlib only, no Flask) |
| Frontend | Vanilla HTML/CSS/JS embedded as a string in `app.py` |
| Upload | Custom multipart/form-data parser (stdlib, no dependencies) |
| Job queue | In-memory `dict` + `threading.Thread` per job |
| GIF encoding | ffmpeg, Gifski, or libvips — user-selectable |
| Frame extraction | ffmpeg (all encoder paths) |
| Python bindings | `pyvips` (required for libvips encoder) |

## System Requirements

- Python 3.8+
- `ffmpeg` + `ffprobe` — `which ffmpeg`
- `gifski` — `which gifski`
- `vips` + `pyvips` — `which vips` / `python3 -c "import pyvips"`
- macOS (tested Darwin 24.x, Apple Silicon)
- All tools installed via Homebrew; pyvips via `pip3 install --break-system-packages pyvips`

## Architecture

```
Browser
  │ drag & drop video file
  │ POST /convert  (multipart/form-data)
  ▼
Handler.do_POST
  │ parse_multipart() — custom stdlib parser
  │ write video to tempfile
  │ spawn threading.Thread → run_conversion()
  │ return { job_id }
  ▼
run_conversion(job_id, params)
  │ jobs[job_id] = { status, step }   ← polled by frontend
  │
  ├── encoder == "gifski"
  │     gifski --fps --width -o output.gif input.mp4
  │     (trim via ffmpeg pre-pass if start/end set)
  │
  ├── encoder == "libvips"
  │     ffmpeg → PNG frames → pyvips.arrayjoin()
  │     set page-height + delay metadata → gifsave()
  │
  ├── encoder == "ffmpeg-high"
  │     ffmpeg palettegen (pass 1) → paletteuse (pass 2)
  │
  └── encoder == "ffmpeg-med"
        ffmpeg single pass
  │
  └── ffprobe → gather width/height/frame count
      jobs[job_id] = { status: "done", url, size, ... }

Browser polls GET /status/<job_id> every 800ms
  → on "done": display preview img + Download button
```

## Encoders

| Encoder | Key | Mechanism |
|---------|-----|-----------|
| Gifski | `gifski` | Perceptual quantization via gifski binary |
| ffmpeg 2-pass | `ffmpeg-high` | palettegen + paletteuse with Bayer dithering |
| libvips | `libvips` | pyvips arrayjoin + cgif-backed gifsave |
| ffmpeg | `ffmpeg-med` | Single-pass ffmpeg |

## UI Controls

| Control | Values |
|---------|--------|
| FPS | 5–30 (slider) |
| Width | Original / 800 / 640 / 480 / 320px |
| Start / End | Seconds — trims the clip |
| Encoder | Gifski / ffmpeg (2-pass palette) / libvips / ffmpeg |
| Loop | Forever / Play once / Twice |

## Known Limitations

- Job state is in-memory — restarting the server clears all jobs
- Large uploads (>500MB) are held entirely in memory during parsing
- No job cancellation — a running ffmpeg/gifski process continues until done even if browser closes
- Output GIFs persist in `output/` indefinitely; no auto-cleanup

---

## 🧠 Project Memory (Chroma)
Use server `chroma`. Collection `gif_maker_memory`.

Log after any confirmed fix, decision, gotcha, or preference.

**Schema:**
- **documents**: 1–2 sentences. Under 300 chars.
- **metadatas**: `{ "type":"decision|fix|tip|preference", "tags":"comma,separated", "source":"file|PR|spec|issue" }`
- **ids**: stable string if updating the same fact.

### Chroma Calls
```javascript
// Create once:
mcp__chroma__chroma_create_collection { "collection_name": "gif_maker_memory" }

// Add:
mcp__chroma__chroma_add_documents {
  "collection_name": "gif_maker_memory",
  "documents": ["<text>"],
  "metadatas": [{"type":"<type>","tags":"a,b,c","source":"<src>"}],
  "ids": ["<stable-id>"]
}

// Query (start with 5; escalate only if <3 strong hits):
mcp__chroma__chroma_query_documents {
  "collection_name": "gif_maker_memory",
  "query_texts": ["<query>"],
  "n_results": 5
}
```

## 🔍 Retrieval Checklist Before Coding
1. Query Chroma for related memories.
2. Check repo files that match the task.
3. List open PRs or issues that touch the same area.
4. Only then propose changes.

## ⚡ Activation
Read this file at session start.
Then read `.chroma/context/*.md` (titles + first bullets) and list which ones you used.
Run `bin/chroma-stats.py` and announce: **Contract loaded. Using Chroma gif_maker_memory. Found [N] memories (by type ...).**

## 🧹 Session Hygiene
Prune to last 20 turns if context gets heavy. Save long outputs in `./backups/` and echo paths.

## 📁 Output Policy
For code, return unified diff or patchable files. For scripts, include exact commands and paths.

## 🛡️ Safety
No secrets in `.chroma` or transcripts. Respect rate limits. Propose batching if needed.