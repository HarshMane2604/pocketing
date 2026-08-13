#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/../.." && pwd)"
backend_dir="$project_root/backend"
frontend_dir="$project_root/frontend"
python_bin="$backend_dir/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python3 -m venv "$backend_dir/.venv"
fi
"$python_bin" -m pip install -r "$backend_dir/requirements.txt"

if [[ -f "$frontend_dir/package-lock.json" ]]; then
  npm --prefix "$frontend_dir" ci
else
  npm --prefix "$frontend_dir" install
fi
npm --prefix "$frontend_dir" run build

mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
sed \
  -e "s|@@BACKEND_DIR@@|$backend_dir|g" \
  -e "s|@@PYTHON@@|$python_bin|g" \
  "$script_dir/pocketing.service.template" \
  > "$HOME/.config/systemd/user/pocketing.service"

cp "$frontend_dir/public/icons/app-icon.svg" "$HOME/.local/share/icons/pocketing.svg"
launcher="$script_dir/open-pocketing.sh"
desktop_file="$HOME/.local/share/applications/pocketing.desktop"

sed \
  -e "s|@@LAUNCHER@@|$launcher|g" \
  "$script_dir/pocketing.desktop.template" \
  > "$desktop_file"
cp "$desktop_file" "$HOME/.config/autostart/pocketing.desktop"

chmod +x "$launcher"
systemctl --user daemon-reload
systemctl --user enable --now pocketing.service

echo 'Pocketing is installed. It will run and open automatically at Linux login.'
