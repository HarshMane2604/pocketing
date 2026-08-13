#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now memory-inbox.service 2>/dev/null || true
rm -f \
  "$HOME/.config/systemd/user/memory-inbox.service" \
  "$HOME/.config/autostart/memory-inbox.desktop" \
  "$HOME/.local/share/applications/memory-inbox.desktop" \
  "$HOME/.local/share/icons/memory-inbox.svg"
systemctl --user daemon-reload
echo 'Memory Inbox startup entries were removed. Notes and configuration were preserved.'
