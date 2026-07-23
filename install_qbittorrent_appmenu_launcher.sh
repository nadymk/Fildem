#!/usr/bin/env bash
set -euo pipefail

system_desktop="/usr/share/applications/org.qbittorrent.qBittorrent.desktop"
user_desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
user_desktop="$user_desktop_dir/org.qbittorrent.qBittorrent.desktop"
plugin_path="${XDG_DATA_HOME:-$HOME/.local}/lib/qt6/plugins"

mkdir -p "$user_desktop_dir"
cp "$system_desktop" "$user_desktop"

python3 - "$user_desktop" "$plugin_path" <<'PY'
import sys
from pathlib import Path

desktop = Path(sys.argv[1])
plugin_path = sys.argv[2]
lines = desktop.read_text().splitlines()
for i, line in enumerate(lines):
    if line.startswith("Exec="):
        lines[i] = f"Exec=env QT_PLUGIN_PATH={plugin_path} QT_QPA_PLATFORMTHEME=lomiriappmenu qbittorrent %U"
        break
desktop.write_text("\n".join(lines) + "\n")
PY

update-desktop-database "$user_desktop_dir" 2>/dev/null || true

echo "Installed qBittorrent appmenu launcher override at $user_desktop"
