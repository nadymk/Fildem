import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS = 'es.inled.fildem';
const PATH = '/es/inled/fildem';
// Fildem's historical MyService methods/signals use the registrar interface
// name even though they live on the es.inled.fildem object.
const IFACE = 'com.canonical.AppMenu.Registrar';

class NativeMenuManager {
    constructor() {
        this._buttons = [];
        this._proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, null, BUS, PATH, IFACE, null);
        this._signal = this._proxy.connect('g-signal', (_p, _sender, signal, params) => {
            if (signal !== 'SendMenuTree') return;
            const [payload] = params.deep_unpack();
            try { this.setTree(JSON.parse(payload)); }
            catch (e) { logError(e, 'Fildem menu tree'); }
        });
        this._focus = global.display.connect('notify::focus-window', () => this._sendWindow());
        this._sendWindow();
    }

    _sendWindow() {
        const app = Shell.WindowTracker.get_default().focus_app;
        const win = global.display.get_focus_window();
        const data = {};
        if (win) {
            const desc = win.get_description() || '';
            const match = desc.match(/0x[0-9a-f]+/i);
            data.xid = match ? String(parseInt(match[0])) : '';
            for (const key of Object.keys(win)) {
                if (key.startsWith('gtk_') && win[key] !== null && win[key] !== undefined)
                    data[key] = String(win[key]);
            }
        }
        this._proxy.call('WindowSwitched', new GLib.Variant('(a{ss})', [data]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _activate(path) {
        this._proxy.call('EchoSignal', new GLib.Variant('(su)', [`__fildem_activate:${path}`, 0]),
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _build(items, menu) {
        for (const item of items) {
            if (item.children?.length) {
                const sub = new PopupMenu.PopupSubMenuMenuItem(item.label);
                this._build(item.children, sub.menu);
                menu.addMenuItem(sub);
            } else {
                const entry = new PopupMenu.PopupMenuItem(item.label);
                entry.setSensitive(item.enabled !== false);
                if (item.toggle) entry.setOrnament(PopupMenu.Ornament.CHECK);
                entry.connect('activate', () => this._activate(item.action));
                menu.addMenuItem(entry);
            }
        }
    }

    setTree(tree) {
        this._buttons.forEach(button => button.destroy());
        this._buttons = [];
        tree.forEach((item, index) => {
            const button = new PanelMenu.Button(0.0, item.label);
            button.add_child(new St.Label({ text: item.label, y_align: Clutter.ActorAlign.CENTER }));
            this._build(item.children || [], button.menu);
            Main.panel.addToStatusArea(`fildem-native-${index}`, button, index + 1, 'left');
            this._buttons.push(button);
        });
    }

    destroy() {
        if (this._focus) global.display.disconnect(this._focus);
        if (this._proxy && this._signal) this._proxy.disconnect(this._signal);
        this._buttons.forEach(button => button.destroy());
        this._buttons = [];
    }
}

export default class FildemExtension extends Extension {
    enable() { this._manager = new NativeMenuManager(); }
    disable() { this._manager?.destroy(); this._manager = null; }
}
