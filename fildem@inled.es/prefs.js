import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Gtk from 'gi://Gtk';
import Adw from 'gi://Adw';
// Path exacto documentado para el proceso de preferencias en GNOME 45-48
import { ExtensionPreferences, gettext as _ } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const FildemBusName = 'es.inled.fildem';
const FildemObjectPath = '/es/inled/fildem';
const FildemInterface = 'es.inled.fildem';

export default class FildemPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage();
        window.add(page);

        const group = new Adw.PreferencesGroup({
            title: _('Settings'),
        });
        page.add(group);

        // min-padding
        const paddingRow = new Adw.ActionRow({
            title: _('Button paddings'),
            subtitle: _('Tweak this if the menu and items desynchronize'),
        });
        const paddingSpin = new Gtk.SpinButton({
            adjustment: new Gtk.Adjustment({
                lower: 0,
                upper: 50,
                step_increment: 1,
            }),
            valign: Gtk.Align.CENTER,
        });
        settings.bind('min-padding', paddingSpin, 'value', Gio.SettingsBindFlags.DEFAULT);
        paddingRow.add_suffix(paddingSpin);
        group.add(paddingRow);

        // hover-switch-delay
        const hoverDelayRow = new Adw.ActionRow({
            title: _('Hover switch delay'),
            subtitle: _('Milliseconds to wait before switching to another already-open menu'),
        });
        const hoverDelaySpin = new Gtk.SpinButton({
            adjustment: new Gtk.Adjustment({
                lower: 0,
                upper: 3000,
                step_increment: 50,
                page_increment: 250,
            }),
            valign: Gtk.Align.CENTER,
        });
        settings.bind('hover-switch-delay', hoverDelaySpin, 'value', Gio.SettingsBindFlags.DEFAULT);
        hoverDelayRow.add_suffix(hoverDelaySpin);
        group.add(hoverDelayRow);

        // max-menu-width-percent
        const maxWidthRow = new Adw.ActionRow({
            title: _('Max menu width'),
            subtitle: _('Maximum menu width as a percentage of the active monitor width'),
        });
        const maxWidthSpin = new Gtk.SpinButton({
            adjustment: new Gtk.Adjustment({
                lower: 10,
                upper: 80,
                step_increment: 1,
                page_increment: 5,
            }),
            valign: Gtk.Align.CENTER,
        });
        settings.bind('max-menu-width-percent', maxWidthSpin, 'value', Gio.SettingsBindFlags.DEFAULT);
        maxWidthRow.add_suffix(maxWidthSpin);
        group.add(maxWidthRow);

        // show-only-when-hover
        const hoverRow = new Adw.SwitchRow({
            title: _('Show menu only when hover'),
            subtitle: _('Show menu only when the mouse is over the panel'),
        });
        settings.bind('show-only-when-hover', hoverRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(hoverRow);

        // hide-app-menu
        const hideAppRow = new Adw.SwitchRow({
            title: _('Hide app menu'),
            subtitle: _('Hide the app label when showing the menu'),
        });
        settings.bind('hide-app-menu', hideAppRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(hideAppRow);

        // refresh menu cache
        const refreshCacheRow = new Adw.ActionRow({
            title: _('Refresh menu cache'),
            subtitle: _('Clear cached menus so the active application rebuilds its menu'),
        });
        const refreshCacheButton = new Gtk.Button({
            label: _('Refresh'),
            valign: Gtk.Align.CENTER,
        });
        refreshCacheButton.connect('clicked', () => {
            refreshCacheButton.sensitive = false;
            refreshCacheButton.label = _('Refreshing…');

            Gio.DBusProxy.new_for_bus(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                null,
                FildemBusName,
                FildemObjectPath,
                FildemInterface,
                null,
                (_source, proxyResult) => {
                    try {
                        const proxy = Gio.DBusProxy.new_for_bus_finish(proxyResult);
                        proxy.call(
                            'ClearMenuCache',
                            null,
                            Gio.DBusCallFlags.NONE,
                            -1,
                            null,
                            (_proxy, callResult) => {
                                try {
                                    proxy.call_finish(callResult);
                                    refreshCacheButton.label = _('Refreshed');
                                } catch (error) {
                                    console.error(`Fildem failed to refresh menu cache: ${error.message}`);
                                    refreshCacheButton.label = _('Failed');
                                } finally {
                                    refreshCacheButton.sensitive = true;
                                }
                            }
                        );
                    } catch (error) {
                        console.error(`Fildem failed to connect to helper service: ${error.message}`);
                        refreshCacheButton.label = _('Failed');
                        refreshCacheButton.sensitive = true;
                    }
                }
            );
        });
        refreshCacheRow.add_suffix(refreshCacheButton);
        refreshCacheRow.activatable_widget = refreshCacheButton;
        group.add(refreshCacheRow);
    }
}
