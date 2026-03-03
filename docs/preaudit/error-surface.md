# Error Handling Analysis

## Structured Error Paths

### parse_multipart() → app.py:638
- Wrapped in try/except at call site (do_POST:614)
- Returns HTTP 400 with `{"error": "Upload parse error: <e>"}` on failure ✓

### run_conversion() → app.py:690
- Outer try/except catches all Exception
- Sets `jobs[job_id] = {"status": "error", "error": str(e)}` on failure ✓
- `finally` block cleans up temp files (input, palette, frames_dir) ✓

### Subprocess failures
- ffmpeg/gifski return codes checked → raise RuntimeError with stderr tail ✓
- Gifski trim has copy-mode fallback → re-encode fallback if copy fails ✓
- Timeout: 120s for palette/trim, 300s for conversion, 180s for frame extraction ✓

## Gaps

| Gap | Location | Risk |
|-----|----------|------|
| No file size limit on upload | do_POST:604-605 | Large files read fully into RAM |
| No MIME type validation | parse_multipart result | Any file accepted as "video" |
| fps/loop/start/end: raw int()/float() casts, no bounds checking | run_conversion:713-718 | ValueError on bad input, caught by outer try |
| width param: "original" or numeric string passed directly into ffmpeg -vf | run_conversion:724-728 | Malformed scale filter if unexpected value |
| jobs dict never evicted | app.py:24 | Memory leak in long-running sessions |
| pollJob() in frontend has no error handling on fetch() | app.py:514 | Network errors silently ignored |

## Error Format
- Backend: plain string errors (not Problem+JSON)
- Frontend: error div with text message, auto-dismisses after 8s

## Verdict
Score 1 — basic try/catch with good cleanup, no retries, no structured error format
