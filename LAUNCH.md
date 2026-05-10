# GIF Maker Launch

Target: `https://gif.tangonan.dev`

## Architecture

The Mac mini is the origin and pays the CPU cost for `ffmpeg`, `gifski`, and `libvips`.
Cloudflare should only expose the private local service through a Tunnel:

```text
browser -> Cloudflare -> cloudflared tunnel -> http://127.0.0.1:7878
```

Do not deploy the Python app to Cloudflare Workers. Workers cannot run the native video tooling this app needs.

## Runtime Limits

Default launch settings:

```sh
PORT=7878
MAX_UPLOAD_MB=95
MAX_CONCURRENT_CONVERSIONS=1
MAX_DURATION_SECONDS=30
MAX_OUTPUT_FRAMES=900
```

Raise `MAX_CONCURRENT_CONVERSIONS` only after watching Mac mini CPU, memory, and disk pressure during real conversions.

## Mac Mini App Service

Before installing, keep the Mac mini awake while it is acting as an origin. In System Settings, disable sleep when possible. From the terminal, this is the operational target:

```sh
sudo pmset -a sleep 0
```

Install runtime dependencies on the Mac mini:

```sh
brew install ffmpeg gifski vips
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run manually for smoke testing:

```sh
PORT=7878 MAX_CONCURRENT_CONVERSIONS=1 .venv/bin/python app.py
curl http://127.0.0.1:7878/healthz
```

Example `launchd` plist path:

```text
~/Library/LaunchAgents/dev.tangonan.gif-maker.plist
```

Example plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>dev.tangonan.gif-maker</string>
  <key>WorkingDirectory</key>
  <string>/Users/bradleytangonan/Projects/gif-maker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/bradleytangonan/Projects/gif-maker/.venv/bin/python</string>
    <string>/Users/bradleytangonan/Projects/gif-maker/app.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PORT</key>
    <string>7878</string>
    <key>MAX_UPLOAD_MB</key>
    <string>95</string>
    <key>MAX_CONCURRENT_CONVERSIONS</key>
    <string>1</string>
    <key>MAX_DURATION_SECONDS</key>
    <string>30</string>
    <key>MAX_OUTPUT_FRAMES</key>
    <string>900</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/gif-maker.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/gif-maker.err.log</string>
</dict>
</plist>
```

Load it:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.tangonan.gif-maker.plist
launchctl kickstart -k gui/$(id -u)/dev.tangonan.gif-maker
```

## Cloudflare Tunnel

Create and route the tunnel from the Mac mini:

```sh
cloudflared tunnel login
cloudflared tunnel create gif-maker
cloudflared tunnel route dns gif-maker gif.tangonan.dev
```

Example Cloudflare Tunnel config:

```yaml
tunnel: gif-maker
credentials-file: /Users/bradleytangonan/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: gif.tangonan.dev
    service: http://127.0.0.1:7878
  - service: http_status:404
```

Run manually:

```sh
cloudflared tunnel --config ~/.cloudflared/gif-maker.yml run gif-maker
```

Install as a service after manual verification:

```sh
cloudflared service install
```

## Launch Smoke Test

```sh
curl http://127.0.0.1:7878/healthz
curl https://gif.tangonan.dev/healthz
```

Then convert one short video through the public URL and confirm:

- second simultaneous conversions are rejected while one is running
- clips over `MAX_DURATION_SECONDS` are rejected
- results download from `/output/<job>.gif`
