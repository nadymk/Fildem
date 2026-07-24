#!/usr/bin/env bash
set -euo pipefail

user_bin_dir="${HOME}/.local/bin"
user_desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
system_desktop="/usr/share/applications/synaptic.desktop"
user_desktop="$user_desktop_dir/synaptic.desktop"
launcher="$user_bin_dir/fildem-synaptic-pkexec"

mkdir -p "$user_bin_dir" "$user_desktop_dir"

cat > "$launcher" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

display="${DISPLAY:-}"
xauth="${XAUTHORITY:-}"
dbus_session="${DBUS_SESSION_BUS_ADDRESS:-}"
xdg_runtime="${XDG_RUNTIME_DIR:-}"
gtk_modules="${GTK_MODULES:-}"
gtk_theme="$(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null | awk -F"'" 'NF > 1 {print $2}')"
color_scheme="$(gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null | awk -F"'" 'NF > 1 {print $2}')"

if [[ -n "$gtk_modules" ]]; then
	gtk_modules="${gtk_modules}:appmenu-gtk-module"
else
	gtk_modules="appmenu-gtk-module"
fi

if [[ -z "$gtk_theme" && "$color_scheme" == "prefer-dark" ]]; then
	gtk_theme="Adwaita:dark"
fi

export DISPLAY="$display"
export XAUTHORITY="$xauth"
export DBUS_SESSION_BUS_ADDRESS="$dbus_session"
export XDG_RUNTIME_DIR="$xdg_runtime"
export GTK_MODULES="$gtk_modules"
export UBUNTU_MENUPROXY=1

env_args=(
	DISPLAY="$DISPLAY"
	XAUTHORITY="$XAUTHORITY"
	DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
	XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR"
	GTK_MODULES="$GTK_MODULES"
	UBUNTU_MENUPROXY="$UBUNTU_MENUPROXY"
)

if [[ -n "$gtk_theme" ]]; then
	env_args+=(GTK_THEME="$gtk_theme")
fi

exec pkexec env "${env_args[@]}" /usr/sbin/synaptic "$@"
EOF

chmod 0755 "$launcher"

cp "$system_desktop" "$user_desktop"

python3 - "$user_desktop" "$launcher" <<'PY'
import sys
from pathlib import Path

desktop = Path(sys.argv[1])
launcher = sys.argv[2]
lines = desktop.read_text().splitlines()
for i, line in enumerate(lines):
    if line.startswith("Exec="):
        lines[i] = f"Exec={launcher} %U"
        break
desktop.write_text("\n".join(lines) + "\n")
PY

update-desktop-database "$user_desktop_dir" 2>/dev/null || true

echo "Installed Synaptic appmenu launcher override at $user_desktop"
echo "Wrapper: $launcher"
