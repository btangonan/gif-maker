#!/usr/bin/env python3
"""
GIF Maker — drag & drop MP4 → GIF converter
Run: python3 app.py
Then open: http://localhost:7878
"""

import http.server
import socketserver
import json
import math
import os
import subprocess
import sys
import time
import threading
import uuid
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("PORT", 7878))
HOST = os.environ.get("HOST", "127.0.0.1")
# Cloudflare-proxied requests are commonly capped at 100 MB on Free/Pro plans.
# Keep the app default just below that; override with MAX_UPLOAD_MB for other hosts.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "95"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_JOBS = 500
MAX_CONCURRENT_CONVERSIONS = int(os.environ.get("MAX_CONCURRENT_CONVERSIONS", "1"))
MAX_DURATION_SECONDS = float(os.environ.get("MAX_DURATION_SECONDS", "30"))
MAX_OUTPUT_FRAMES = int(os.environ.get("MAX_OUTPUT_FRAMES", "900"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_MIME_PREFIXES = ("video/", "application/octet-stream")
ALLOWED_ENCODERS = {"gifski", "libvips", "ffmpeg-high", "ffmpeg-med"}
ALLOWED_WIDTHS = {"original", "800", "640", "480", "320"}
ALLOWED_LOOPS = {0, 1, 2}
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Track job progress
jobs = {}
jobs_lock = threading.Lock()
conversion_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CONVERSIONS)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GIF Maker</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="shortcut icon" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-primary: #0a0a0a;
    --bg-secondary: #141414;
    --bg-tertiary: #1a1a1a;
    --accent-primary: #c8ff00;
    --accent-secondary: #ff6b6b;
    --accent-success: #4ade80;
    --text-primary: #e4e4e7;
    --text-secondary: #a1a1aa;
    --text-muted: #71717a;
    --border-color: #2a2a2a;
    --cell-hover: rgba(200, 255, 0, 0.15);
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
    --radius: 8px;
    --transition: 0.2s ease;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 48px 24px 24px;
    overflow-x: hidden;
  }

  .app {
    width: 100%;
    max-width: 620px;
  }

  h1 {
    font-family: 'Inter', sans-serif;
    font-size: 2rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--accent-primary);
    margin-bottom: 6px;
  }

  .subtitle {
    color: var(--text-secondary);
    font-size: 0.95rem;
    font-weight: 400;
    margin-bottom: 28px;
  }

  /* Drop zone */
  .drop-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border: 2px dashed var(--border-color);
    border-radius: var(--radius);
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all var(--transition);
    background: var(--bg-secondary);
    position: relative;
  }

  .drop-zone:hover, .drop-zone.drag-over {
    border-color: var(--accent-primary);
    background: var(--cell-hover);
  }

  .drop-zone.has-file {
    border-color: var(--accent-primary);
    border-style: solid;
    background: var(--cell-hover);
  }

  .drop-icon {
    display: none;
  }

  .drop-label {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .drop-zone:hover .drop-label,
  .drop-zone.drag-over .drop-label {
    color: var(--accent-primary);
  }

  .drop-hint {
    font-size: 0.8rem;
    color: var(--text-muted);
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
    color: var(--accent-primary);
  }

  .file-size { color: var(--text-muted); font-size: 0.8rem; }

  input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  /* Options */
  .options {
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
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
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  select, input[type="number"] {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 0.9rem;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    width: 100%;
    outline: none;
    transition: border-color var(--transition);
  }

  select:focus, input[type="number"]:focus {
    border-color: var(--accent-primary);
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
    background: var(--border-color);
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
    background: var(--accent-primary);
    cursor: pointer;
  }

  .slider-val {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent-primary);
    min-width: 36px;
    text-align: right;
  }

  /* Convert button */
  .convert-btn {
    width: 100%;
    margin-top: 16px;
    padding: 14px;
    background: var(--accent-primary);
    color: var(--bg-primary);
    border: 1px solid var(--accent-primary);
    border-radius: var(--radius);
    font-family: 'Inter', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: all var(--transition);
    letter-spacing: 0.01em;
  }

  .convert-btn:hover:not(:disabled) { background: transparent; color: var(--accent-primary); }
  .convert-btn:active:not(:disabled) { transform: scale(0.98); }
  .convert-btn:disabled { background: var(--bg-tertiary); border-color: var(--border-color); color: var(--text-muted); cursor: not-allowed; }

  /* Progress */
  .progress-section {
    display: none;
    margin-top: 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    padding: 20px;
  }

  .progress-section.visible { display: block; }

  .progress-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 10px;
  }

  .progress-bar-wrap {
    background: var(--bg-primary);
    border-radius: 6px;
    height: 6px;
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-primary), var(--accent-success));
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
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    padding: 20px;
    text-align: center;
  }

  .result-section.visible { display: block; animation: flash-success 0.6s ease; }

  .result-section img {
    max-width: 100%;
    max-height: 320px;
    border-radius: 6px;
    margin-bottom: 14px;
    border: 1px solid var(--border-color);
  }

  .result-section img.checkerboard {
    background: repeating-conic-gradient(#e0e0e0 0% 25%, #fff 0% 50%) 0 0 / 16px 16px;
  }

  .result-meta {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 14px;
  }

  .download-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 24px;
    background: var(--accent-primary);
    color: var(--bg-primary);
    border-radius: var(--radius);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    transition: all var(--transition);
    border: 1px solid var(--accent-primary);
  }

  .download-btn:hover { background: transparent; color: var(--accent-primary); }

  .error-msg {
    color: var(--accent-secondary);
    font-size: 0.85rem;
    font-weight: 500;
    margin-top: 8px;
  }

  .reset-btn {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    border-radius: var(--radius);
    padding: 8px 16px;
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    margin-top: 10px;
    transition: all var(--transition);
  }

  .reset-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); background: var(--bg-primary); }

  /* Animations */
  @keyframes flash-success {
    0%, 100% { box-shadow: none; }
    50% { box-shadow: 0 0 20px var(--accent-success); }
  }

  /* Responsive */
  @media (max-width: 600px) {
    body { padding: 12px; }
    .options { grid-template-columns: 1fr; }
    h1 { font-size: 1.5rem; }
  }
</style>
</head>
<body>
<div class="app">
  <h1>GIF Maker</h1>
  <p class="subtitle">Drop a video to make a GIF</p>

  <!-- Drop Zone -->
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="video/mp4,video/*">
    <span class="drop-icon" id="dropIcon"></span>
    <div class="drop-label" id="dropLabel">Drop video here or click to browse</div>
    <div class="drop-hint" id="dropHint">.mp4, .mov, .m4v, .webm supported · max __MAX_UPLOAD_MB__ MB</div>
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
        <option value="gifski">Gifski (best quality)</option>
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

    <div class="option-group">
      <label>Transparent</label>
      <select id="transparent">
        <option value="0" selected>Off</option>
        <option value="1">On</option>
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
const MAX_UPLOAD_MB = __MAX_UPLOAD_MB__;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

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
  if (file.size > MAX_UPLOAD_BYTES) {
    clearSelection();
    showError(`File too large. Max upload is ${MAX_UPLOAD_MB} MB.`);
    fileInput.value = '';
    return;
  }
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

function clearSelection() {
  selectedFile = null;
  fileInput.value = '';
  dropZone.classList.remove('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = '';
  dropHint.style.display = '';
  fileInfo.classList.remove('visible');
  fileName.textContent = '';
  fileSize.textContent = '';
  convertBtn.disabled = true;
  convertBtn.textContent = 'Select a video first';
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
  formData.append('transparent', document.getElementById('transparent').value);

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
    try {
      const res = await fetch('/status/' + jobId);
      const data = await res.json();

      if (data.status === 'done') {
        clearInterval(pollTimer);
        showResult(data);
      } else if (data.status === 'error') {
        clearInterval(pollTimer);
        showError(data.error);
      } else if (data.status === 'unknown') {
        clearInterval(pollTimer);
        showError('Conversion status expired. Please try again.');
      } else {
        if (data.step) progressLabel.textContent = data.step;
      }
    } catch(e) {
      clearInterval(pollTimer);
      showError('Network error while checking conversion status. Please try again.');
    }
  }, 800);
}

function showResult(data) {
  progressSection.classList.remove('visible');
  resultSection.classList.add('visible');
  resultGif.src = data.url + '?t=' + Date.now();
  if (data.transparent) {
    resultGif.classList.add('checkerboard');
  } else {
    resultGif.classList.remove('checkerboard');
  }
  const encoderLabel = {'gifski':'Gifski','ffmpeg-high':'ffmpeg (2-pass)','libvips':'libvips','ffmpeg-med':'ffmpeg'}[data.encoder] || data.encoder;
  resultMeta.textContent = `${data.width}×${data.height} · ${data.size} · ${data.frames} frames · ${data.fps} fps · ${encoderLabel}`;
  downloadBtn.href = data.url;
  downloadBtn.download = data.filename;
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert Again';
}

function showError(msg, canRetry = Boolean(selectedFile)) {
  progressSection.classList.remove('visible');
  // Clear any existing error before inserting a new one
  document.querySelectorAll('.error-msg').forEach(el => el.remove());
  const err = document.createElement('div');
  err.className = 'error-msg';
  err.textContent = msg;
  convertBtn.parentNode.insertBefore(err, convertBtn.nextSibling);
  convertBtn.disabled = !canRetry;
  convertBtn.textContent = canRetry ? 'Try Again' : 'Select a video first';
  setTimeout(() => err.remove(), 8000);
}

resetBtn.addEventListener('click', () => {
  clearSelection();
  resultSection.classList.remove('visible');
  resultGif.classList.remove('checkerboard');
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
            html = HTML.replace("__MAX_UPLOAD_MB__", str(MAX_UPLOAD_MB))
            self._send(200, "text/html", html.encode())

        elif path == "/healthz":
            self._json(200, {"ok": True})

        elif path == "/favicon.svg":
            svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0a0a0a"/><text x="16" y="26" font-family="\'Inter\', system-ui, -apple-system, sans-serif" font-size="30" font-weight="900" fill="#c8ff00" text-anchor="middle">G</text></svg>'
            self._send(200, "image/svg+xml", svg.encode())

        elif path.startswith("/status/"):
            job_id = path.split("/")[-1]
            with jobs_lock:
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
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "Invalid Content-Length."})
                return
            if content_length > MAX_UPLOAD_BYTES:
                self._json(413, {"error": f"File too large. Max upload is {MAX_UPLOAD_MB} MB."})
                return
            if content_length <= 0:
                self._json(400, {"error": "Empty upload."})
                return
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)

            # Parse multipart
            try:
                params = parse_multipart(body, content_type)
                params = validate_params(params)
            except Exception as e:
                self._json(400, {"error": str(e)})
                return

            if not conversion_slots.acquire(blocking=False):
                self._json(503, {"error": "Another conversion is running. Please try again shortly."})
                return

            job_id = str(uuid.uuid4())[:8]
            with jobs_lock:
                if len(jobs) >= MAX_JOBS:
                    evictable = [k for k, v in list(jobs.items())
                                 if isinstance(v, dict) and v.get("status") in ("done", "error")]
                    for k in evictable[:50]:
                        gif = OUTPUT_DIR / f"{k}.gif"
                        gif.unlink(missing_ok=True)
                        jobs.pop(k, None)
                if len(jobs) >= MAX_JOBS:
                    self._json(503, {"error": "Server is busy. Please try again shortly."})
                    conversion_slots.release()
                    return
                jobs[job_id] = {"status": "queued", "step": "Queued…"}

            self._json(200, {"job_id": job_id})

            # Run conversion in background thread
            t = threading.Thread(target=run_conversion, args=(job_id, params, True), daemon=True)
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
        part_content_type = ""
        for line in headers_str.splitlines():
            if "Content-Disposition" in line:
                for seg in line.split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        name = seg[5:].strip('"')
                    elif seg.startswith("filename="):
                        filename = seg[9:].strip('"')
            elif line.lower().startswith("content-type:"):
                part_content_type = line.split(":", 1)[1].strip().lower()

        if name:
            if filename:
                result[name] = {
                    "filename": filename,
                    "content_type": part_content_type,
                    "data": content,
                }
            else:
                result[name] = content.decode("utf-8", errors="replace").strip()

    return result


def _parse_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _parse_time(value, label):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"{label} time must be a number of seconds")
    if parsed < 0:
        raise ValueError(f"{label} time must be 0 or greater")
    return str(parsed)


def validate_params(params: dict) -> dict:
    video_data = params.get("video")
    if not video_data or not isinstance(video_data, dict):
        raise ValueError("No video file received")

    filename = video_data.get("filename") or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported video type. Use one of: {allowed}")

    content_type = (video_data.get("content_type") or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_MIME_PREFIXES):
        raise ValueError("Unsupported upload content type")

    if len(video_data.get("data", b"")) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large. Max upload is {MAX_UPLOAD_MB} MB.")

    fps = _parse_int(params.get("fps", "15"), default=15, minimum=1, maximum=30)
    width_opt = (params.get("width", "640") or "640").strip()
    if width_opt not in ALLOWED_WIDTHS:
        raise ValueError("Unsupported width option")

    encoder = (params.get("encoder", "ffmpeg-high") or "ffmpeg-high").strip()
    if encoder not in ALLOWED_ENCODERS:
        raise ValueError("Unsupported encoder option")

    loop = _parse_int(params.get("loop", "0"), default=0)
    if loop not in ALLOWED_LOOPS:
        raise ValueError("Unsupported loop option")

    start = _parse_time(params.get("start", ""), "Start")
    end = _parse_time(params.get("end", ""), "End")
    if start and end and float(end) <= float(start):
        raise ValueError("End time must be greater than start time")

    transparent = params.get("transparent", "0") == "1"

    return {
        "video": video_data,
        "fps": fps,
        "width": width_opt,
        "start": start,
        "end": end,
        "encoder": encoder,
        "loop": loop,
        "transparent": transparent,
    }


def loop_values(ui_loop: int) -> tuple[int, int]:
    """Return loop values for ffmpeg/libvips and gifski."""
    # UI: 0 = forever, 1 = play once, 2 = play twice.
    # ffmpeg/libvips store extra loops after the first play; gifski uses
    # -1 for no repeat and positive values for additional repeats.
    ffmpeg_loop = {0: 0, 1: -1, 2: 1}.get(ui_loop, 0)
    gifski_repeat = {0: 0, 1: -1, 2: 1}.get(ui_loop, 0)
    return ffmpeg_loop, gifski_repeat


def probe_duration(input_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError("Invalid or unsupported video file")
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        raise ValueError("Could not read video duration")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Could not read video duration")
    return duration


def enforce_clip_limits(source_duration: float, start: str, end: str, fps: int):
    start_s = float(start) if start else 0.0
    end_s = float(end) if end else source_duration
    if start_s >= source_duration:
        raise ValueError("Start time is beyond the end of the video")
    clip_duration = min(end_s, source_duration) - start_s
    if clip_duration <= 0:
        raise ValueError("Selected clip has no duration")
    if clip_duration > MAX_DURATION_SECONDS:
        raise ValueError(f"Clip is too long. Max duration is {MAX_DURATION_SECONDS:g} seconds.")
    estimated_frames = math.ceil(clip_duration * fps)
    if estimated_frames > MAX_OUTPUT_FRAMES:
        raise ValueError(f"Clip has too many frames. Max output is {MAX_OUTPUT_FRAMES} frames.")
    return clip_duration, estimated_frames


def run_conversion(job_id: str, params: dict, release_slot: bool = False):
    import tempfile
    import shutil

    def update(step, **extra):
        with jobs_lock:
            jobs[job_id] = {"status": "running", "step": step, **extra}

    input_path = None
    palette_path = None
    frames_dir = None
    trimmed_path = None
    try:
        update("Saving uploaded video…")

        video_data = params.get("video")
        if not video_data or not isinstance(video_data, dict):
            raise ValueError("No video file received")

        suffix = Path(video_data["filename"]).suffix.lower() or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(video_data["data"])
            input_path = f.name

        # Options
        fps = params["fps"]
        width_opt = params["width"]
        start = params["start"]
        end = params["end"]
        encoder = params["encoder"]
        loop = params["loop"]
        transparent = params["transparent"]
        ffmpeg_loop, gifski_repeat = loop_values(loop)
        source_duration = probe_duration(input_path)
        clip_duration, estimated_frames = enforce_clip_limits(source_duration, start, end, fps)

        # ffmpeg single-pass cannot produce transparent GIFs; auto-upgrade
        if transparent and encoder == "ffmpeg-med":
            encoder = "ffmpeg-high"

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
                time_args += ["-t", str(clip_duration)]
            else:
                time_args += ["-to", end]
        elif start:
            time_args += ["-t", str(clip_duration)]

        # ── Gifski ────────────────────────────────────────────────────────────
        if encoder == "gifski":
            update("Encoding with Gifski…")
            gifski_cmd = [
                "gifski",
                "--fps", str(fps),
                "--quality", "90",
                "--repeat", str(gifski_repeat),
                "-o", output_path,
            ]
            if width_opt != "original":
                gifski_cmd += ["-W", width_opt]
            # gifski handles trim via ffmpeg pre-pass if time args needed
            if time_args:
                update("Trimming clip…")
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                    trimmed_path = tf.name
                trim_cmd = [
                    "ffmpeg", "-y", *time_args,
                    "-i", input_path,
                    "-c", "copy", trimmed_path
                ]
                r = subprocess.run(trim_cmd, capture_output=True, text=True, timeout=120)
                if r.returncode != 0:
                    # fallback: re-encode trim
                    trim_cmd = ["ffmpeg", "-y", *time_args, "-i", input_path, trimmed_path]
                    r = subprocess.run(trim_cmd, capture_output=True, text=True, timeout=120)
                if r.returncode != 0:
                    raise RuntimeError(f"Trim failed:\n{r.stderr[-800:]}")
                gifski_cmd.append(trimmed_path)
                update("Encoding with Gifski…")
                result = subprocess.run(gifski_cmd, capture_output=True, text=True, timeout=300)
                os.unlink(trimmed_path)
                trimmed_path = None
            else:
                gifski_cmd.append(input_path)
                result = subprocess.run(gifski_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"Gifski failed:\n{result.stderr[-800:]}")

        # ── libvips ───────────────────────────────────────────────────────────
        elif encoder == "libvips":
            import glob as globmod
            frames_dir = tempfile.mkdtemp()
            update("Extracting frames…")
            frame_pattern = os.path.join(frames_dir, "frame%05d.png")
            pix_fmt_args = ["-pix_fmt", "rgba"] if transparent else []
            extract_cmd = [
                "ffmpeg", "-y", *time_args,
                "-i", input_path,
                "-vf", vf_base,
                *pix_fmt_args,
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
            joined.set_type(pyvips.GValue.gint_type, "loop", ffmpeg_loop)
            joined.gifsave(output_path, effort=7, dither=1.0)

        # ── ffmpeg high (2-pass palette) ──────────────────────────────────────
        elif encoder == "ffmpeg-high":
            update("Generating color palette…")
            palette_path = str(OUTPUT_DIR / f"{job_id}_palette.png")
            reserve = "1" if transparent else "0"
            r = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", f"{vf_base},palettegen=stats_mode=diff:reserve_transparent={reserve}", palette_path],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                raise RuntimeError(f"Palette generation failed:\n{r.stderr[-800:]}")

            update("Rendering GIF…")
            alpha_opt = ":alpha_threshold=128" if transparent else ""
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path, "-i", palette_path,
                 "-lavfi", f"{vf_base} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle{alpha_opt}",
                 "-loop", str(ffmpeg_loop), output_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"GIF conversion failed:\n{result.stderr[-800:]}")

        # ── ffmpeg standard ───────────────────────────────────────────────────
        else:
            update("Rendering GIF…")
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", vf_base, "-loop", str(ffmpeg_loop), output_path],
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

        with jobs_lock:
            if job_id not in jobs:
                if os.path.exists(output_path):
                    os.unlink(output_path)
                return
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
                "transparent": transparent,
            }

    except Exception as e:
        with jobs_lock:
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
        if trimmed_path and os.path.exists(trimmed_path):
            try: os.unlink(trimmed_path)
            except OSError: pass
        if release_slot:
            conversion_slots.release()


class GifMakerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Thread-per-request server so status polling doesn't block uploads."""
    allow_reuse_address = True
    daemon_threads = True


def _cleanup_loop():
    """Background thread: delete GIFs and job entries older than 1 hour, atomically."""
    while True:
        time.sleep(1800)  # run every 30 minutes
        cutoff = time.time() - 3600
        # Identify expired files outside the lock (disk I/O should not block job state)
        expired = []
        for fpath in list(OUTPUT_DIR.iterdir()):
            if fpath.suffix == ".gif":
                try:
                    if fpath.stat().st_mtime < cutoff:
                        expired.append(fpath)
                except OSError:
                    pass
        # Delete files outside the lock, collect job IDs to evict
        evict_ids = []
        for fpath in expired:
            try:
                fpath.unlink()
                evict_ids.append(fpath.stem)
            except OSError:
                pass
        # Single lock acquisition to batch-evict all job entries
        if evict_ids:
            with jobs_lock:
                for job_id in evict_ids:
                    jobs.pop(job_id, None)


def main():
    threading.Thread(target=_cleanup_loop, daemon=True).start()

    print(f"\n  GIF Maker running at http://{HOST}:{PORT}")
    is_local = sys.stdout.isatty()
    if is_local:
        import webbrowser
        print(f"  Press Ctrl+C to stop\n")
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    try:
        with GifMakerServer((HOST, PORT), Handler) as httpd:
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
