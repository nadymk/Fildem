import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import Shell from 'gi://Shell';

const BUS = 'org.gnome.GlobalMenu';
const PATH = '/org/gnome/GlobalMenu';
const IFACE = 'org.gnome.GlobalMenu';

const KEYCODES = {
    ctrl: 29,
    shift: 42,
    alt: 56,
    left: 105,
    right: 106,
    tab: 15,
    escape: 1,
    delete: 111,
    f1: 59,
    f3: 61,
    f11: 87,
    comma: 51,
    plus: 13,
    minus: 12,
    0: 11,
    a: 30,
    b: 48,
    c: 46,
    d: 32,
    f: 33,
    h: 35,
    i: 23,
    j: 36,
    n: 49,
    o: 24,
    p: 25,
    q: 16,
    r: 19,
    s: 31,
    t: 20,
    u: 22,
    v: 47,
    w: 17,
    x: 45,
    z: 44,
};

export class NativeMenuManager {
    constructor(settings = null) {
        this._settings = settings;
        this._buttons = [];
        this._popupManagers = [];
        this._boxPopups = [];
        this._outsideOverlay = null;
        this._activeRootButton = null;
        this._menuTree = null;
        this._menuGeneration = 0;
        this._hoverSwitchId = 0;
        this._pointerDismissId = 0;
        this._startupRefreshId = 0;
        this._startupRefreshTries = 0;
        this._pendingFocusRefresh = false;
        this._focusOpenGuard = false;
        this._focusOpenGuardId = 0;
        this._proxyRetryId = 0;
        this._pendingWindowData = null;
        this._destroyed = false;
        // Keep a copy so we can restore the session environment when the
        // extension is disabled or reloaded.
        this._appMenuDisplayBothOriginal = GLib.getenv('APPMENU_DISPLAY_BOTH');
        this._appMenuDisplayBothSettingsId = this._settings?.connect('changed::keep-app-menubar', () => {
            this._applyAppMenuDisplayBothSetting();
        }) ?? 0;
        this._paddingSettingsId = this._settings?.connect('changed::min-padding', () => {
            this._buttons.forEach(button => this._applyPanelButtonStyle(button));
        }) ?? 0;
        this._leadingGapSettingsId = this._settings?.connect('changed::leading-gap', () => {
            if (this._menuTree)
                this._replaceMenus(this._menuTree);
        }) ?? 0;
        this._leadingWidthSettingsId = this._settings?.connect('changed::leading-column-width', () => {
            if (this._menuTree)
                this._replaceMenus(this._menuTree);
        }) ?? 0;
        this._hoverDelaySettingsId = this._settings?.connect('changed::hover-switch-delay', () => {
            this._cancelHoverSwitch();
        }) ?? 0;
        this._maxWidthSettingsId = this._settings?.connect('changed::max-menu-width-percent', () => {
            this._buttons.forEach(button => {
                button._fildemBoxPopup?.destroy();
                button._fildemBoxPopup = null;
            });
            this._boxPopups = this._boxPopups.filter(popup => popup.get_parent());
        }) ?? 0;
        this._proxy = null;
        this._signalId = 0;
        this._applyAppMenuDisplayBothSetting();
        this._connectProxy();
        this._focusId = global.display.connect('notify::focus-window', () => {
            if (this._focusOpenGuard)
                return;
            if (this._anyBoxPopupVisible()) {
                this._pendingFocusRefresh = true;
                return;
            }
            this._sendWindow();
        });
        this._workspaceId = global.workspace_manager.connect('active-workspace-changed',
            () => this._closeBoxPopups());
        this._overviewShownId = Main.overview.connect('shown', () => this._closeBoxPopups());
        this._overviewHiddenId = Main.overview.connect('hidden', () => this._closeBoxPopups());
        this._stageId = global.stage.connect('captured-event', (_stage, event) => {
            if (event.type() !== Clutter.EventType.BUTTON_PRESS &&
                event.type() !== Clutter.EventType.TOUCH_BEGIN)
                return Clutter.EVENT_PROPAGATE;
            const [x, y] = event.get_coords();
            const inside = actor => {
                if (!actor?.visible)
                    return false;
                const [ax, ay] = actor.get_transformed_position();
                const [aw, ah] = actor.get_transformed_size();
                return x >= ax && x <= ax + aw && y >= ay && y <= ay + ah;
            };
            const popupActors = [...this._boxPopups, ...this._buttons];
            if (this._boxPopups.some(popup => popup.visible) &&
                !popupActors.some(inside))
                this._closeBoxPopups();
            return Clutter.EVENT_PROPAGATE;
        });
        this._startupCompleteId = Main.layoutManager.connect('startup-complete', () => {
            this._sendWindow();
        });
        this._sendWindow();
        this._scheduleStartupRefresh();
    }

    _scheduleProxyRetry() {
        if (this._destroyed || this._proxyRetryId)
            return;
        this._proxyRetryId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._proxyRetryId = 0;
            if (!this._destroyed && !this._proxy)
                this._connectProxy();
            return GLib.SOURCE_REMOVE;
        });
    }

    _connectProxy() {
        if (this._destroyed || this._proxy)
            return true;
        try {
            this._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                null,
                BUS, PATH, IFACE, null);
        } catch (error) {
            this._scheduleProxyRetry();
            return false;
        }

        this._signalId = this._proxy.connect('g-signal', (_proxy, _sender, name, params) => {
            if (name !== 'MenuBarChanged' && name !== 'MenuUpdated')
                return;
            const unpacked = params.deep_unpack();
            if (name === 'MenuBarChanged' && unpacked.length > 0)
                this._menuGeneration = Number(unpacked[0] ?? 0);
            this._menuTree = null;
            this._loadMenuTree(tree => {
                this._menuTree = tree;
                this._replaceMenus(tree);
                if (tree?.length)
                    this._cancelStartupRefresh();
            }, 0, false, false);
        });

        if (this._pendingWindowData) {
            const pending = this._pendingWindowData;
            this._pendingWindowData = null;
            this._sendActiveWindowData(pending);
        }
        return true;
    }

    _sendActiveWindowData(variantData) {
        if (this._destroyed)
            return false;
        if (!this._proxy && !this._connectProxy()) {
            this._pendingWindowData = variantData;
            return false;
        }
        try {
            this._proxy.call('SetActiveWindow', new GLib.Variant('(a{sv})', [variantData]),
                Gio.DBusCallFlags.NONE, -1, null, null);
            this._pendingWindowData = null;
            return true;
        } catch (error) {
            this._pendingWindowData = variantData;
            this._scheduleProxyRetry();
            return false;
        }
    }

    _scheduleStartupRefresh() {
        if (this._destroyed || this._startupRefreshId)
            return;
        this._startupRefreshTries = 0;
        this._startupRefreshId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._destroyed) {
                this._startupRefreshId = 0;
                return GLib.SOURCE_REMOVE;
            }
            if (this._menuTree && this._buttons.length) {
                this._startupRefreshId = 0;
                return GLib.SOURCE_REMOVE;
            }
            if (this._startupRefreshTries >= 120) {
                this._startupRefreshId = 0;
                return GLib.SOURCE_REMOVE;
            }
            this._startupRefreshTries += 1;
            this._sendWindow();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _cancelStartupRefresh() {
        if (!this._startupRefreshId)
            return;
        GLib.source_remove(this._startupRefreshId);
        this._startupRefreshId = 0;
    }

    _isPointInsideOpenMenu(x, y) {
        const inside = actor => {
            if (!actor?.visible)
                return false;
            const [ax, ay] = actor.get_transformed_position();
            const [aw, ah] = actor.get_transformed_size();
            return x >= ax && x <= ax + aw && y >= ay && y <= ay + ah;
        };
        return [...this._boxPopups, ...this._buttons].some(inside);
    }

    _anyBoxPopupVisible() {
        return this._boxPopups.some(popup => popup.visible);
    }

    _startPointerDismissWatch() {
        if (this._pointerDismissId)
            return;
        this._pointerDismissId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 40, () => {
            if (!this._anyBoxPopupVisible()) {
                this._pointerDismissId = 0;
                return GLib.SOURCE_REMOVE;
            }
            const [x, y, mods] = global.get_pointer();
            const buttonMask =
                (Clutter.ModifierType.BUTTON1_MASK ?? 0) |
                (Clutter.ModifierType.BUTTON2_MASK ?? 0) |
                (Clutter.ModifierType.BUTTON3_MASK ?? 0);
            if ((mods & buttonMask) !== 0 && !this._isPointInsideOpenMenu(x, y))
                this._closeBoxPopups();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopPointerDismissWatch() {
        if (!this._pointerDismissId)
            return;
        GLib.source_remove(this._pointerDismissId);
        this._pointerDismissId = 0;
    }

    _closeBoxPopups() {
        if (this._destroyed)
            return;
        this._cancelHoverSwitch();
        for (const popup of this._boxPopups)
            popup.hide();
        this._outsideOverlay?.hide();
        this._setActiveRootButton(null);
        this._stopPointerDismissWatch();
        if (this._pendingFocusRefresh) {
            this._pendingFocusRefresh = false;
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                if (!this._destroyed)
                    this._sendWindow();
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _cancelHoverSwitch() {
        if (!this._hoverSwitchId)
            return;
        GLib.source_remove(this._hoverSwitchId);
        this._hoverSwitchId = 0;
    }

    _scheduleHoverSwitch(callback) {
        this._cancelHoverSwitch();
        const delay = this._settings
            ? Math.max(0, Math.min(3000, this._settings.get_int('hover-switch-delay')))
            : 1000;
        this._hoverSwitchId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
            this._hoverSwitchId = 0;
            callback();
            return GLib.SOURCE_REMOVE;
        });
    }

    _setFocusOpenGuard(durationMs = 200) {
        if (this._destroyed || this._focusOpenGuardId)
            return;
        this._focusOpenGuard = true;
        this._focusOpenGuardId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, durationMs, () => {
            this._focusOpenGuardId = 0;
            this._focusOpenGuard = false;
            return GLib.SOURCE_REMOVE;
        });
    }

    _showBoxPopup(popup) {
        this._setFocusOpenGuard();
        const keep = new Set();
        for (let current = popup; current; current = current._fildemParent)
            keep.add(current);
        for (const other of this._boxPopups) {
            if (!keep.has(other))
                other.hide();
        }
        popup.show();
        this._startPointerDismissWatch();
    }

    _setActiveRootButton(button) {
        if (this._activeRootButton === button)
            return;
        const current = this._activeRootButton;
        this._activeRootButton = null;
        if (current && !current._fildemDestroyed) {
            try {
                current.remove_style_pseudo_class('active');
                current.remove_style_pseudo_class('checked');
            } catch (error) {
                logError(error, 'Fildem active button cleanup');
            }
        }
        this._activeRootButton = button;
        if (this._activeRootButton && !this._activeRootButton._fildemDestroyed) {
            try {
                this._activeRootButton.add_style_pseudo_class('active');
                this._activeRootButton.add_style_pseudo_class('checked');
            } catch (error) {
                logError(error, 'Fildem active button apply');
            }
        }
    }

    _showRootPopup(button) {
        if (this._destroyed || !button || button._fildemDestroyed)
            return;
        const popup = button._fildemBoxPopup;
        this._setFocusOpenGuard();
        popup.setPosition(button, 0.0);
        popup.show();
        this._setActiveRootButton(button);
        this._startPointerDismissWatch();

        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            if (this._destroyed || button._fildemDestroyed || !popup.visible)
                return GLib.SOURCE_REMOVE;
            const [buttonX] = button.get_transformed_position();
            const [, popupY] = popup.get_position();
            popup.set_position(Math.round(buttonX), popupY);
            return GLib.SOURCE_REMOVE;
        });
    }

    _ensureOutsideOverlay() {
        if (this._outsideOverlay)
            return;
        this._outsideOverlay = new St.Widget({reactive: true});
        this._outsideOverlay.set_position(0, 0);
        this._outsideOverlay.set_size(global.stage.width, global.stage.height);
        this._outsideOverlay.connect('button-press-event', () => {
            this._closeBoxPopups();
            return Clutter.EVENT_PROPAGATE;
        });
        Main.uiGroup.add_child(this._outsideOverlay);
        if (this._boxPopups[0])
            Main.uiGroup.set_child_below_sibling(this._outsideOverlay, this._boxPopups[0]);
        this._outsideOverlay.hide();
    }

    _sendWindow() {
        this._closeBoxPopups();
        this._menuTree = null;
        const window = global.display.get_focus_window();
        const data = {};
        if (window) {
            data.title = String(window.get_title?.() || '');
            data.wmClass = String(window.get_wm_class?.() || '');
            try {
                const app = Shell.WindowTracker.get_default().get_window_app(window);
                if (app) {
                    data.appName = String(app.get_name?.() || '');
                    data.appId = String(app.get_id?.() || '');
                }
            } catch (error) {
                logError(error, 'Fildem get_window_app');
            }
            const description = window.get_description() || '';
            const match = description.match(/0x[0-9a-f]+/i);
            data.xid = match ? String(parseInt(match[0])) : '';
            if (typeof window.get_pid === 'function') {
                try {
                    const pid = window.get_pid();
                    if (pid)
                        data.pid = String(pid);
                } catch (error) {
                    logError(error, 'Fildem get_pid');
                }
            }
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
        const variantData = {};
        for (const [key, value] of Object.entries(data)) {
            if (value === undefined || value === null || value === '')
                continue;
            if (key === 'pid' || key === 'xid')
                variantData[key] = GLib.Variant.new_int32(Number(value) || 0);
            else
                variantData[key] = GLib.Variant.new_string(String(value));
        }
        this._pendingWindowData = variantData;
        this._sendActiveWindowData(variantData);
    }

    _activate(action) {
        if (this._activateSynthetic(action))
            return;
        if (!this._proxy && !this._connectProxy())
            return;
        try {
            this._proxy.call('Activate',
                new GLib.Variant('(us)', [this._menuGeneration, String(action)]),
                Gio.DBusCallFlags.NONE, -1, null, null);
        } catch (error) {
            this._scheduleProxyRetry();
        }
    }

    _activateSynthetic(action) {
        if (!String(action).startsWith('__fildem_shell_key:'))
            return false;

        const sequence = String(action).slice('__fildem_shell_key:'.length);
        const seat = Clutter.get_default_backend().get_default_seat();
        const keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        if (!keyboard)
            return true;

        const pressChord = chord => {
            const keys = chord.split('+').map(part => part.trim().toLowerCase()).filter(Boolean);
            const codes = keys.map(key => KEYCODES[key]).filter(code => code);
            if (!codes.length)
                return;

            const timeUs = GLib.get_monotonic_time();
            let offset = 0;
            for (const code of codes.slice(0, -1)) {
                keyboard.notify_key(timeUs + offset, code, Clutter.KeyState.PRESSED);
                offset += 10;
            }
            keyboard.notify_key(timeUs + offset, codes[codes.length - 1], Clutter.KeyState.PRESSED);
            offset += 10;
            keyboard.notify_key(timeUs + offset, codes[codes.length - 1], Clutter.KeyState.RELEASED);
            offset += 10;
            for (const code of codes.slice(0, -1).reverse()) {
                keyboard.notify_key(timeUs + offset, code, Clutter.KeyState.RELEASED);
                offset += 10;
            }
        };

        const chords = sequence.split(',').map(chord => chord.trim()).filter(Boolean);
        this._closeBoxPopups();
        for (const [index, chord] of chords.entries()) {
            if (index === 0) {
                pressChord(chord);
                continue;
            }
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, index * 120, () => {
                pressChord(chord);
                return GLib.SOURCE_REMOVE;
            });
        }
        return true;
    }

    _loadMenuTree(callback, tries = 0, force = false, retryOnEmpty = true) {
        if (this._menuTree && !force) {
            callback(this._menuTree);
            return;
        }
        if (!this._proxy && !this._connectProxy()) {
            if (retryOnEmpty && tries < 6) {
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250 * (tries + 1), () => {
                    this._loadMenuTree(callback, tries + 1, force, retryOnEmpty);
                    return GLib.SOURCE_REMOVE;
                });
                return;
            }
            if (!retryOnEmpty) {
                this._menuTree = [];
                callback(this._menuTree);
                return;
            }
            callback([]);
            return;
        }
        try {
            this._proxy.call(
                'GetMenuBar',
                null,
                Gio.DBusCallFlags.NONE,
                -1,
                null,
                (_proxy, result) => {
                    try {
                        const [payload] = this._proxy.call_finish(result).deep_unpack();
                        const bar = JSON.parse(payload);
                        const tree = Array.isArray(bar) ? bar : (bar?.menus ?? []);
                        this._menuGeneration = Number(bar?.generation ?? this._menuGeneration ?? 0);
                        if (!tree.length && retryOnEmpty && tries < 6) {
                            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250 * (tries + 1), () => {
                                this._loadMenuTree(callback, tries + 1, force, retryOnEmpty);
                                return GLib.SOURCE_REMOVE;
                            });
                            return;
                        }
                        this._menuTree = tree;
                        callback(this._menuTree);
                    } catch (error) {
                        if (retryOnEmpty && tries < 6) {
                            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250 * (tries + 1), () => {
                                this._loadMenuTree(callback, tries + 1, force, retryOnEmpty);
                                return GLib.SOURCE_REMOVE;
                            });
                            return;
                        }
                        if (!retryOnEmpty) {
                            this._menuTree = [];
                            callback(this._menuTree);
                            return;
                        }
                        logError(error, 'Fildem GetMenuBar');
                    }
                });
        } catch (error) {
            this._scheduleProxyRetry();
            if (retryOnEmpty && tries < 6) {
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250 * (tries + 1), () => {
                    this._loadMenuTree(callback, tries + 1, force, retryOnEmpty);
                    return GLib.SOURCE_REMOVE;
                });
                return;
            }
            if (!retryOnEmpty) {
                this._menuTree = [];
                callback(this._menuTree);
                return;
            }
            logError(error, 'Fildem GetMenuBar');
        }
    }

    _label(text) {
        // GTK labels use '_' for mnemonics and Qt labels use '&'. GNOME Shell
        // does not interpret either marker, so remove them while preserving
        // escaped literal characters.
        return String(text ?? '')
            .replace(/__/g, '\u0000').replace(/_/g, '').replace(/\u0000/g, '_')
            .replace(/&&/g, '\u0000').replace(/&/g, '').replace(/\u0000/g, '&');
    }

    _shortcut(text) {
        return String(text ?? '')
            .replace(/<Primary>/g, 'Ctrl+')
            .replace(/<Control>/g, 'Ctrl+')
            .replace(/<Ctrl>/g, 'Ctrl+')
            .replace(/<Shift>/g, 'Shift+')
            .replace(/<Alt>/g, 'Alt+')
            .replace(/<Super>/g, 'Super+')
            .replace(/<Meta>/g, 'Meta+')
            .replace(/<Command>/g, 'Cmd+')
            .replace(/>/g, '')
            .replace(/</g, '')
            .replace(/\+plus$/i, '++')
            .replace(/\+minus$/i, '+−');
    }

    _iconBytes(iconData) {
        if (!iconData)
            return [];
        if (iconData instanceof Uint8Array)
            return Array.from(iconData);
        if (Array.isArray(iconData)) {
            if (iconData.length > 0 && iconData.every(value =>
                Number.isInteger(value) && value >= 0 && value <= 255))
                return iconData;
            for (const value of iconData) {
                const bytes = this._iconBytes(value);
                if (bytes.length)
                    return bytes;
            }
        }
        if (typeof iconData === 'object') {
            for (const value of Object.values(iconData)) {
                const bytes = this._iconBytes(value);
                if (bytes.length)
                    return bytes;
            }
        }
        return [];
    }

    _createDataIconActor(iconData) {
        const bytes = this._iconBytes(iconData);
        if (!bytes.length)
            return null;

        try {
            const gbytes = GLib.Bytes.new(Uint8Array.from(bytes));
            const gicon = Gio.BytesIcon.new(gbytes);
            return new St.Icon({
                gicon,
                icon_size: 16,
                y_align: Clutter.ActorAlign.CENTER,
            });
        } catch (error) {
            logError(error, 'Fildem icon data');
            return null;
        }
    }

    _createIconActor(item) {
        const iconName = String(item.iconName ?? '');
        if (iconName) {
            return new St.Icon({
                gicon: Gio.ThemedIcon.new(iconName),
                icon_size: 16,
                y_align: Clutter.ActorAlign.CENTER,
            });
        }

        return this._createDataIconActor(item.iconData) ?? this._leadingPlaceholder();
    }

    _createStateActor(item) {
        if (!item.toggleType && !item.toggle)
            return this._leadingPlaceholder();

        const isActive = Boolean(item.toggle);
        const isRadio = item.toggleType === 'radio';
        return new St.Label({
            text: isRadio ? (isActive ? '◉' : '◯') : (isActive ? '☑' : '☐'),
            style_class: 'popup-menu-ornament',
            y_align: Clutter.ActorAlign.CENTER,
        });
    }

    _itemHasLeadingGraphic(item) {
        return Boolean(item?.toggle ||
            String(item?.toggleType ?? '') ||
            String(item?.iconName ?? '') ||
            this._iconBytes(item?.iconData).length);
    }

    _sectionKey(item) {
        if (!item || item.section === undefined || item.section === null)
            return '';
        return JSON.stringify(item.section);
    }

    _itemsNeedIconColumn(items) {
        return items.some(item => {
            if (item.separator)
                return false;
            return this._itemHasLeadingGraphic(item);
        });
    }

    _maxMenuWidthPercent() {
        return Math.max(10, Math.min(80, this._settingInt('max-menu-width-percent', 33)));
    }

    _createMenuRow(item, hasChildren = false, showIconColumn = false) {
        const row = new St.Button({
            style_class: 'popup-menu-item',
            x_expand: true,
            reactive: item.enabled !== false,
            can_focus: item.enabled !== false,
        });
        if (item.enabled === false)
            row.add_style_pseudo_class('insensitive');

        const rowBox = new St.BoxLayout({
            x_expand: true,
            style: 'spacing: 0px;',
        });
        const leading = new St.BoxLayout({
            x_expand: false,
            y_align: Clutter.ActorAlign.CENTER,
            style: `width: ${this._leadingColumnWidth()}px;`,
        });
        if (showIconColumn) {
            const graphic = new St.BoxLayout({
                style: `spacing: ${this._leadingGap()}px;`,
                y_align: Clutter.ActorAlign.CENTER,
            });
            graphic.add_child(this._createStateActor(item));
            graphic.add_child(this._itemHasLeadingGraphic(item)
                ? this._createIconActor(item)
                : this._leadingPlaceholder());
            leading.add_child(graphic);
        }
        rowBox.add_child(leading);

        const label = new St.Label({
            text: this._label(item.label),
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        label.clutter_text.set_single_line_mode(true);
        label.clutter_text.set_ellipsize(Pango.EllipsizeMode.END);
        rowBox.add_child(label);

        rowBox.add_child(new St.Widget({x_expand: true}));

        const hint = this._shortcut(item.shortcut || item.accel || '');
        if (hint) {
            rowBox.add_child(new St.Label({
                text: hint,
                style_class: 'popup-menu-accelerator',
                style: 'opacity: 0.65; margin-left: 18px;',
                x_align: Clutter.ActorAlign.END,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }

        if (hasChildren) {
            rowBox.add_child(new St.Icon({
                icon_name: 'go-next-symbolic',
                style_class: 'popup-menu-arrow',
                icon_size: 12,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }

        row.set_child(rowBox);
        return row;
    }

    _panelPadding() {
        return this._settingInt('min-padding', 6);
    }

    _leadingGap() {
        return Math.max(0, Math.min(32, this._settingInt('leading-gap', 10)));
    }

    _leadingColumnWidth() {
        return Math.max(0, Math.min(48, this._settingInt('leading-column-width', 18)));
    }

    _settingInt(key, fallback) {
        if (!this._settings)
            return fallback;
        try {
            return this._settings.get_int(key);
        } catch (error) {
            logError(error, `Fildem settings fallback for ${key}`);
            return fallback;
        }
    }

    _settingBool(key, fallback) {
        if (!this._settings)
            return fallback;
        try {
            return this._settings.get_boolean(key);
        } catch (error) {
            logError(error, `Fildem settings fallback for ${key}`);
            return fallback;
        }
    }

    _applyAppMenuDisplayBothSetting() {
        const keepVisible = this._settingBool('keep-app-menubar', false);
        if (keepVisible) {
            // Appmenu-based GTK and Qt apps can keep both menus visible via
            // this session env toggle.
            GLib.setenv('APPMENU_DISPLAY_BOTH', '1', true);
            return;
        }
        GLib.unsetenv('APPMENU_DISPLAY_BOTH');
    }

    _restoreAppMenuDisplayBothSetting() {
        if (this._appMenuDisplayBothOriginal !== null && this._appMenuDisplayBothOriginal !== undefined)
            GLib.setenv('APPMENU_DISPLAY_BOTH', this._appMenuDisplayBothOriginal, true);
        else
            GLib.unsetenv('APPMENU_DISPLAY_BOTH');
    }

    _leadingPlaceholder() {
        return new St.Widget({style: `width: ${this._leadingColumnWidth()}px;`});
    }

    _createSeparatorActor() {
        return new PopupMenu.PopupSeparatorMenuItem().actor;
    }

    _applyPanelButtonStyle(button) {
        const padding = Math.max(0, Math.min(50, this._panelPadding()));
        button.set_style(`-natural-hpadding: ${padding}px; -minimum-hpadding: ${padding}px; padding-left: ${padding}px; padding-right: ${padding}px;`);
    }

    _createBoxPopup(sourceActor, content, side = St.Side.TOP) {
        const popup = new BoxPointer.BoxPointer(side, {});
        popup.add_style_class_name('popup-menu-boxpointer');
        // BoxPointer normally mutes all captured input for menu management.
        // These custom menus have their own stage-level dismissal handling;
        // unmute the BoxPointer so touch gestures reach St.ScrollView.
        popup._unmuteInput?.();
        popup.bin.set_child(content);
        Main.uiGroup.add_child(popup);
        popup.setPosition(sourceActor, 0.0);
        popup.hide();
        popup.connect('captured-event', (_actor, event) => {
            if (event.type() !== Clutter.EventType.BUTTON_PRESS)
                return Clutter.EVENT_PROPAGATE;
            const [x, y] = event.get_coords();
            const inside = actor => {
                if (!actor?.visible)
                    return false;
                const [ax, ay] = actor.get_transformed_position();
                const [aw, ah] = actor.get_transformed_size();
                return x >= ax && x <= ax + aw && y >= ay && y <= ay + ah;
            };
            const insideMenu = this._boxPopups.some(menu => inside(menu)) ||
                this._buttons.some(button => inside(button));
            if (!insideMenu)
                this._closeBoxPopups();
            return Clutter.EVENT_PROPAGATE;
        });
        this._boxPopups.push(popup);
        return popup;
    }

    _buildBoxPopup(items, sourceActor, side = St.Side.TOP) {
        const monitor = Main.layoutManager.primaryMonitor;
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor.index);
        const maxWidth = Math.max(160, Math.floor(workArea.width * this._maxMenuWidthPercent() / 100));
        const showIconColumn = this._itemsNeedIconColumn(items);
        const scroll = new St.ScrollView({
            x_expand: true,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            hscrollbar_policy: St.PolicyType.NEVER,
        });
        scroll.set_touch_scrolling?.(true);
        scroll.set_mouse_scrolling?.(true);
        let touchStartY = null;
        let touchLastY = null;
        let touchMoved = false;
        scroll.connect('captured-event', (_actor, event) => {
            const type = event.type();
            if (type !== Clutter.EventType.TOUCH_BEGIN &&
                type !== Clutter.EventType.TOUCH_UPDATE &&
                type !== Clutter.EventType.TOUCH_END &&
                type !== Clutter.EventType.TOUCH_CANCEL)
                return Clutter.EVENT_PROPAGATE;
            const adjustment = scroll.vadjustment ?? scroll.vscroll?.adjustment;
            if (!adjustment)
                return Clutter.EVENT_PROPAGATE;
            const [, y] = event.get_coords();
            if (type === Clutter.EventType.TOUCH_BEGIN) {
                touchStartY = y;
                touchLastY = y;
                touchMoved = false;
                return Clutter.EVENT_PROPAGATE;
            }
            if (type === Clutter.EventType.TOUCH_UPDATE && touchLastY !== null) {
                const delta = y - touchLastY;
                touchLastY = y;
                if (touchStartY !== null && Math.abs(y - touchStartY) > 8)
                    touchMoved = true;
                const max = Math.max(0, adjustment.upper - adjustment.page_size);
                adjustment.value = Math.max(0, Math.min(max, adjustment.value - delta));
                return touchMoved ? Clutter.EVENT_STOP : Clutter.EVENT_PROPAGATE;
            }
            touchStartY = null;
            touchLastY = null;
            const stop = touchMoved;
            touchMoved = false;
            return stop ? Clutter.EVENT_STOP : Clutter.EVENT_PROPAGATE;
        });
        scroll.add_style_class_name('popup-menu-content');
        scroll.set_style(`max-height: ${Math.max(200, workArea.height * 0.8)}px; max-width: ${maxWidth}px;`);
        const box = new St.BoxLayout({vertical: true});
        scroll.set_child(box);
        const popup = this._createBoxPopup(sourceActor, scroll, side);
        let previousSection = null;
        for (const item of items) {
            if (item.separator) {
                box.add_child(this._createSeparatorActor());
                previousSection = null;
                continue;
            }
            const sectionKey = this._sectionKey(item);
            if (previousSection !== null && sectionKey !== previousSection)
                box.add_child(this._createSeparatorActor());
            previousSection = sectionKey;
            if (item.children?.length) {
                const row = this._createMenuRow(item, true, showIconColumn);
                box.add_child(row);
                row.connect('clicked', () => {
                    if (!row._fildemChildPopup) {
                        row._fildemChildPopup = this._buildBoxPopup(item.children, row, St.Side.RIGHT);
                        row._fildemChildPopup._fildemParent = popup;
                    }
                    const child = row._fildemChildPopup;
                    child.setPosition(row, 0.0);
                    this._showBoxPopup(child);
                });
                row.connect('enter-event', () => {
                    if (!popup.visible)
                        return Clutter.EVENT_PROPAGATE;
                    this._scheduleHoverSwitch(() => {
                        if (!popup.visible)
                            return;
                        if (!row._fildemChildPopup) {
                            row._fildemChildPopup = this._buildBoxPopup(item.children, row, St.Side.RIGHT);
                            row._fildemChildPopup._fildemParent = popup;
                        }
                        const child = row._fildemChildPopup;
                        child.setPosition(row, 0.0);
                        this._showBoxPopup(child);
                    });
                    return Clutter.EVENT_PROPAGATE;
                });
                continue;
            }
            const row = this._createMenuRow(item, false, showIconColumn);
            box.add_child(row);
            row.connect('enter-event', () => {
                if (popup.visible)
                    this._scheduleHoverSwitch(() => {
                        if (popup.visible)
                            this._showBoxPopup(popup);
                    });
                return Clutter.EVENT_PROPAGATE;
            });
            row.connect('clicked', () => {
                if (item.enabled !== false)
                    this._activate(item.action);
            });
        }
        return popup;
    }

    _populate(items, menu, popupManager = null) {
        for (const item of items) {
            if (item.separator) {
                menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                continue;
            }
            if (item.children?.length) {
                const submenu = new PopupMenu.PopupBaseMenuItem({reactive: true});
                const label = new St.Label({text: this._label(item.label), x_expand: true});
                const arrow = new St.Label({text: '›'});
                submenu.add_child(label);
                submenu.add_child(arrow);
                const popup = new PopupMenu.PopupMenu(submenu.actor, 0.0, St.Side.RIGHT);
                this._populate(item.children, popup, popupManager);
                if (popupManager)
                    popupManager.addMenu(popup);
                submenu.connect('activate', () => {
                    GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                        if (!popup.isOpen)
                            popup.open();
                        return GLib.SOURCE_REMOVE;
                    });
                });
                popup.connect('open-state-changed', (_popup, open) => {
                    arrow.text = open ? '‹' : '›';
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

    _limitMenu(menu) {
        menu.actor.add_style_class_name('fildem-bounded-menu');
        const monitor = Main.layoutManager.findMonitorForActor(menu.actor) ?? Main.layoutManager.primaryMonitor;
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor.index);
        const maxHeight = Math.max(200, workArea.height - 80);
        menu.actor.set_style(`max-height: ${maxHeight}px;`);
    }

    _replaceMenus(tree) {
        this._menuTree = tree;
        this._replaceMenuButtons(tree.map(item => item.label));
        for (const [index, item] of tree.entries()) {
            if (this._buttons[index])
                this._buttons[index]._fildemMenuChildren = item.children || [];
        }
    }

    _replaceMenuButtons(labels) {
        this._outsideOverlay?.destroy();
        this._outsideOverlay = null;
        this._boxPopups.forEach(popup => popup.destroy());
        this._boxPopups = [];
        this._buttons.forEach(button => {
            button._fildemBoxPopup = null;
            button.destroy();
        });
        this._popupManagers = [];
        this._buttons = [];
        labels.forEach((rawLabel, index) => {
            const label = this._label(rawLabel);
            const button = new PanelMenu.Button(0.0, label);
            button._fildemDestroyed = false;
            button.connect('destroy', () => {
                button._fildemDestroyed = true;
                if (this._activeRootButton === button)
                    this._activeRootButton = null;
            });
            this._applyPanelButtonStyle(button);
            // GNOME 50 no longer reliably toggles extension-created menus
            // through PanelMenu.Button's legacy click action. Install the
            // popup and an explicit ClickGesture, as current GNOME extensions
            // do.
            button.setMenu(new PopupMenu.PopupMenu(button, 0.0, St.Side.TOP));
            if (button._clickGesture)
                button.remove_action(button._clickGesture);
            button._fildemClickGesture = new Clutter.ClickGesture();
            button._fildemClickGesture.set_recognize_on_press(true);
            button.menu.actor.hide();
            button._fildemMenuChildren = null;
            button._fildemClickGesture.connect('recognize', () => {
                if (this._destroyed || button._fildemDestroyed)
                    return;
                for (const other of this._buttons) {
                    if (other !== button)
                        other._fildemBoxPopup?.hide();
                }
                if (!button._fildemMenuChildren) {
                    this._loadMenuTree(tree => {
                        const item = tree[index];
                        if (!item)
                            return;
                        button._fildemMenuChildren = item.children || [];
                        button._fildemBoxPopup = this._buildBoxPopup(button._fildemMenuChildren, button);
                        this._closeBoxPopups();
                        this._showRootPopup(button);
                    });
                    return;
                }
                if (!button._fildemBoxPopup)
                    button._fildemBoxPopup = this._buildBoxPopup(button._fildemMenuChildren, button);
                if (button._fildemBoxPopup.visible) {
                    this._closeBoxPopups();
                }
                else {
                    this._closeBoxPopups();
                    this._showRootPopup(button);
                }
            });
            button.add_action(button._fildemClickGesture);
            button.connect('enter-event', () => {
                if (this._destroyed || button._fildemDestroyed)
                    return Clutter.EVENT_PROPAGATE;
                if (!this._activeRootButton || this._activeRootButton === button)
                    return Clutter.EVENT_PROPAGATE;
                this._scheduleHoverSwitch(() => {
                    if (this._destroyed || button._fildemDestroyed)
                        return;
                    if (!this._activeRootButton || this._activeRootButton === button)
                        return;
                    if (!button._fildemMenuChildren) {
                        this._loadMenuTree(tree => {
                            if (this._destroyed || button._fildemDestroyed)
                                return;
                            const item = tree[index];
                            if (!item || !this._activeRootButton)
                                return;
                            button._fildemMenuChildren = item.children || [];
                            button._fildemBoxPopup = this._buildBoxPopup(button._fildemMenuChildren, button);
                            this._closeBoxPopups();
                            this._showRootPopup(button);
                        });
                        return;
                    }
                    if (!button._fildemBoxPopup)
                        button._fildemBoxPopup = this._buildBoxPopup(button._fildemMenuChildren, button);
                    this._closeBoxPopups();
                    this._showRootPopup(button);
                });
                return Clutter.EVENT_PROPAGATE;
            });
            const buttonLabel = new St.Label({
                text: label,
                y_align: Clutter.ActorAlign.CENTER,
                x_expand: false,
            });
            buttonLabel.clutter_text.set_ellipsize(Pango.EllipsizeMode.NONE);
            button.add_child(buttonLabel);
            Main.panel.addToStatusArea(`fildem-native-${index}`, button, index + 1, 'left');
            this._buttons.push(button);
        });
    }

    destroy() {
        this._destroyed = true;
        this._cancelHoverSwitch();
        this._stopPointerDismissWatch();
        if (this._proxyRetryId) {
            GLib.source_remove(this._proxyRetryId);
            this._proxyRetryId = 0;
        }
        if (this._focusOpenGuardId) {
            GLib.source_remove(this._focusOpenGuardId);
            this._focusOpenGuardId = 0;
        }
        this._focusOpenGuard = false;
        this._outsideOverlay?.destroy();
        this._outsideOverlay = null;
        this._boxPopups.forEach(popup => popup.destroy());
        this._boxPopups = [];
        this._buttons.forEach(button => {
            button._fildemBoxPopup = null;
            button.destroy();
        });
        this._buttons = [];
        if (this._proxy && this._signalId)
            this._proxy.disconnect(this._signalId);
        if (this._focusId)
            global.display.disconnect(this._focusId);
        if (this._workspaceId)
            global.workspace_manager.disconnect(this._workspaceId);
        if (this._overviewShownId)
            Main.overview.disconnect(this._overviewShownId);
        if (this._overviewHiddenId)
            Main.overview.disconnect(this._overviewHiddenId);
        if (this._stageId)
            global.stage.disconnect(this._stageId);
        if (this._startupCompleteId)
            Main.layoutManager.disconnect(this._startupCompleteId);
        if (this._settings && this._paddingSettingsId)
            this._settings.disconnect(this._paddingSettingsId);
        if (this._settings && this._appMenuDisplayBothSettingsId)
            this._settings.disconnect(this._appMenuDisplayBothSettingsId);
        if (this._settings && this._leadingGapSettingsId)
            this._settings.disconnect(this._leadingGapSettingsId);
        if (this._settings && this._leadingWidthSettingsId)
            this._settings.disconnect(this._leadingWidthSettingsId);
        if (this._settings && this._hoverDelaySettingsId)
            this._settings.disconnect(this._hoverDelaySettingsId);
        if (this._settings && this._maxWidthSettingsId)
            this._settings.disconnect(this._maxWidthSettingsId);
        this._restoreAppMenuDisplayBothSetting();
        this._cancelStartupRefresh();
    }
}
