#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_src_dir="$repo_dir/third_party/qtlomiri-appmenutheme-qt6/src/lomiriappmenu"
build_dir="$repo_dir/build/qtlomiri-appmenutheme-qt5"
plugin_install_dir="${XDG_DATA_HOME:-$HOME/.local}/lib/qt5/plugins/platformthemes"

if ! command -v qmake >/dev/null 2>&1 && ! command -v qmake-qt5 >/dev/null 2>&1; then
    echo "Qt5 qmake was not found. Install build dependencies first:" >&2
    echo "  sudo apt install qtbase5-dev qtbase5-private-dev qt5-qmake qtchooser" >&2
    exit 1
fi

qmake_cmd=qmake
if command -v qmake-qt5 >/dev/null 2>&1; then
    qmake_cmd=qmake-qt5
fi

mkdir -p "$build_dir"
(
    cd "$build_dir"
    "$qmake_cmd" "$plugin_src_dir/lomiriappmenu.pro"
    make -j"$(nproc)"
)

mkdir -p "$plugin_install_dir"
install -m 0644 "$build_dir/liblomiriappmenu.so" "$plugin_install_dir/liblomiriappmenu.so"

echo "Installed Qt5 Lomiri appmenu platform theme to $plugin_install_dir/liblomiriappmenu.so"
