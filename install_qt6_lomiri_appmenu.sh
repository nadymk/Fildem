#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_src_dir="$repo_dir/third_party/qtlomiri-appmenutheme-qt6/src/lomiriappmenu"
plugin_install_dir="${XDG_DATA_HOME:-$HOME/.local}/lib/qt6/plugins/platformthemes"

qmake6 -o "$plugin_src_dir/Makefile" "$plugin_src_dir/lomiriappmenu.pro"
make -C "$plugin_src_dir" -j"$(nproc)"

mkdir -p "$plugin_install_dir"
install -m 0644 "$plugin_src_dir/liblomiriappmenu.so" "$plugin_install_dir/liblomiriappmenu.so"

echo "Installed Qt6 Lomiri appmenu platform theme to $plugin_install_dir/liblomiriappmenu.so"
echo "Launch Qt6 apps with:"
echo "  QT_PLUGIN_PATH=${XDG_DATA_HOME:-$HOME/.local}/lib/qt6/plugins QT_QPA_PLATFORMTHEME=lomiriappmenu <app>"
