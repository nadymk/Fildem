# Fildem Global Menu & HUD

[![Inled Branding](https://img.shields.io/badge/Developed%20by-Inled-blue.svg)](https://inled.es)
![GNOME Shell](https://img.shields.io/badge/GNOME-45--50-green.svg)

![Fildem Global Menu & HUD Demo](demo.png)

Fildem is a global menu system and HUD for the GNOME desktop.
 This project allows you to have a menu bar integrated into the GNOME top panel, similar to macOS or Unity, and a HUD (Heads-Up Display) searcher to quickly access menu options.

This version has been adapted to be fully compatible with **GNOME 48, 49, and 50**, migrating the extension to ESM and updating D-Bus communication.

## Requirements and Components

Fildem consists of two parts that must be installed and running simultaneously:

1.  **GNOME Shell Extension (`fildem@inled.es`)**: Manages the interface in the GNOME panel.
2.  **Companion App (Python)**: Manages menu extraction from applications and HUD logic.

## Installation

### 1. Companion App Installation

The companion app is required for the extension to receive menus from active windows.

#### Dependencies (Ubuntu/Debian)
```bash
sudo apt install python3-gi python3-dbus bamfdaemon libbamf3-dev libkeybinder-3.0-dev python3-setuptools appmenu-gtk-module-common unity-gtk2-module appmenu-gtk3-module
```

#### Quick Installation (Recommended)
If you want to install everything automatically (Extension + App + Service), run the following command in your terminal from a cloned copy of this repository:

```bash
./install.sh
```

The installer will set up the Python companion in your user account, install the GNOME Shell extension, and configure the auto-start service. It automatically chooses the GTK3 module package that matches your system, so it won’t try to install conflicting `appmenu-gtk3-module` and `unity-gtk3-module` packages together.

If you prefer a one-line install directly from GitHub, the installer will fall back to cloning the repository when the local scripts are not present:

```bash
curl -fsSL https://raw.githubusercontent.com/InledGroup/Fildem/main/install.sh | bash
```

#### Manual Installation (Step by step)

If you prefer to install components separately or you are in the repository directory:

1. **Install the Companion App and Service:**
   ```bash
   ./install_app.sh
   ```
2. **Install the GNOME Shell Extension:**
   ```bash
   ./install_extension.sh
   ```

### GTK Module Configuration

- Create or edit the file `~/.gtkrc-2.0` and add:
  ```text
  gtk-modules="appmenu-gtk-module"
  ```
- Create or edit the file `~/.config/gtk-3.0/settings.ini` and add under the `[Settings]` section:
  ```ini
  [Settings]
  gtk-modules="appmenu-gtk-module"
  ```

### 3. Extension Installation

1. Copy the extension folder to your local extensions directory:
   ```bash
   cp -r fildem@inled.es ~/.local/share/gnome-shell/extensions/
   ```
2. Restart GNOME Shell (Alt+F2, type `r` and press Enter on X11, or log out and back in on Wayland).
3. Enable the extension using the "Extensions" or "Tweaks" app.

## Usage

### Running the service
For the global menu to work, the Fildem service must be running. You can start it manually with:
```bash
fildem
```
*(The installer places `fildem` in `~/.local/bin` and configures the user systemd service to start it automatically.)*

### HUD (Heads-Up Display)
The HUD allows you to search for menu actions by pressing a key combination.
- On **Xorg**: Press `Alt + Space`.
- On **Wayland**: You must create a custom keyboard shortcut in GNOME settings that executes the command `fildem-hud`.

## Customization

You can configure the extension's behavior from its preferences:
- **Button paddings**: Adjust the spacing between menu buttons.
- **Show menu only when hover**: Hides the menu unless you hover over the panel.
- **Hide app menu**: Hides the active application's name to give more space to the global menu.

## Credits
Originally created by Gonzalo. Adapted and maintained for modern GNOME versions by **Inled**.
