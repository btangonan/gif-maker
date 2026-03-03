# GIF Maker — Pre-Audit Summary
**Date**: 2026-02-18 | **Overall Maturity**: 4/18 (22%)

---

## Maturity Scorecard

| Dimension            | Score | Max | Evidence |
|----------------------|-------|-----|----------|
| LOC Discipline       | 0     | 3   | app.py = 919 LOC (3× limit) |
| Validation Coverage  | 0     | 3   | No schema validation on any inputs |
| Secrets Hygiene      | **3** | 3   | No credentials, clean codebase ✓ |
| State & Persistence  | 0     | 3   | jobs={} ephemeral, lost on restart |
| Errors/Retry/Idem.   | 1     | 3   | try/catch + cleanup; no retries |
| Testing / CI         | 0     | 3   | Zero tests, no CI |

---

## Top 3 Risks

### 🔴 R1 — app.py is 919 LOC (monolithic)
- HTML (330 lines) + CSS + JS + HTTP server + multipart parser + 4 encoder branches all in one file.
- SRP violated. Changes to UI require editing server code and vice versa.
- Hotspot: `run_conversion()` is 200 lines with 4 deeply nested encoder branches.

### 🔴 R2 — No input validation on /convert
- `fps`, `loop`, `start`, `end` raw-cast with `int()`/`float()` — ValueError caught by outer try but returns unhelpful error to user.
- `width` param flows directly into ffmpeg `-vf` filter string (path: app.py:724-728) — malformed value produces confusing ffmpeg error.
- No file size limit: large uploads load fully into RAM before temp write.
- No MIME type validation: any file accepted as "video".

### 🟡 R3 — jobs dict is ephemeral and unbounded
- Server restart clears all pending/running job state; client gets `{"status": "unknown"}` on stale poll.
- Dict never evicted: long-running server sessions accumulate all job records in memory.
- 8-char UUID collision risk negligible at local scale but no deduplication.

---

## Top 3 Strengths

### ✅ S1 — Zero secrets, clean hygiene
No credentials, no tokens, no .env needed. Entirely localhost. Score: 3/3.

### ✅ S2 — Solid temp file cleanup
`finally` block in `run_conversion()` reliably cleans input video, palette file, and frames directory across all encoder paths.

### ✅ S3 — Graceful degradation in encoder paths
Gifski trim has a copy-mode → re-encode fallback. Port 7878 uses `SO_REUSEADDR`. Browser auto-opens on start.

---

## 2-PR Minimum Fix Plan

### PR 1 — Split app.py into modules (LOC + SRP)
**Acceptance criteria**: No file >300 LOC; HTML/JS served from `static/` or `templates/`; server handler in `server.py`; conversion logic in `converter.py`.

```
app.py (entry) ~30 LOC
server.py      ~120 LOC  (Handler, routes, multipart parser)
converter.py   ~200 LOC  (run_conversion, encoder branches)
static/index.html ~330 LOC
```

### PR 2 — Add input validation + job TTL
**Acceptance criteria**: fps clamped 1-60; width allowlisted; start/end validated as non-negative floats ≤ video duration; encoder allowlisted to 4 known values; loop allowlisted {0,1,2}; upload size capped at 500MB; jobs dict evicted after 1hr TTL.

---

## Artifacts Generated
- `repo-shape.json`
- `file-inventory.json`
- `frameworks.json`
- `secrets-findings.json`
- `state-map.md`
- `error-surface.md`
- `maturity.json`
- `PRE_AUDIT_SUMMARY.md` ← this file
