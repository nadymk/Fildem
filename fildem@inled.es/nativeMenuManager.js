import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

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
    }

    _activate(action) {
        this._proxy.call(
            'EchoSignal',
            new GLib.Variant('(su)', [`__fildem_activate:${action}`, 0]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _populate(items, menu) {
        for (const item of items) {
            if (item.separator) {
                menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                continue;
            }
            if (item.children?.length) {
                const submenu = new PopupMenu.PopupSubMenuMenuItem(item.label);
                this._populate(item.children, submenu.menu);
                menu.addMenuItem(submenu);
                continue;
            }
            const entry = new PopupMenu.PopupMenuItem(item.label);
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
            const button = new PanelMenu.Button(0.0, item.label);
            button.add_child(new St.Label({
                text: item.label,
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
    }
}
