#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/bradleytangonan/Projects/gif-maker"
APP_PLIST="$HOME/Library/LaunchAgents/dev.tangonan.gif-maker.plist"

cd "$ROOT"

if ! command -v ffmpeg >/dev/null; then
  echo "Missing ffmpeg. Install with: brew install ffmpeg"
  exit 1
fi

if ! command -v ffprobe >/dev/null; then
  echo "Missing ffprobe. Install with: brew install ffmpeg"
  exit 1
fi

if ! command -v gifski >/dev/null; then
  echo "Missing gifski. Install with: brew install gifski"
  exit 1
fi

if ! command -v vips >/dev/null; then
  echo "Missing vips. Install with: brew install vips"
  exit 1
fi

if ! command -v cloudflared >/dev/null; then
  echo "Missing cloudflared. Install with: brew install cloudflared"
  exit 1
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv"
fi

"$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$ROOT/ops/dev.tangonan.gif-maker.plist" "$APP_PLIST"
launchctl bootout "gui/$(id -u)" "$APP_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$APP_PLIST"
launchctl kickstart -k "gui/$(id -u)/dev.tangonan.gif-maker"

sleep 1
curl -fsS http://127.0.0.1:7878/healthz
echo
echo "gif-maker service is running on http://127.0.0.1:7878"
