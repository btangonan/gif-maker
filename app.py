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

TOOL_PATH_PREFIX = "/opt/homebrew/bin:/usr/local/bin"
os.environ["PATH"] = f"{TOOL_PATH_PREFIX}:{os.environ.get('PATH', os.defpath)}"

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
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_MIME_PREFIXES = ("video/", "application/octet-stream")
ALLOWED_ENCODERS = {"gifski", "libvips", "ffmpeg-high", "ffmpeg-med"}
ALLOWED_WIDTHS = {"original", "1000", "800", "640", "480", "320"}
ALLOWED_LOOPS = {0, 1, 2}
# Photo-series canvas: how the common frame size is derived.
ALLOWED_CANVAS = {"first", "bbox", "1:1", "16:9", "9:16"}
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
  <p class="subtitle">Drop a video — or a series of photos — to make a GIF</p>

  <!-- Drop Zone -->
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="video/mp4,video/*,image/*" multiple>
    <span class="drop-icon" id="dropIcon"></span>
    <div class="drop-label" id="dropLabel">Drop a video or photos, or click to browse</div>
    <div class="drop-hint" id="dropHint">Multiple photos → GIF frames · mp4 mov webm png jpg webp · max __MAX_UPLOAD_MB__ MB</div>
    <div class="file-info" id="fileInfo">
      <span class="file-name" id="fileName"></span>
      <span class="file-size" id="fileSize"></span>
    </div>
  </div>

  <!-- Options -->
  <div class="options">
    <div class="option-group">
      <label id="fpsLabel">FPS</label>
      <div class="slider-row">
        <input type="range" id="fps" min="5" max="30" step="1" value="15">
        <span class="slider-val" id="fpsVal">15</span>
      </div>
    </div>

    <div class="option-group">
      <label>Width</label>
      <select id="width">
        <option value="original">Original</option>
        <option value="1000">1000px</option>
        <option value="800">800px</option>
        <option value="640" selected>640px</option>
        <option value="480">480px</option>
        <option value="320">320px</option>
      </select>
    </div>

    <div class="option-group" id="canvasGroup" style="display:none">
      <label>Canvas</label>
      <select id="canvas">
        <option value="first" selected>First photo</option>
        <option value="bbox">Largest bounding box</option>
        <option value="1:1">Square (1:1)</option>
        <option value="16:9">Widescreen (16:9)</option>
        <option value="9:16">Vertical (9:16)</option>
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
        <option value="ffmpeg-high">ffmpeg (2-pass palette)</option>
        <option value="gifski">Gifski (best quality)</option>
        <option value="libvips" selected>libvips</option>
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

  <button class="convert-btn" id="convertBtn" disabled>Select a video or photos</button>

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
let selectedImages = null;  // Array of File when an image series is chosen
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
const fpsLabel = document.getElementById('fpsLabel');

// The same slider drives FPS (video) and Seconds-per-photo (image series).
function renderRateVal() {
  fpsVal.textContent = selectedImages ? fps.value + 's' : fps.value;
}
function setRateControl(mode) {
  const canvasGroup = document.getElementById('canvasGroup');
  if (mode === 'images') {
    fpsLabel.textContent = 'Seconds per photo';
    fps.min = '0.25'; fps.max = '10'; fps.step = '0.25'; fps.value = '1';
    canvasGroup.style.display = '';  // photo-only control
  } else {
    fpsLabel.textContent = 'FPS';
    fps.min = '5'; fps.max = '30'; fps.step = '1'; fps.value = '15';
    canvasGroup.style.display = 'none';
  }
  renderRateVal();
}
fps.addEventListener('input', renderRateVal);
const MAX_UPLOAD_MB = __MAX_UPLOAD_MB__;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

// Drag & drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) handleFiles(fileInput.files);
});

// Route a FileList: a single video → video mode; one or more images → series.
function handleFiles(fileList) {
  const files = Array.from(fileList);  // preserve drop/selection order
  const allImages = files.every(f => f.type.startsWith('image/'));
  if (files.length > 1 || (allImages && files.length >= 1)) {
    if (!allImages) {
      clearSelection();
      showError('Mixed selection. Drop one video, or only images.');
      return;
    }
    setImages(files);
  } else {
    setFile(files[0]);
  }
}

function setImages(files) {
  const total = files.reduce((sum, f) => sum + f.size, 0);
  if (total > MAX_UPLOAD_BYTES) {
    clearSelection();
    showError(`Images too large. Max upload is ${MAX_UPLOAD_MB} MB total.`);
    return;
  }
  selectedFile = null;
  selectedImages = files;
  setRateControl('images');
  dropZone.classList.add('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = 'none';
  dropHint.style.display = 'none';
  fileInfo.classList.add('visible');
  fileName.textContent = `${files.length} images`;
  fileSize.textContent = formatBytes(total);
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert to GIF →';
  resultSection.classList.remove('visible');
}

function setFile(file) {
  if (file.size > MAX_UPLOAD_BYTES) {
    clearSelection();
    showError(`File too large. Max upload is ${MAX_UPLOAD_MB} MB.`);
    fileInput.value = '';
    return;
  }
  selectedImages = null;
  selectedFile = file;
  setRateControl('video');
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
  selectedImages = null;
  setRateControl('video');
  fileInput.value = '';
  dropZone.classList.remove('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = '';
  dropHint.style.display = '';
  fileInfo.classList.remove('visible');
  fileName.textContent = '';
  fileSize.textContent = '';
  convertBtn.disabled = true;
  convertBtn.textContent = 'Select a video or photos';
}

function formatBytes(b) {
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/(1024*1024)).toFixed(1) + ' MB';
}

// Convert
convertBtn.addEventListener('click', async () => {
  if (!selectedFile && !selectedImages) return;

  convertBtn.disabled = true;
  convertBtn.textContent = 'Converting…';
  progressSection.classList.add('visible');
  progressLabel.textContent = selectedImages ? 'Uploading images…' : 'Uploading video…';
  progressBar.classList.add('indeterminate');
  resultSection.classList.remove('visible');

  const formData = new FormData();
  if (selectedImages) {
    selectedImages.forEach(f => formData.append('images', f));  // order preserved
    formData.append('seconds_per_photo', fps.value);  // slider is seconds/photo here
    formData.append('canvas', document.getElementById('canvas').value);
  } else {
    formData.append('video', selectedFile);
    formData.append('fps', fps.value);
  }
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
  convertBtn.textContent = canRetry ? 'Try Again' : 'Select a video or photos';
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
                entry = {
                    "filename": filename,
                    "content_type": part_content_type,
                    "data": content,
                }
                # Multiple files under the same field name (e.g. image series)
                # accumulate into a list, preserving multipart part order.
                if name in result:
                    existing = result[name]
                    if not isinstance(existing, list):
                        existing = [existing]
                    existing.append(entry)
                    result[name] = existing
                else:
                    result[name] = entry
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


def _parse_float(value, default, minimum=None, maximum=None):
    try:
        parsed = float(value)
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
    images = params.get("images")
    if images is not None and not isinstance(images, list):
        images = [images]  # parser yields a dict for a single file

    has_video = isinstance(video_data, dict)
    has_images = bool(images)
    if has_video == has_images:
        raise ValueError("Upload either one video or a series of images")

    # Options common to both modes
    width_opt = (params.get("width", "640") or "640").strip()
    if width_opt not in ALLOWED_WIDTHS:
        raise ValueError("Unsupported width option")

    loop = _parse_int(params.get("loop", "0"), default=0)
    if loop not in ALLOWED_LOOPS:
        raise ValueError("Unsupported loop option")

    transparent = params.get("transparent", "0") == "1"

    if has_images:
        if len(images) > MAX_OUTPUT_FRAMES:
            raise ValueError(f"Too many images. Max is {MAX_OUTPUT_FRAMES} frames.")
        total_bytes = 0
        for img in images:
            if not isinstance(img, dict):
                raise ValueError("Invalid image upload")
            ext = Path(img.get("filename") or "").suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
                raise ValueError(f"Unsupported image type. Use one of: {allowed}")
            ctype = (img.get("content_type") or "").lower()
            if not ctype.startswith("image/"):
                raise ValueError("Unsupported image content type")
            total_bytes += len(img.get("data", b""))
        if total_bytes > MAX_UPLOAD_BYTES:
            raise ValueError(f"Images too large. Max upload is {MAX_UPLOAD_MB} MB.")
        # Photos: user picks seconds-per-photo; fps is its inverse (gifski accepts
        # fractional fps, so e.g. 2s/photo -> 0.5 fps holds each frame for 2s).
        seconds_per_photo = _parse_float(
            params.get("seconds_per_photo", "1"), default=1.0, minimum=0.25, maximum=10.0
        )
        fps = round(1.0 / seconds_per_photo, 4)
        canvas = (params.get("canvas", "first") or "first").strip()
        if canvas not in ALLOWED_CANVAS:
            raise ValueError("Unsupported canvas option")
        # Image series are assembled with gifski (purpose-built for frame lists).
        return {
            "mode": "images",
            "images": images,
            "fps": fps,
            "width": width_opt,
            "canvas": canvas,
            "encoder": "gifski",
            "loop": loop,
            "transparent": transparent,
        }

    # Video mode
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

    encoder = (params.get("encoder", "libvips") or "libvips").strip()
    if encoder not in ALLOWED_ENCODERS:
        raise ValueError("Unsupported encoder option")

    fps = _parse_int(params.get("fps", "15"), default=15, minimum=1, maximum=30)

    start = _parse_time(params.get("start", ""), "Start")
    end = _parse_time(params.get("end", ""), "End")
    if start and end and float(end) <= float(start):
        raise ValueError("End time must be greater than start time")

    return {
        "mode": "video",
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


def _probe_image_size(path: str, label: str) -> tuple[int, int]:
    """Return (width, height) of an image via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        raise RuntimeError(f"Could not read dimensions of image '{label}'")


def _canvas_dims(canvas: str, sizes: list) -> tuple[int, int]:
    """Common (width, height) for a photo series, from the chosen canvas mode.
    `sizes` is a list of (w, h) in upload order (sizes[0] = first photo)."""
    max_w = max(w for w, _ in sizes)
    max_h = max(h for _, h in sizes)
    if canvas == "bbox":
        return max_w, max_h
    if canvas in ("1:1", "16:9", "9:16"):
        longest = max(max_w, max_h)
        if canvas == "1:1":
            return longest, longest
        short = max(1, round(longest * 9 / 16))
        return (longest, short) if canvas == "16:9" else (short, longest)
    return sizes[0]  # "first" (default)


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


def _finalize_output(job_id, output_path, output_name, fps, encoder, transparent):
    """Probe the finished GIF and publish the done status (shared by all modes)."""
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
        if job_id not in jobs:  # job evicted/expired mid-run — discard output
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
        # ── Image series → GIF ────────────────────────────────────────────────
        if params.get("mode") == "images":
            fps = params["fps"]
            width_opt = params["width"]
            transparent = params["transparent"]
            _, gifski_repeat = loop_values(params["loop"])
            output_name = f"{job_id}.gif"
            output_path = str(OUTPUT_DIR / output_name)

            update("Preparing images…")
            frames_dir = tempfile.mkdtemp()  # cleaned by finally (rmtree)

            # Pass 1: write each source and probe its size — needed to size the
            # canvas before encoding (gifski rejects mismatched frame sizes).
            srcs = []  # (src_path, filename)
            sizes = []
            for i, img in enumerate(params["images"]):
                src_suffix = Path(img["filename"]).suffix.lower() or ".png"
                src_path = os.path.join(frames_dir, f"src{i:05d}{src_suffix}")
                with open(src_path, "wb") as sf:
                    sf.write(img["data"])
                sizes.append(_probe_image_size(src_path, img["filename"]))
                srcs.append((src_path, img["filename"]))

            tw, th = _canvas_dims(params["canvas"], sizes)
            # Crop-to-fill: scale to cover the canvas, then center-crop overflow,
            # so every frame is exactly tw×th. format=rgba keeps source alpha.
            fmt = "format=rgba," if transparent else ""
            vf = (f"{fmt}scale={tw}:{th}:force_original_aspect_ratio=increase:"
                  f"flags=lanczos,crop={tw}:{th}")

            # Pass 2: transcode each source to a uniform PNG frame (gifski's
            # multi-image input is PNG-only; sequential names preserve order).
            frame_paths = []
            for i, (src_path, fname) in enumerate(srcs):
                frame_path = os.path.join(frames_dir, f"frame{i:05d}.png")
                r = subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path, "-vf", vf, "-frames:v", "1", frame_path],
                    capture_output=True, text=True, timeout=60
                )
                os.unlink(src_path)
                if r.returncode != 0:
                    raise RuntimeError(
                        f"Could not read image '{fname}':\n{r.stderr[-400:]}"
                    )
                frame_paths.append(frame_path)

            update("Encoding with Gifski…")
            gifski_cmd = [
                "gifski",
                "--no-sort",  # preserve given (drop) order, don't re-sort
                "--fps", str(fps),
                "--quality", "90",
                "--repeat", str(gifski_repeat),
                "-o", output_path,
            ]
            if width_opt != "original":
                gifski_cmd += ["-W", width_opt]
            gifski_cmd += frame_paths
            result = subprocess.run(gifski_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"Gifski failed:\n{result.stderr[-800:]}")

            _finalize_output(job_id, output_path, output_name, fps, "gifski",
                             params["transparent"])
            return

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
        _finalize_output(job_id, output_path, output_name, fps, encoder, transparent)

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
