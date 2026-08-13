#!/usr/bin/env bash
set -euo pipefail

url="http://127.0.0.1:8010"
for _ in $(seq 1 40); do
  if curl --silent --fail "$url/health" >/dev/null; then
    break
  fi
  sleep 0.5
done

for browser in microsoft-edge google-chrome chromium chromium-browser; do
  if command -v "$browser" >/dev/null 2>&1; then
    exec "$browser" --app="$url"
  fi
done

exec xdg-open "$url"
