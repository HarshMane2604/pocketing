#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now pocketing.service 2>/dev/null || true
rm -f \
  "$HOME/.config/systemd/user/pocketing.service" \
  "$HOME/.config/autostart/pocketing.desktop" \
  "$HOME/.local/share/applications/pocketing.desktop" \
  "$HOME/.local/share/icons/pocketing.svg"
systemctl --user daemon-reload
echo 'Pocketing startup entries were removed. Notes and configuration were preserved.'
