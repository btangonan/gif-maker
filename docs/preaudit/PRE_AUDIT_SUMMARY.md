# GIF Maker — Pre-Audit Summary
**Date**: 2026-05-09 | **Prior**: 2026-04-03 (6/18) | **Overall Maturity**: 10/18 (56%)

---

## Maturity Scorecard

| Dimension | Score | Max | Evidence |
|-----------|-------|-----|----------|
| LOC Discipline | 0 | 3 | `app.py` is still a single-file app with embedded HTML/CSS/JS plus server/conversion logic. |
| Validation Coverage | 2 | 3 | Upload size, extension, MIME prefix, fps, width, encoder, loop, time range, duration, and estimated output frames are bounded. Actual media validation still relies on `ffprobe`/native decoders. |
| Secrets Hygiene | 3 | 3 | No credentials in repo. Mac mini launch uses local service plus Cloudflare Tunnel credentials outside repo. |
| State & Persistence | 1 | 3 | Job state and output GIFs are local/ephemeral. Cleanup loop and job cap exist, but restart loses active jobs/results. |
| Errors/Retry/Idem. | 2 | 3 | Frontend handles polling/network failures; server returns clear 400/413/503 errors. No retry/idempotency layer. |
| Testing / CI | 2 | 3 | Focused unit tests cover validation, loop mapping, clip limits, and conversion slot behavior. No CI yet. |

---

## Launch Judgment

The right launch shape is **Mac mini origin + Cloudflare Tunnel**, not Cloudflare Workers and not Render as the CPU host.

```text
browser -> Cloudflare -> cloudflared tunnel -> http://127.0.0.1:7878
```

The app needs native CPU-bound tools (`ffmpeg`, `gifski`, `libvips`). Cloudflare should expose and protect the local origin; it should not run the converter.

---

## Remaining Top Risks

### R1 — Ephemeral Local State
Active jobs and completed GIF metadata live in memory. Output GIFs live on local disk and are cleaned after TTL. A restart during conversion returns `unknown` to the browser.

### R2 — Multipart Uploads Are Buffered
The request body is still read into memory before being written to a temp file. This is acceptable for a single-conversion Mac mini launch with `MAX_UPLOAD_MB=95` and `MAX_CONCURRENT_CONVERSIONS=1`, but it should be revisited if traffic grows.

### R3 — Monolithic `app.py`
The single-file structure is maintainable enough for launch, but future changes should extract frontend/static files and encoder helpers once the live path is stable.

---

## Current Strengths

- Launch resource controls are explicit: upload cap, single conversion slot, max clip duration, and max output frame count.
- Subprocess inputs are allowlisted before reaching ffmpeg filter strings.
- Temp files and stale outputs are cleaned up.
- The default encoder is the reliable `ffmpeg-high` palette path; `libvips` and `gifski` remain optional.

---

## Next Work

1. Run the focused unit tests plus a real short-video smoke test on the Mac mini.
2. Install the app and Cloudflare Tunnel as persistent services.
3. Verify `https://gif.tangonan.dev/healthz` and one public conversion.
4. Only after launch, consider extracting the embedded frontend and adding CI.
