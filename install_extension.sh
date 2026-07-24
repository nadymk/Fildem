#!/bin/bash
set -e

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UUID="fildem@inled.es"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
OLD_UUID="fildemGMenu@gonza.com"
OLD_EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$OLD_UUID"

echo "🧹 Cleaning previous versions..."
if [ -d "$EXT_DIR" ]; then
    rm -rf "$EXT_DIR"
fi
if [ -d "$OLD_EXT_DIR" ]; then
    rm -rf "$OLD_EXT_DIR"
fi

echo "📂 Installing new extension ($UUID)..."
mkdir -p "$EXT_DIR"
cp -a "$repo_dir/fildem@inled.es/." "$EXT_DIR/"

echo "🛠️ Compiling GSettings schemas..."
glib-compile-schemas "$EXT_DIR/schemas/"

echo "✨ Extension installed successfully."
echo "🔄 Restart GNOME Shell (Alt+F2 -> r on X11, or log out on Wayland) and enable the extension."
