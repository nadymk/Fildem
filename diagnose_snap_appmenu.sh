#!/usr/bin/env bash
set -euo pipefail

snap_name="${1:-}"
if [ -z "$snap_name" ]; then
    echo "Usage: $0 <snap-name>"
    echo
    echo "Example:"
    echo "  $0 gimp"
    exit 2
fi

if ! command -v snap >/dev/null 2>&1; then
    echo "snap command not found"
    exit 1
fi

if ! snap list "$snap_name" >/dev/null 2>&1; then
    echo "Snap is not installed: $snap_name"
    exit 1
fi

host_module="/usr/lib/x86_64-linux-gnu/gtk-3.0/modules/libappmenu-gtk-module.so"
host_parser="/usr/lib/x86_64-linux-gnu/libappmenu-gtk3-parser.so.0"
host_schema="/usr/share/glib-2.0/schemas/org.appmenu.gtk-module.gschema.xml"

for required in "$host_module" "$host_parser" "$host_schema"; do
    if [ ! -e "$required" ]; then
        echo "Missing host appmenu dependency: $required"
        exit 1
    fi
done

snap_user_common="$HOME/snap/$snap_name/common"
bundle_dir="$snap_user_common/fildem-gtk"
module_dir="$bundle_dir/gtk-3.0/modules"
lib_dir="$bundle_dir/lib"
schema_dir="$bundle_dir/glib-2.0/schemas"

mkdir -p "$module_dir" "$lib_dir" "$schema_dir"
install -m 0644 "$host_module" "$module_dir/libappmenu-gtk-module.so"
install -m 0644 "$host_parser" "$lib_dir/libappmenu-gtk3-parser.so.0"
install -m 0644 "$host_schema" "$schema_dir/org.appmenu.gtk-module.gschema.xml"
glib-compile-schemas "$schema_dir"

echo "Prepared snap-local appmenu module bundle:"
echo "  $bundle_dir"
echo

echo "Snap package:"
snap list "$snap_name"
echo

echo "Relevant snap connections:"
snap connections "$snap_name" | grep -E '(^Interface|desktop|gsettings|wayland|x11|dbus)' || true
echo

desktop_file="/var/lib/snapd/desktop/applications/${snap_name}_${snap_name}.desktop"
if [ -e "$desktop_file" ]; then
    echo "Launcher Exec lines:"
    grep -n '^Exec=' "$desktop_file" || true
    echo
fi

echo "Inside-snap appmenu environment probe:"
snap run --shell "$snap_name" -c '
    echo "  SNAP=$SNAP"
    echo "  GTK_MODULES=${GTK_MODULES-}"
    echo "  GTK_PATH=${GTK_PATH-}"
    echo "  GSETTINGS_SCHEMA_DIR=${GSETTINGS_SCHEMA_DIR-}"
    echo "  DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS-}"
    echo
    echo "  Can read copied module?"
    ls -l "'"$module_dir"'/libappmenu-gtk-module.so" "'"$lib_dir"'/libappmenu-gtk3-parser.so.0" "'"$schema_dir"'/gschemas.compiled"
' || true
echo

echo "Inside-snap DBus access probe:"
if snap run --shell "$snap_name" -c '
    gdbus call --session \
        --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.ListNames >/dev/null
    gdbus introspect --session \
        --dest com.canonical.AppMenu.Registrar \
        --object-path /com/canonical/AppMenu/Registrar >/dev/null
' >/tmp/fildem-snap-appmenu-probe.log 2>&1; then
    echo "  OK: snap can query session DBus and see Fildem registrar."
    echo
    echo "For a manual test launch, run:"
    echo "  snap run --shell $snap_name -c 'GTK_MODULES=$module_dir/libappmenu-gtk-module.so GTK_PATH=$bundle_dir:\$GTK_PATH LD_LIBRARY_PATH=$lib_dir:\$LD_LIBRARY_PATH GSETTINGS_SCHEMA_DIR=$schema_dir UBUNTU_MENUPROXY=1 <app-command>'"
else
    echo "  BLOCKED: snap AppArmor policy prevents the appmenu module from using session DBus."
    echo
    sed -n '1,80p' /tmp/fildem-snap-appmenu-probe.log | sed 's/^/  /'
    echo
    echo "This snap cannot support real Fildem/appmenu GTK export unless the snap package adds the needed DBus permissions,"
    echo "or it is rebuilt/installed with looser confinement. A launcher override alone will not fix it."
fi
