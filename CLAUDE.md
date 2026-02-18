# CLAUDE.md — Project Contract

**Purpose**: Follow this in every session for this repo. Keep memory sharp. Keep outputs concrete. Cut rework.

---

## 🚀 What This App Is & How to Run It

A single-file drag-and-drop web app that converts MP4 (and other video) to GIF.
No pip installs needed — uses Python stdlib + `ffmpeg`/`ffprobe` (installed via Homebrew).

### Run it
```bash
python3 "/Users/bradleytangonan/Desktop/my apps/gif-maker/app.py"
```
- Auto-opens browser at **http://localhost:7878**
- Stop with `Ctrl+C`
- If port is busy: `kill $(lsof -ti :7878)`

### File structure
```
gif-maker/
├── app.py        ← entire app (server + HTML/CSS/JS all in one file)
├── output/       ← generated GIFs land here (auto-created)
└── CLAUDE.md     ← this file
```

### Architecture in one paragraph
`app.py` is a Python `http.server` with an embedded HTML/JS frontend. The frontend POSTs the video as `multipart/form-data`. The server parses it, saves a temp file, and runs `ffmpeg` in a background thread (2-pass palette for high quality). The frontend polls `/status/<job_id>` every 800ms and shows the result GIF with a download button when done.

### System requirements
- Python 3.8+
- `ffmpeg` + `ffprobe` → verify: `which ffmpeg`
- macOS (tested Darwin 24.x, Apple Silicon)

### UI options
| Option | Values |
|--------|--------|
| FPS | 5–30 slider |
| Width | Original / 800 / 640 / 480 / 320px |
| Start / End | Seconds (trim clip) |
| Quality | High (2-pass palette) / Medium (fast) |
| Loop | Forever / Once / Twice |

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