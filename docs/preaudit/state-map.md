# State & Persistence Map

## In-Memory State
- `jobs: dict` (module-level global, app.py:24)
  - Keyed by job_id (uuid4()[:8] — 8 hex chars)
  - Stores: status, step, url, filename, size, width, height, frames, fps, encoder, error
  - **Ephemeral**: wiped entirely on server restart

## Durable State
- GIF output files in `output/` directory
  - Created by run_conversion(), named `<job_id>.gif`
  - Palette temp file `<job_id>_palette.png` cleaned up in finally block
  - Temp frame dir (libvips path) cleaned up in finally block

## Risks
- Jobs lost on restart → client poll returns `{"status": "unknown"}` for stale IDs
- 8-char UUID has ~1/16M collision probability per 100k concurrent jobs (acceptable for local tool)
- No job eviction: `jobs` dict grows unbounded in long-running sessions
- No upload size limit: large videos load entirely into RAM before temp write

## Verdict
Score 0 — cross-request in-memory state with no persistence or idempotency keys
