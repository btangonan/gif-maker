#!/usr/bin/env python3
"""
GIF Maker — drag & drop MP4 → GIF converter
Run: python3 app.py
Then open: http://localhost:7878
"""

import http.server
import socketserver
import json
import os
import subprocess
import sys
import time
import threading
import uuid
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("PORT", 7878))
MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB
MAX_JOBS = 500
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Track job progress
jobs = {}
jobs_lock = threading.Lock()

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GIF Maker</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f0f13;
    color: #e8e8f0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }

  .app {
    width: 100%;
    max-width: 620px;
  }

  h1 {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 6px;
    letter-spacing: -0.02em;
  }

  .subtitle {
    color: #888;
    font-size: 0.85rem;
    margin-bottom: 28px;
  }

  /* Drop zone */
  .drop-zone {
    border: 2px dashed #333;
    border-radius: 14px;
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: #16161e;
    position: relative;
  }

  .drop-zone:hover, .drop-zone.drag-over {
    border-color: #7c5cfc;
    background: #1a1828;
  }

  .drop-zone.has-file {
    border-color: #5c9cfc;
    background: #131a28;
  }

  .drop-icon {
    display: none;
  }

  .drop-label {
    font-size: 1rem;
    font-weight: 500;
    margin-bottom: 6px;
  }

  .drop-hint {
    font-size: 0.8rem;
    color: #666;
  }

  .file-info {
    display: none;
    align-items: center;
    gap: 10px;
    font-size: 0.9rem;
  }

  .file-info.visible { display: flex; justify-content: center; }

  .file-name {
    font-weight: 600;
    color: #7cb4fc;
  }

  .file-size { color: #666; font-size: 0.8rem; }

  input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  /* Options */
  .options {
    background: #16161e;
    border-radius: 14px;
    padding: 20px;
    margin-top: 16px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .option-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .option-group.full { grid-column: 1 / -1; }

  label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  select, input[type="number"] {
    background: #0f0f13;
    border: 1px solid #2a2a35;
    color: #e8e8f0;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 0.9rem;
    width: 100%;
    outline: none;
    transition: border-color 0.15s;
  }

  select:focus, input[type="number"]:focus {
    border-color: #7c5cfc;
  }

  .time-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .time-row input { width: 100%; }

  /* Slider row */
  .slider-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .slider-row input[type="range"] {
    flex: 1;
    -webkit-appearance: none;
    height: 4px;
    background: #2a2a35;
    border-radius: 2px;
    border: none;
    padding: 0;
    cursor: pointer;
  }

  .slider-row input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #7c5cfc;
    cursor: pointer;
  }

  .slider-val {
    font-size: 0.85rem;
    font-weight: 600;
    color: #7c5cfc;
    min-width: 36px;
    text-align: right;
  }

  /* Convert button */
  .convert-btn {
    width: 100%;
    margin-top: 16px;
    padding: 14px;
    background: #7c5cfc;
    color: #fff;
    border: none;
    border-radius: 10px;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
    letter-spacing: 0.01em;
  }

  .convert-btn:hover { background: #6a48f0; }
  .convert-btn:active { transform: scale(0.98); }
  .convert-btn:disabled { background: #333; color: #666; cursor: not-allowed; }

  /* Progress */
  .progress-section {
    display: none;
    margin-top: 16px;
    background: #16161e;
    border-radius: 14px;
    padding: 20px;
  }

  .progress-section.visible { display: block; }

  .progress-label {
    font-size: 0.85rem;
    color: #999;
    margin-bottom: 10px;
  }

  .progress-bar-wrap {
    background: #0f0f13;
    border-radius: 6px;
    height: 8px;
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, #7c5cfc, #5c9cfc);
    border-radius: 6px;
    width: 0%;
    transition: width 0.3s;
  }

  .progress-bar.indeterminate {
    width: 40% !important;
    animation: slide 1.2s ease-in-out infinite;
  }

  @keyframes slide {
    0%   { margin-left: -40%; }
    100% { margin-left: 100%; }
  }

  /* Result */
  .result-section {
    display: none;
    margin-top: 16px;
    background: #16161e;
    border-radius: 14px;
    padding: 20px;
    text-align: center;
  }

  .result-section.visible { display: block; }

  .result-section img {
    max-width: 100%;
    max-height: 320px;
    border-radius: 8px;
    margin-bottom: 14px;
    border: 1px solid #2a2a35;
  }

  .result-meta {
    font-size: 0.8rem;
    color: #666;
    margin-bottom: 14px;
  }

  .download-btn {
    display: inline-block;
    padding: 10px 24px;
    background: #1e3a5f;
    color: #7cb4fc;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    transition: background 0.15s;
    border: 1px solid #2a4a7f;
  }

  .download-btn:hover { background: #25487a; }

  .error-msg {
    color: #fc5c7c;
    font-size: 0.85rem;
    margin-top: 8px;
  }

  .reset-btn {
    background: none;
    border: 1px solid #333;
    color: #888;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 0.82rem;
    cursor: pointer;
    margin-top: 10px;
    transition: all 0.15s;
  }

  .reset-btn:hover { border-color: #555; color: #ccc; }
</style>
</head>
<body>
<div class="app">
  <h1>GIF Maker</h1>
  <p class="subtitle">Convert MP4 to GIF — drop a file and go</p>

  <!-- Drop Zone -->
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="video/mp4,video/*">
    <span class="drop-icon" id="dropIcon"></span>
    <div class="drop-label" id="dropLabel">Drop MP4 here or click to browse</div>
    <div class="drop-hint" id="dropHint">.mp4, .mov, .webm supported</div>
    <div class="file-info" id="fileInfo">
      <span class="file-name" id="fileName"></span>
      <span class="file-size" id="fileSize"></span>
    </div>
  </div>

  <!-- Options -->
  <div class="options">
    <div class="option-group">
      <label>FPS</label>
      <div class="slider-row">
        <input type="range" id="fps" min="5" max="30" step="1" value="15">
        <span class="slider-val" id="fpsVal">15</span>
      </div>
    </div>

    <div class="option-group">
      <label>Width</label>
      <select id="width">
        <option value="original">Original</option>
        <option value="800">800px</option>
        <option value="640" selected>640px</option>
        <option value="480">480px</option>
        <option value="320">320px</option>
      </select>
    </div>

    <div class="option-group">
      <label>Start (sec)</label>
      <input type="number" id="startTime" placeholder="0" min="0" step="0.1">
    </div>

    <div class="option-group">
      <label>End (sec)</label>
      <input type="number" id="endTime" placeholder="full" min="0" step="0.1">
    </div>

    <div class="option-group">
      <label>Encoder</label>
      <select id="encoder">
        <option value="ffmpeg-high" selected>ffmpeg (2-pass palette)</option>
        <option value="libvips">libvips</option>
        <option value="ffmpeg-med">ffmpeg</option>
      </select>
    </div>

    <div class="option-group">
      <label>Loop</label>
      <select id="loop">
        <option value="0" selected>Forever</option>
        <option value="1">Play once</option>
        <option value="2">Twice</option>
      </select>
    </div>
  </div>

  <button class="convert-btn" id="convertBtn" disabled>Select a video first</button>

  <!-- Progress -->
  <div class="progress-section" id="progressSection">
    <div class="progress-label" id="progressLabel">Converting…</div>
    <div class="progress-bar-wrap">
      <div class="progress-bar indeterminate" id="progressBar"></div>
    </div>
  </div>

  <!-- Result -->
  <div class="result-section" id="resultSection">
    <img id="resultGif" src="" alt="Result GIF">
    <div class="result-meta" id="resultMeta"></div>
    <a class="download-btn" id="downloadBtn" href="#" download>Download GIF</a>
    <br>
    <button class="reset-btn" id="resetBtn">Make another</button>
  </div>
</div>

<script>
let selectedFile = null;
let jobId = null;
let pollTimer = null;

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const dropIcon = document.getElementById('dropIcon');
const dropLabel = document.getElementById('dropLabel');
const dropHint = document.getElementById('dropHint');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const convertBtn = document.getElementById('convertBtn');
const progressSection = document.getElementById('progressSection');
const progressLabel = document.getElementById('progressLabel');
const progressBar = document.getElementById('progressBar');
const resultSection = document.getElementById('resultSection');
const resultGif = document.getElementById('resultGif');
const resultMeta = document.getElementById('resultMeta');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');

const fps = document.getElementById('fps');
const fpsVal = document.getElementById('fpsVal');
fps.addEventListener('input', () => fpsVal.textContent = fps.value);

// Drag & drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});

function setFile(file) {
  selectedFile = file;
  dropZone.classList.add('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = 'none';
  dropHint.style.display = 'none';
  fileInfo.classList.add('visible');
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert to GIF →';
  resultSection.classList.remove('visible');
}

function formatBytes(b) {
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/(1024*1024)).toFixed(1) + ' MB';
}

// Convert
convertBtn.addEventListener('click', async () => {
  if (!selectedFile) return;

  convertBtn.disabled = true;
  convertBtn.textContent = 'Converting…';
  progressSection.classList.add('visible');
  progressLabel.textContent = 'Uploading video…';
  progressBar.classList.add('indeterminate');
  resultSection.classList.remove('visible');

  const formData = new FormData();
  formData.append('video', selectedFile);
  formData.append('fps', fps.value);
  formData.append('width', document.getElementById('width').value);
  formData.append('start', document.getElementById('startTime').value || '');
  formData.append('end', document.getElementById('endTime').value || '');
  formData.append('encoder', document.getElementById('encoder').value);
  formData.append('loop', document.getElementById('loop').value);

  try {
    const res = await fetch('/convert', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    jobId = data.job_id;
    progressLabel.textContent = 'Converting… (this may take a moment)';
    pollJob();
  } catch(e) {
    showError(e.message);
  }
});

function pollJob() {
  pollTimer = setInterval(async () => {
    const res = await fetch('/status/' + jobId);
    const data = await res.json();

    if (data.status === 'done') {
      clearInterval(pollTimer);
      showResult(data);
    } else if (data.status === 'error') {
      clearInterval(pollTimer);
      showError(data.error);
    } else {
      if (data.step) progressLabel.textContent = data.step;
    }
  }, 800);
}

function showResult(data) {
  progressSection.classList.remove('visible');
  resultSection.classList.add('visible');
  resultGif.src = data.url + '?t=' + Date.now();
  const encoderLabel = {'ffmpeg-high':'ffmpeg (2-pass)','libvips':'libvips','ffmpeg-med':'ffmpeg'}[data.encoder] || data.encoder;
  resultMeta.textContent = `${data.width}×${data.height} · ${data.size} · ${data.frames} frames · ${data.fps} fps · ${encoderLabel}`;
  downloadBtn.href = data.url;
  downloadBtn.download = data.filename;
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert Again';
}

function showError(msg) {
  progressSection.classList.remove('visible');
  // Clear any existing error before inserting a new one
  document.querySelectorAll('.error-msg').forEach(el => el.remove());
  const err = document.createElement('div');
  err.className = 'error-msg';
  err.textContent = msg;
  convertBtn.parentNode.insertBefore(err, convertBtn.nextSibling);
  convertBtn.disabled = false;
  convertBtn.textContent = 'Try Again';
  setTimeout(() => err.remove(), 8000);
}

resetBtn.addEventListener('click', () => {
  selectedFile = null;
  fileInput.value = '';
  dropZone.classList.remove('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = '';
  dropHint.style.display = '';
  fileInfo.classList.remove('visible');
  convertBtn.disabled = true;
  convertBtn.textContent = 'Select a video first';
  resultSection.classList.remove('visible');
  progressSection.classList.remove('visible');
});
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._send(200, "text/html", HTML.encode())

        elif path.startswith("/status/"):
            job_id = path.split("/")[-1]
            job = jobs.get(job_id, {"status": "unknown"})
            self._json(200, job)

        elif path.startswith("/output/"):
            fname = path.split("/")[-1]
            fpath = OUTPUT_DIR / fname
            if fpath.exists() and fpath.suffix == ".gif":
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/gif")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, "text/plain", b"Not found")
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/convert":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_UPLOAD_BYTES:
                self._json(413, {"error": f"File too large. Max upload is 150 MB."})
                return
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)

            job_id = str(uuid.uuid4())[:8]
            with jobs_lock:
                if len(jobs) >= MAX_JOBS:
                    oldest = list(jobs.keys())[:50]
                    for k in oldest:
                        jobs.pop(k, None)
                jobs[job_id] = {"status": "queued", "step": "Queued…"}

            # Parse multipart
            try:
                params = parse_multipart(body, content_type)
            except Exception as e:
                self._json(400, {"error": f"Upload parse error: {e}"})
                return

            self._json(200, {"job_id": job_id})

            # Run conversion in background thread
            t = threading.Thread(target=run_conversion, args=(job_id, params), daemon=True)
            t.start()

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self._send(code, "application/json", body)


def parse_multipart(body: bytes, content_type: str) -> dict:
    """Simple multipart/form-data parser."""
    import email
    from email import policy

    # Extract boundary
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break

    if not boundary:
        raise ValueError("No boundary found")

    result = {}
    delim = ("--" + boundary).encode()
    parts = body.split(delim)

    for part in parts[1:]:
        if part.strip() in (b"", b"--", b"--\r\n"):
            continue
        part = part.lstrip(b"\r\n")
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, content = part.split(b"\r\n\r\n", 1)
        # Strip exactly the trailing CRLF that precedes the next boundary marker
        if content.endswith(b"\r\n"):
            content = content[:-2]

        headers_str = headers_raw.decode("utf-8", errors="replace")
        name = None
        filename = None
        for line in headers_str.splitlines():
            if "Content-Disposition" in line:
                for seg in line.split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        name = seg[5:].strip('"')
                    elif seg.startswith("filename="):
                        filename = seg[9:].strip('"')

        if name:
            if filename:
                result[name] = {"filename": filename, "data": content}
            else:
                result[name] = content.decode("utf-8", errors="replace").strip()

    return result


def run_conversion(job_id: str, params: dict):
    import tempfile
    import shutil

    def update(step, **extra):
        jobs[job_id] = {"status": "running", "step": step, **extra}

    input_path = None
    palette_path = None
    frames_dir = None
    try:
        update("Saving uploaded video…")

        video_data = params.get("video")
        if not video_data or not isinstance(video_data, dict):
            raise ValueError("No video file received")

        suffix = Path(video_data["filename"]).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(video_data["data"])
            input_path = f.name

        # Options
        fps       = int(params.get("fps", "15"))
        width_opt = params.get("width", "640")
        start     = params.get("start", "").strip()
        end       = params.get("end", "").strip()
        encoder   = params.get("encoder", "ffmpeg-high")
        loop      = int(params.get("loop", "0"))

        output_name = f"{job_id}.gif"
        output_path = str(OUTPUT_DIR / output_name)

        # ffmpeg scale filter
        if width_opt == "original":
            scale = "scale=iw:ih"
        else:
            scale = f"scale={width_opt}:-2:flags=lanczos"
        vf_base = f"fps={fps},{scale}"

        # ffmpeg time-range args
        time_args = []
        if start:
            time_args += ["-ss", start]
        if end:
            if start:
                time_args += ["-t", str(float(end) - float(start))]
            else:
                time_args += ["-to", end]

        # ── libvips ───────────────────────────────────────────────────────────
        if encoder == "libvips":
            import glob as globmod
            frames_dir = tempfile.mkdtemp()
            update("Extracting frames…")
            frame_pattern = os.path.join(frames_dir, "frame%05d.png")
            extract_cmd = [
                "ffmpeg", "-y", *time_args,
                "-i", input_path,
                "-vf", vf_base,
                frame_pattern
            ]
            r = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(f"Frame extraction failed:\n{r.stderr[-800:]}")

            frames = sorted(globmod.glob(os.path.join(frames_dir, "frame*.png")))
            if not frames:
                raise RuntimeError("No frames extracted from video")

            update(f"Encoding {len(frames)} frames with libvips…")

            # Use pyvips to set page-height + delay metadata correctly.
            # The vips CLI arrayjoin → gifsave path fails when total stacked
            # height (frame_h × N) exceeds the GIF canvas limit of 65535px.
            # pyvips lets us set these fields explicitly before saving.
            import pyvips
            images = [pyvips.Image.new_from_file(f, access="sequential") for f in frames]
            joined = pyvips.Image.arrayjoin(images, across=1)
            delay_ms = max(10, round(1000 / fps))
            joined.set_type(pyvips.GValue.array_int_type, "delay", [delay_ms] * len(images))
            joined.set_type(pyvips.GValue.gint_type, "page-height", images[0].height)
            joined.set_type(pyvips.GValue.gint_type, "loop", loop)
            joined.gifsave(output_path, effort=7, dither=1.0)

        # ── ffmpeg high (2-pass palette) ──────────────────────────────────────
        elif encoder == "ffmpeg-high":
            update("Generating color palette…")
            palette_path = str(OUTPUT_DIR / f"{job_id}_palette.png")
            r = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", f"{vf_base},palettegen=stats_mode=diff", palette_path],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                raise RuntimeError(f"Palette generation failed:\n{r.stderr[-800:]}")

            update("Rendering GIF…")
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path, "-i", palette_path,
                 "-lavfi", f"{vf_base} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                 "-loop", str(loop), output_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"GIF conversion failed:\n{result.stderr[-800:]}")

        # ── ffmpeg standard ───────────────────────────────────────────────────
        else:
            update("Rendering GIF…")
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", vf_base, "-loop", str(loop), output_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"GIF conversion failed:\n{result.stderr[-800:]}")

        # ── Gather output info ────────────────────────────────────────────────
        gif_bytes = os.path.getsize(output_path)
        size_str = f"{gif_bytes/1024:.0f} KB" if gif_bytes < 1024*1024 else f"{gif_bytes/1024/1024:.1f} MB"

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-count_packets",
             "-show_entries", "stream=width,height,nb_read_packets",
             "-of", "csv=p=0", output_path],
            capture_output=True, text=True
        )
        w, h, frames_count = "?", "?", "?"
        parts_out = probe.stdout.strip().split(",")
        if len(parts_out) >= 2:
            w, h = parts_out[0], parts_out[1]
        if len(parts_out) >= 3 and parts_out[2].strip():
            frames_count = parts_out[2].strip()

        jobs[job_id] = {
            "status": "done",
            "url": f"/output/{output_name}",
            "filename": output_name,
            "size": size_str,
            "width": w,
            "height": h,
            "frames": frames_count,
            "fps": fps,
            "encoder": encoder,
        }

    except Exception as e:
        jobs[job_id] = {"status": "error", "error": str(e)}
    finally:
        if input_path and os.path.exists(input_path):
            try: os.unlink(input_path)
            except OSError: pass
        if palette_path and os.path.exists(palette_path):
            try: os.unlink(palette_path)
            except OSError: pass
        if frames_dir and os.path.exists(frames_dir):
            try: shutil.rmtree(frames_dir)
            except OSError: pass


class GifMakerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Thread-per-request server so status polling doesn't block uploads."""
    allow_reuse_address = True
    daemon_threads = True


def _cleanup_loop():
    """Background thread: delete GIFs and job entries older than 1 hour."""
    while True:
        time.sleep(1800)  # run every 30 minutes
        cutoff = time.time() - 3600
        for fpath in list(OUTPUT_DIR.iterdir()):
            if fpath.suffix == ".gif":
                try:
                    if fpath.stat().st_mtime < cutoff:
                        fpath.unlink()
                except OSError:
                    pass
        with jobs_lock:
            stale = [k for k, v in list(jobs.items())
                     if isinstance(v, dict) and v.get("status") in ("done", "error")]
            for k in stale[:-100]:  # keep last 100 completed
                jobs.pop(k, None)


def main():
    threading.Thread(target=_cleanup_loop, daemon=True).start()

    print(f"\n  GIF Maker running at http://0.0.0.0:{PORT}")
    is_local = sys.stdout.isatty()
    if is_local:
        import webbrowser
        print(f"  Press Ctrl+C to stop\n")
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    try:
        with GifMakerServer(("", PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n  Stopped.")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n  Port {PORT} is already in use.")
            print(f"  Try: lsof -ti :{PORT} | xargs kill\n")
        else:
            raise


if __name__ == "__main__":
    main()
