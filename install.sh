#!/usr/bin/env bash
set -euo pipefail

# Output colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

run_root() {
    if command -v pkexec >/dev/null 2>&1; then
        pkexec "$@"
    else
        sudo "$@"
    fi
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$script_dir"
temp_dir=""

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}   Fildem Global Menu - Unified Installer  ${NC}"
echo -e "${BLUE}===========================================${NC}"

if [[ ! -f "$script_dir/install_app.sh" || ! -f "$script_dir/install_extension.sh" ]]; then
    echo -e "${YELLOW}📥 Local installer files not found. Falling back to a fresh clone...${NC}"
    if ! command -v git >/dev/null 2>&1; then
        echo -e "${YELLOW}📦 Git is not installed. Installing...${NC}"
        run_root apt update
        run_root apt install -y git
    fi

    temp_dir=$(mktemp -d)
    trap 'rm -rf "$temp_dir"' EXIT

    echo -e "${BLUE}📥 Cloning repository from GitHub...${NC}"
    git clone --depth 1 https://github.com/InledGroup/Fildem.git "$temp_dir"
    repo_dir="$temp_dir"
fi

chmod +x "$repo_dir/install_app.sh" "$repo_dir/install_extension.sh"

echo -e "${BLUE}📦 Installing companion app...${NC}"
"$repo_dir/install_app.sh"

echo -e "${BLUE}🧩 Installing GNOME Shell extension...${NC}"
"$repo_dir/install_extension.sh"

echo -e "${GREEN}===========================================${NC}"
echo -e "${GREEN}      Installation completed successfully!  ${NC}"
echo -e "${GREEN}===========================================${NC}"
echo -e "${YELLOW}IMPORTANT:${NC}"
echo -e "1. ${BLUE}Restart GNOME Shell${NC} (Alt+F2, type 'r' and press Enter, or log out on Wayland)."
echo -e "2. ${BLUE}Enable the 'Fildem Global Menu' extension${NC} in the 'Extensions' app."
echo -e "3. ${BLUE}Log out and back in${NC} for menus to work in all applications."
echo -e ""
echo -e "Developed with ❤️ by ${BLUE}Inled${NC} (https://inled.es)"
