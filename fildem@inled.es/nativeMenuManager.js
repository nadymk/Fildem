import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import Shell from 'gi://Shell';

const BUS = 'es.inled.fildem';
const PATH = '/es/inled/fildem';
const IFACE = 'es.inled.fildem';

export class NativeMenuManager {
    constructor() {
        this._buttons = [];
        this._proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, null,
            BUS, PATH, IFACE, null);
        this._signalId = this._proxy.connect('g-signal', (_proxy, _sender, name, params) => {
            if (name !== 'SendMenuTree') return;
            const [payload] = params.deep_unpack();
            try {
                this._replaceMenus(JSON.parse(payload));
            } catch (error) {
                logError(error, 'Fildem menu tree');
            }
        });
        this._focusId = global.display.connect('notify::focus-window', () => this._sendWindow());
        this._sendWindow();
    }

    _sendWindow() {
        const window = global.display.get_focus_window();
        const data = {};
        if (window) {
            const description = window.get_description() || '';
            const match = description.match(/0x[0-9a-f]+/i);
            data.xid = match ? String(parseInt(match[0])) : '';
            const gtkProperties = [
                'gtk_unique_bus_name', 'gtk_application_object_path',
                'gtk_window_object_path', 'gtk_menubar_object_path',
                'gtk_app_menu_object_path',
            ];
            for (const property of gtkProperties) {
                const getter = `get_${property}`;
                if (typeof window[getter] !== 'function') continue;
                try {
                    const value = window[getter]();
                    if (value !== null && value !== undefined)
                        data[property] = String(value);
                } catch (error) {
                    logError(error, `Fildem ${getter}`);
                }
            }
        }
        this._proxy.call('WindowSwitched', new GLib.Variant('(a{ss})', [data]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _activate(action) {
        this._proxy.call(
            'EchoSignal',
            new GLib.Variant('(su)', [`__fildem_activate:${action}`, 0]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _label(text) {
        // GTK menu labels use '_' for mnemonics. GNOME Shell PopupMenu does
        // not interpret them, so remove the marker while retaining the text.
        return String(text ?? '').replace(/__/g, '\u0000').replace(/_/g, '').replace(/\u0000/g, '_');
    }

    _populate(items, menu) {
        for (const item of items) {
            if (item.separator) {
                menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                continue;
            }
            if (item.children?.length) {
                const submenu = new PopupMenu.PopupSubMenuMenuItem(this._label(item.label));
                this._populate(item.children, submenu.menu);
                // GNOME 50 can toggle the arrow without opening a nested
                // menu when the model is populated before the parent menu is
                // mapped. Explicitly open it after activation.
                submenu.connect('activate', () => {
                    submenu.menu.open();
                    // Keep the nested actor above the parent popup. This is
                    // a diagnostic for GNOME 50's nested-popup stacking.
                    if (submenu.menu.actor?.raise_top)
                        submenu.menu.actor.raise_top();
                });
                menu.addMenuItem(submenu);
                continue;
            }
            const entry = new PopupMenu.PopupMenuItem(this._label(item.label));
            entry.setSensitive(item.enabled !== false);
            if (item.toggle) entry.setOrnament(PopupMenu.Ornament.CHECK);
            entry.connect('activate', () => this._activate(item.action));
            menu.addMenuItem(entry);
        }
    }

    _replaceMenus(tree) {
        this._buttons.forEach(button => button.destroy());
        this._buttons = [];
        tree.forEach((item, index) => {
            const label = this._label(item.label);
            const button = new PanelMenu.Button(0.0, label);
            button.add_child(new St.Label({
                text: label,
                y_align: Clutter.ActorAlign.CENTER,
            }));
            this._populate(item.children || [], button.menu);
            Main.panel.addToStatusArea(`fildem-native-${index}`, button, index + 1, 'left');
            this._buttons.push(button);
        });
    }

    destroy() {
        this._buttons.forEach(button => button.destroy());
        this._buttons = [];
        if (this._proxy && this._signalId)
            this._proxy.disconnect(this._signalId);
        if (this._focusId)
            global.display.disconnect(this._focusId);
    }
}
