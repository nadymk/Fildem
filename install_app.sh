#!/bin/bash
set -e

# Get absolute path of current directory
CURRENT_DIR=$(pwd)

echo "📦 Updating package indices..."
pkexec apt update

echo "📦 Installing main dependencies (GTK3)..."
pkexec apt install -y python3-gi python3-dbus bamfdaemon libbamf3-dev libkeybinder-3.0-dev \
    appmenu-gtk3-module python3-setuptools

echo "📦 Attempting to install legacy compatibility packages (optional)..."
# We try to install GTK2 and Unity modules but don't fail if they don't exist
pkexec apt install -y unity-gtk2-module appmenu-gtk-module-common 2>/dev/null || echo "⚠️  Note: Some legacy GTK2 packages are not available on your system. They will be skipped."

echo "⚙️ Installing Python companion (Fildem Service)..."
# Enter project directory before running setup.py so it finds README.md
pkexec sh -c "cd '$CURRENT_DIR' && python3 setup.py install"

echo "📝 Configuring GTK modules..."
# GTK 2 (if file or support exists)
if [ ! -f ~/.gtkrc-2.0 ]; then
    touch ~/.gtkrc-2.0
fi
if ! grep -q "appmenu-gtk-module" ~/.gtkrc-2.0; then
    echo 'gtk-modules="appmenu-gtk-module"' >> ~/.gtkrc-2.0
fi

# GTK 3 (Main for GNOME 45+)
mkdir -p ~/.config/gtk-3.0
if [ ! -f ~/.config/gtk-3.0/settings.ini ]; then
    echo -e "[Settings]\ngtk-modules=\"appmenu-gtk-module\"" > ~/.config/gtk-3.0/settings.ini
else
    if ! grep -q "appmenu-gtk-module" ~/.config/gtk-3.0/settings.ini; then
        if grep -q "\[Settings\]" ~/.config/gtk-3.0/settings.ini; then
            sed -i '/\[Settings\]/a gtk-modules="appmenu-gtk-module"' ~/.config/gtk-3.0/settings.ini
        else
            echo -e "\n[Settings]\ngtk-modules=\"appmenu-gtk-module\"" >> ~/.config/gtk-3.0/settings.ini
        fi
    fi
fi

echo "🚀 Configuring systemd service..."
mkdir -p ~/.config/systemd/user
cp "$CURRENT_DIR/fildem.service" ~/.config/systemd/user/fildem.service
systemctl --user daemon-reload
systemctl --user enable fildem.service
systemctl --user restart fildem.service

echo "✅ Companion installation completed."
echo "💡 The fildem service is now running and will start automatically."
echo "💡 Restart your session for GTK modules to take effect in all applications."
