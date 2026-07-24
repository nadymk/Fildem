#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_root() {
    if command -v pkexec >/dev/null 2>&1; then
        pkexec "$@"
    else
        sudo "$@"
    fi
}

has_package() {
    apt-cache show "$1" >/dev/null 2>&1
}

install_packages() {
    local -a requested=("$@")
    local -a available=()
    local pkg

    for pkg in "${requested[@]}"; do
        if has_package "$pkg"; then
            available+=("$pkg")
        else
            echo "⚠️  Skipping unavailable package: $pkg"
        fi
    done

    if ((${#available[@]})); then
        run_root apt install -y "${available[@]}"
    fi
}

detect_gtk_module_name() {
    local candidate
    for candidate in appmenu-gtk-module unity-gtk-module; do
        if compgen -G "/usr/lib/*/gtk-3.0/modules/lib${candidate}.so" >/dev/null 2>&1 || \
           compgen -G "/usr/lib/*/gtk-2.0/modules/lib${candidate}.so" >/dev/null 2>&1 || \
           compgen -G "${HOME}/.local/lib/gtk-3.0/modules/lib${candidate}.so" >/dev/null 2>&1 || \
           compgen -G "${HOME}/.local/lib/gtk-2.0/modules/lib${candidate}.so" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    printf '%s\n' "appmenu-gtk-module"
}

ensure_gtk_module_setting() {
    local module_name="$1"
    local target_file="$2"
    local init_key="$3"

    python3 - "$module_name" "$target_file" "$init_key" <<'PY'
from pathlib import Path
from configparser import ConfigParser
import re
import sys

module = sys.argv[1]
target = Path(sys.argv[2]).expanduser()
key = sys.argv[3]

def update_value(raw: str) -> str:
    values = [item for item in raw.split(':') if item]
    if module not in values:
        values.insert(0, module)
    seen = set()
    deduped = []
    for item in values:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return ':'.join(deduped)

if target.name == '.gtkrc-2.0':
    lines = target.read_text().splitlines() if target.exists() else []
    updated = False
    for idx, line in enumerate(lines):
        match = re.match(r'^\s*%s\s*=\s*"(.*)"\s*$' % re.escape(key), line)
        if match:
            lines[idx] = f'{key}="{update_value(match.group(1))}"'
            updated = True
            break
    if not updated:
        lines.append(f'{key}="{module}"')
    target.write_text('\n'.join(lines) + '\n')
else:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    if target.exists():
        parser.read(target)
    if not parser.has_section('Settings'):
        parser.add_section('Settings')
    existing = parser.get('Settings', key, fallback='')
    parser.set('Settings', key, update_value(existing) if existing else module)
    with target.open('w') as fh:
        parser.write(fh)
PY
}

echo "📦 Updating package indices..."
run_root apt update

echo "📦 Installing companion dependencies..."
install_packages \
    python3-gi \
    python3-dbus \
    bamfdaemon \
    libbamf3-dev \
    libkeybinder-3.0-dev \
    python3-setuptools \
    appmenu-gtk3-module \
    appmenu-gtk-module-common \
    unity-gtk3-module \
    unity-gtk2-module

echo "⚙️ Installing Python companion (Fildem Service)..."
(
    cd "$repo_dir"
    python3 setup.py install --user
)

gtk_module_name="$(detect_gtk_module_name)"

echo "📝 Configuring GTK modules (${gtk_module_name})..."
ensure_gtk_module_setting "$gtk_module_name" "$HOME/.gtkrc-2.0" "gtk-modules"
mkdir -p "$HOME/.config/gtk-3.0"
ensure_gtk_module_setting "$gtk_module_name" "$HOME/.config/gtk-3.0/settings.ini" "gtk-modules"

echo "🚀 Configuring systemd service..."
mkdir -p "$HOME/.config/systemd/user"
install -m 0644 "$repo_dir/fildem.service" "$HOME/.config/systemd/user/fildem.service"
systemctl --user daemon-reload
systemctl --user enable fildem.service
systemctl --user restart fildem.service

echo "✅ Companion installation completed."
echo "💡 The fildem service is now running and will start automatically."
echo "💡 Restart your session for GTK modules to take effect in all applications."
