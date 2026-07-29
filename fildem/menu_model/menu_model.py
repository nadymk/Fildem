#!/usr/bin/python3

import dbus
import time
import re

from gi.repository import GLib

from ..treelib import Tree

from fildem.menu_model.menu_item import DbusGtkMenuItem, DbusAppMenuItem, clean_label


CALL_TIMEOUT_MS = 300
DISCOVERY_NEGATIVE_TTL_S = 3.0
_MENU_ROOTS = ("/MenuBar", "/com/canonical/menu")
_NODE_NAME_RE = re.compile(r'<node name="([^"]+)"')
_QT_HINT_STOP_WORDS = {
	'app', 'apps', 'bin', 'client', 'com', 'desktop', 'flatpak', 'gnome',
	'gtk', 'kde', 'linux', 'org', 'qt', 'run', 'service', 'ubuntu',
	'wayland', 'window', 'x11',
}


def _json_safe(value):
	if isinstance(value, (str, int, float, bool)) or value is None:
		return value
	if isinstance(value, (bytes, bytearray)):
		return list(value)
	if isinstance(value, (list, tuple)):
		return [_json_safe(item) for item in value]
	if isinstance(value, dict):
		return {str(key): _json_safe(item) for key, item in value.items()}
	return str(value)


def _flatpak_scope(pid):
	try:
		with open(f"/proc/{pid}/cgroup") as f:
			cgroup = f.read()
	except OSError:
		return None

	for line in cgroup.splitlines():
		unit = line.rpartition("/")[2]
		if unit.startswith("app-flatpak-"):
			return unit
	return None


class DbusGtkMenu(object):

	def __init__(self, session, window):
		self.results      = {}
		self.actions      = {}
		self.accels       = {}
		self.descriptions = {}
		self.tree         = Tree()
		self._update_timer = 0
		self.refresh_callback = None
		self.toggle_overrides = {}
		self.session      = session
		self.bus_name     = window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME')
		# with app. prefix
		self.app_path     = window.get_utf8_prop('_GTK_APPLICATION_OBJECT_PATH')
		# with win. prefix
		self.win_path     = window.get_utf8_prop('_GTK_WINDOW_OBJECT_PATH')
		# with unity. prefix
		self.menubar_path = window.get_utf8_prop('_GTK_MENUBAR_OBJECT_PATH')
		self.appmenu_path = window.get_utf8_prop('_GTK_APP_MENU_OBJECT_PATH')
		if not self.menubar_path and self.app_path:
			self.menubar_path = self.app_path + '/menus/menubar/0'
		# GTK apps, especially LibreOffice, can expose hundreds of actions.
		# Calling org.gtk.Actions.Describe once per item makes initial menu
		# generation crawl, so defer that metadata on this path for now.
		self.describe_on_build = False

		self.top_level_menus = []
		self.signal_matcher = []
		self.source_name  = 'gtk'

	def activate(self, selection):
		action = self.actions.get(selection, '')
		target = None
		if isinstance(action, tuple):
			action, target = action
		print('Fildem activate:', repr(selection), '->', repr(action), repr(target), flush=True)
		item = self._find_item(selection)
		if item is not None and item.data is not None:
			if item.data.toggle_type == 'radio':
				self._set_radio_selection(item.data)
			elif item.data.toggle_type == 'checkmark':
				self._toggle_checkmark(item.data)
		activated = self._activate(action, target)
		if activated:
			self.add_timer()
			GLib.timeout_add(300, self._schedule_refresh)
		return activated

	def _find_item(self, selection):
		for node in self.tree.all_nodes():
			data = node.data
			if data is None:
				continue
			if data.text == selection:
				return node
		return None

	def _set_radio_selection(self, selected_item):
		parent_path = tuple(selected_item.path)
		for node in self.tree.all_nodes():
			if node.data is None:
				continue
			if node.data.toggle_type != 'radio':
				continue
			if tuple(node.data.path) != parent_path:
				continue
			is_selected = node.data.text == selected_item.text
			node.data.toggle_state = is_selected
			self.toggle_overrides[node.data.action] = is_selected

	def _toggle_checkmark(self, selected_item):
		selected_item.toggle_state = not bool(selected_item.toggle_state)
		self.toggle_overrides[selected_item.action] = bool(selected_item.toggle_state)

	def _activate(self, action, target=None):
		if 'app.' in action:
			return self.send_action(action, 'app.', self.app_path, target)
		elif 'win.' in action:
			return self.send_action(action, 'win.', self.win_path, target)
		elif 'unity.' in action:
			return self.send_action(action, 'unity.', self.menubar_path, target)
		return False

	def _dbus_target(self, target):
		if target in (None, ''):
			return []
		if isinstance(target, dbus.Boolean):
			return [target]
		if isinstance(target, bool):
			return [dbus.Boolean(target)]
		if isinstance(target, (int, float)):
			return [dbus.Int32(int(target))]
		return [dbus.String(str(target))]

	def send_action(self, name, prefix, path, target=None):
		try:
			obj       = self.session.get_object(self.bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
			print('Fildem sending action:', self.bus_name, path, name, flush=True)
			interface.Activate(name.replace(prefix, ''), self._dbus_target(target), dict())
			return True
		except Exception as e:
			print('Fildem action failed:', repr(e), flush=True)
			return False

	def get_results(self):
		paths = [self.appmenu_path, self.menubar_path]

		for path in filter(None, paths):
			obj       = self.session.get_object(self.bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Menus')
			try:
				results   = interface.Start([x for x in range(1024)])
				interface.End([x for x in range(1024)])
			except Exception:
				continue

			s = interface.connect_to_signal('Changed', self.on_actions_changed)
			self.signal_matcher.append(s)
			self.connect_to_actions_iface(obj)

			for menu in results:
				self.results[(menu[0], menu[1])] = menu[2]

		self._load_descriptions()
		self.tree.create_node('Root', 'Root')
		self.collect_entries(treelib_parent='Root')
		if not len(self.tree.children(self.tree[self.tree.root].identifier)):
			self.tree = Tree()

	def _load_descriptions(self):
		self.descriptions = {}
		for prefix, path in (
			('app.', self.app_path),
			('win.', self.win_path),
			('unity.', self.menubar_path),
		):
			if not path:
				continue
			try:
				obj = self.session.get_object(self.bus_name, path)
				interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
				descriptions = interface.DescribeAll()
			except Exception:
				continue
			for action_name, description in descriptions.items():
				self.descriptions[prefix + str(action_name)] = description

	def collect_entries(self, menu=(0, 0), labels=[], treelib_parent=None, section_group=0):
		section = (menu[0], menu[1])
		for menu in self.results.get(section, []):
			if 'label' in menu:
				label = clean_label(menu.get('label', ''))
				if not label and not menu.get('action') and ':submenu' not in menu:
					continue
				if len(labels) == 0:
					self.top_level_menus.append(label)

				menu_item = DbusGtkMenuItem(menu, labels)
				menu_item.section = (tuple(labels), section_group)
				description = self.descriptions.get(menu_item.action)
				if description is not None:
					menu_item.enabled = bool(description[0])
					menu_item.set_toggle(description[2])
				elif self.describe_on_build:
					description = self.describe(menu_item.action)
					if description is not None:
						menu_item.enabled = description[0]
						menu_item.set_toggle(description[1])

				if menu_item.action in self.toggle_overrides:
					menu_item.toggle_state = bool(self.toggle_overrides[menu_item.action])

				menu_path = labels + [menu_item.label]
				# Some GTK menu entries (notably LibreOffice on newer GTK/appmenu
				# stacks) have no action name. treelib requires every node ID to be
				# non-empty and unique, so use a local structural ID for those nodes.
				node_id = menu_item.action or ('menu-' + str(section[0]) + '-' + str(section[1]) + '-' + str(len(self.tree.all_nodes())))
				if node_id in self.tree:
					node_id += '-' + str(len(self.tree.all_nodes()))
				self.tree.create_node(menu_item.label, node_id, treelib_parent, data=menu_item)

				if ':submenu' in menu:
					self.collect_entries(menu[':submenu'], menu_path, node_id)
				elif 'action' in menu:
					self.actions[menu_item.text] = (menu_item.action, menu_item.target)

			elif ':section' in menu:
				section_group += 1
				self.collect_entries(menu[':section'], labels, treelib_parent, section_group)

	def describe(self, action):
		"""
		Describe return this:
		dbus.Struct((
		 dbus.Boolean(True), # enabled
		 dbus.Signature(''),
		 dbus.Array([ # This is empty in a not checked item
		  dbus.Boolean(True, variant_level=1)], # Checked or not
		  signature=dbus.Signature('v'))),
		 signature=None)
		"""
		if action.startswith('unity'):
			path = self.menubar_path
		elif action.startswith('win'):
			path = self.win_path
		elif action.startswith('app'):
			path = self.app_path
		else:
			return None

		dot = action.find('.')
		action = action[dot+1:]
		obj = self.session.get_object(self.bus_name, path)
		interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')

		try:
			description = interface.Describe(action)
		except Exception as e:
			# import traceback; traceback.print_exc()
			return None
		enabled = description[0]
		checked = description[2]
		return enabled, checked

	def connect_to_actions_iface(self, obj):
		try:
			iface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
			s = iface.connect_to_signal('Changed', self.on_gtk_actions_changed)
			self.signal_matcher.append(s)
		except Exception as e:
			pass

	def on_actions_changed(self, *args):
		print(f'on_actions_changed {args=}')

	def on_gtk_actions_changed(self, removed, enabled_changed, state_changed, new_actions):
		"""
		The name of the actions doesn't have the unity. app. or win. preprended
		"""
		# print(f'{enabled_changed=} {removed=} {state_changed=} {new_actions=}')
		prefixes = ['unity.', 'win.', 'app.']
		needs_refresh = False
		for action_name in [*enabled_changed, *state_changed]:
			items = map(lambda prefix: self.tree.get_node(prefix + action_name), prefixes)
			items = filter(None, items)
			item = next(items, None)
			if item is None:
				print('Item does not exists:', action_name)
				continue

			if action_name in enabled_changed:
				item.data.enabled = enabled_changed[action_name]
				needs_refresh = True
			else:
				if item.data.toggle_type == 'radio':
					parent_path = tuple(item.data.path)
					for node in self.tree.all_nodes():
						if node.identifier == item.identifier or node.data is None:
							continue
						if node.data.toggle_type == 'radio' and tuple(node.data.path) == parent_path:
							node.data.toggle_state = False
							self.toggle_overrides[node.data.action] = False
				item.data.toggle_state = bool(state_changed[action_name])
				self.toggle_overrides[item.data.action] = bool(state_changed[action_name])
				needs_refresh = True
				# item.data.enabled = state_changed[action_name]
				# item.data.set_description(self.describe(item.data.action))
		if needs_refresh:
			self.add_timer()

	def remove_actions_listener(self):
		for s in self.signal_matcher:
			s.remove()
		self.signal_matcher = []
		if self._update_timer != 0:
			GLib.source_remove(self._update_timer)
			self._update_timer = 0

	def add_timer(self):
		if self._update_timer == 0:
			self._update_timer = GLib.timeout_add(50, self._update)

	def _update(self):
		self.results = {}
		self.actions = {}
		self.accels = {}
		self.top_level_menus = []
		self.tree = Tree()
		self.remove_actions_listener()
		self.get_results()
		self._update_timer = 0
		if self.refresh_callback is not None:
			try:
				self.refresh_callback()
			except Exception as error:
				print('Fildem menu refresh callback failed:', repr(error), flush=True)
		return False

	def _schedule_refresh(self):
		self.add_timer()
		return False


class DbusMozillaGtkMenu(DbusGtkMenu):
	"""
	Firefox-derived browsers with widget.gtk.global-menu.* enabled on Wayland
	can export a GtkApplication-style menu without setting the X11 _GTK_* window
	properties that normal GTK apps expose.  In Flatpak Floorp, the interesting
	objects appear below:

	    /org/appmenu/gtk/window/menus/menubar/<id>

	on an org.mozilla.<app>.<profile> bus name.

	This class only accepts a discovered object when org.gtk.Menus returns a
	non-empty model.  Empty placeholder exports are ignored so the synthetic
	browser fallback cannot masquerade as a real menu.
	"""

	def __init__(self, session, window):
		super().__init__(session, window)
		self.source_name = 'mozilla'
		self.window = window
		if self.bus_name and self.menubar_path:
			return
		self.bus_name = None
		self.app_path = None
		self.win_path = None
		self.menubar_path = None
		self.appmenu_path = None
		self.describe_on_build = True
		self._resolve_exported_menu()

	def _candidate_bus_names(self):
		app_id = str(self.window.get_utf8_prop('appId') or '').lower()
		app_name = str(self.window.get_app_name() or '').lower()
		wm_class = str(self.window.get_utf8_prop('wmClass') or '').lower()
		needles = [value for value in [app_id, app_name, wm_class] if value]
		if any('floorp' in value for value in needles):
			needles = ['floorp']
		elif any(name in ' '.join(needles) for name in ['firefox', 'librewolf', 'waterfox', 'zen']):
			needles.extend(['mozilla', 'firefox', 'librewolf', 'waterfox', 'zen'])
		else:
			return []

		try:
			names = self.session.list_names()
		except Exception:
			return []

		candidates = []
		for name in map(str, names):
			lower = name.lower()
			if name.startswith('org.mozilla.') and any(needle in lower for needle in needles):
				candidates.append(name)
		return candidates

	def _child_nodes(self, bus_name, path):
		try:
			obj = self.session.get_object(bus_name, path)
			xml = str(obj.Introspect(dbus_interface='org.freedesktop.DBus.Introspectable'))
		except Exception:
			return []
		return re.findall(r'<node name="([^"]+)"', xml)

	def _has_non_empty_menu(self, bus_name, path):
		try:
			obj = self.session.get_object(bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Menus')
			results = interface.Start([x for x in range(1024)])
			interface.End([x for x in range(1024)])
		except Exception as e:
			print('Fildem Mozilla GtkApplication probe failed:', bus_name, path, repr(e), flush=True)
			return False
		has_items = any(len(menu[2]) for menu in results)
		if not has_items:
			print('Fildem Mozilla GtkApplication export is empty:', bus_name, path, 'menus:', len(results), flush=True)
		return has_items

	def _resolve_exported_menu(self):
		for bus_name in self._candidate_bus_names():
			base_path = '/org/appmenu/gtk/window/menus/menubar'
			for child in self._child_nodes(bus_name, base_path):
				path = base_path + '/' + child
				if self._has_non_empty_menu(bus_name, path):
					self.bus_name = bus_name
					self.menubar_path = path
					print('Fildem using Mozilla GtkApplication menubar:', bus_name, path, flush=True)
					return
			# Some builds use a single fixed object path rather than child IDs.
			for path in [
				'/org/gtk/Application/menus/menubar',
				'/org/gtk/Application/menus/menubar/0',
				'/org/appmenu/gtk/window/menus/menubar/0',
			]:
				if self._has_non_empty_menu(bus_name, path):
					self.bus_name = bus_name
					self.menubar_path = path
					print('Fildem using Mozilla GtkApplication menubar:', bus_name, path, flush=True)
					return


class DbusLomiriMenu(DbusGtkMenu):
	def __init__(self, session, window):
		self.results      = {}
		self.actions      = {}
		self.accels       = {}
		self.tree         = Tree()
		self._update_timer = 0
		self.session      = session
		self.window       = window
		self.source_name  = 'lomiri'
		self.bus_name     = None
		self.app_path     = None
		self.win_path     = None
		self.menubar_path = None
		self.appmenu_path = None
		self.action_path  = None
		self.top_level_menus = []
		self.signal_matcher = []
		self.describe_on_build = True
		self.refresh_callback = None

	def _resolve_registered_menu(self):
		try:
			obj = self.session.get_object(
				'com.lomiri.MenuRegistrar',
				'/com/lomiri/MenuRegistrar',
				introspect=False,
			)
			interface = dbus.Interface(obj, 'com.lomiri.MenuRegistrar')
			menus = interface.GetAppMenus(timeout=CALL_TIMEOUT_MS / 1000.0)
			pid = self.window.get_pid()
			entry = menus.get(pid) if pid else None
			if entry is None and not pid and len(menus) == 1:
				entry = list(menus.values())[0]
			if entry is None:
				return
			self.bus_name = str(entry[0])
			self.appmenu_path = str(entry[1])
			self.action_path = str(entry[2])
		except Exception as e:
			return

	def activate(self, selection):
		action = self.actions.get(selection, '')
		print('Fildem lomiri activate:', repr(selection), '->', repr(action), flush=True)
		if not action or not self.action_path:
			return False
		return self.send_action(action, 'unity.', self.action_path)

	def send_action(self, name, prefix, path, target=None):
		try:
			obj       = self.session.get_object(self.bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
			print('Fildem sending lomiri action:', self.bus_name, path, name, flush=True)
			params = [] if target in (None, '') else [dbus.String(str(target))]
			interface.Activate(name.replace(prefix, ''), params, dict())
			return True
		except Exception as e:
			print('Fildem lomiri action failed:', repr(e), flush=True)
			return False

	def get_results(self):
		if not self.bus_name or not self.appmenu_path:
			self._resolve_registered_menu()
		if not self.bus_name or not self.appmenu_path:
			return
		super().get_results()

	def describe(self, action):
		if not action or not self.action_path:
			return None
		if action.startswith('unity.'):
			action = action.replace('unity.', '', 1)
		obj = self.session.get_object(self.bus_name, self.action_path)
		interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
		try:
			description = interface.Describe(action)
		except Exception:
			return None
		return description[0], description[2]


class DbusAppMenu(object):

	def __init__(self, session, window):
		self.actions   = {}
		self.accels    = {}
		self.tree      = Tree()
		self.session   = session
		self.window    = window
		self.source_name = 'appmenu'
		self._update_timer = 0
		self.signal_matcher = []
		self._discovery_tried = {}
		# Qt/appmenu discovery can be expensive on GTK-heavy desktops. Keep it
		# lazy so GTK windows can publish immediately and only probe this path
		# when the other menu backends do not have anything useful.
		self.interface = None
		self.top_level_menus = []
		self.results = None
		self.refresh_callback = None

	def activate(self, selection):
		action = self.actions[selection]
		try:
			self._event(action, 'clicked')
			return True
		except Exception as e:
			print('Fildem dbusmenu activate failed, retrying:', repr(e), flush=True)
			return self.retry_activate(selection)

	def retry_activate(self, selection):
		# Electron apps change a lot their menus, we have to update to retry
		self.actions = {}
		self.accels = {}
		self.tree = Tree()
		results = self.interface.GetLayout(0, -1, dbus.Array(signature="s"))
		self.collect_entries(results[1], [])
		action = self.actions[selection]
		try:
			self._event(action, 'clicked')
			return True
		except Exception as e:
			print('Fildem dbusmenu retry failed:', repr(e), flush=True)
			return False

	def _event(self, action, event='clicked'):
		try:
			return self.interface.Event(
				dbus.Int32(int(action)),
				dbus.String(event),
				dbus.String(''),
				dbus.UInt32(int(time.time())),
			)
		except TypeError:
			# Some dbus-python builds are picky about the variant slot; retry with
			# a plain Python string so the proxy can coerce it into the signature.
			return self.interface.Event(
				dbus.Int32(int(action)),
				dbus.String(event),
				'',
				dbus.UInt32(int(time.time())),
			)

	def _discovery_key(self):
		pid = int(self.window.get_pid() or 0)
		if pid <= 0:
			return None
		return _flatpak_scope(pid) or f"pid:{pid}"

	def _candidate_name_hints(self):
		parts = (
			str(self.window.get_app_name() or '').lower(),
			str(self.window.get_utf8_prop('wmClass') or '').lower(),
			str(self.window.get_utf8_prop('appId') or '').lower(),
		)
		hints = []
		for part in parts:
			for token in re.split(r'[^a-z0-9]+', part):
				if len(token) < 4:
					continue
				if token in _QT_HINT_STOP_WORDS:
					continue
				if token not in hints:
					hints.append(token)
		return hints

	def get_interface(self):
		bus_name = 'com.canonical.AppMenu.Registrar'
		bus_path = '/com/canonical/AppMenu/Registrar'

		direct_name = self.window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME')
		direct_path = self.window.get_utf8_prop('_GTK_MENUBAR_OBJECT_PATH')
		if direct_name and direct_path:
			try:
				obj = self.session.get_object(direct_name, direct_path, introspect=False)
				interface = dbus.Interface(obj, 'com.canonical.dbusmenu')
				interface.GetLayout(0, 0, dbus.Array(signature="s"))

				s = interface.connect_to_signal('ItemsPropertiesUpdated', self.on_actions_changed)
				self.signal_matcher.append(s)
				s = interface.connect_to_signal('LayoutUpdated', self.layout_updated)
				self.signal_matcher.append(s)

				print('Fildem using direct DBusMenu:', direct_name, direct_path, flush=True)
				return interface
			except Exception as e:
				print('Fildem direct DBusMenu unavailable:', direct_name, direct_path, repr(e), flush=True)

		try:
			obj        = self.session.get_object(bus_name, bus_path, introspect=False)
			interface  = dbus.Interface(obj, bus_name)
			xid = self.window.get_xid()
			if xid:
				try:
					menu = interface.GetMenuForWindow(xid, timeout=CALL_TIMEOUT_MS / 1000.0)
				except Exception:
					menu = None
				if not menu or not menu[0] or not menu[1]:
					menus = interface.GetMenus(timeout=CALL_TIMEOUT_MS / 1000.0)
					name, path = self._find_menu_for_wayland_window(menus)
				else:
					name, path = menu
			else:
				menus = interface.GetMenus(timeout=CALL_TIMEOUT_MS / 1000.0)
				name, path = self._find_menu_for_wayland_window(menus)
			if not name or not path:
				return self._discover_qt_menu()
			obj        = self.session.get_object(name, path, introspect=False)
			interface  = dbus.Interface(obj, 'com.canonical.dbusmenu')

			s = interface.connect_to_signal('ItemsPropertiesUpdated', self.on_actions_changed)
			self.signal_matcher.append(s)
			s = interface.connect_to_signal('LayoutUpdated', self.layout_updated)
			self.signal_matcher.append(s)

			return interface
		except dbus.exceptions.DBusException:
			# import traceback; traceback.print_exc()
			return self._discover_qt_menu()

	def _sender_pid(self, sender):
		try:
			bus_obj = self.session.get_object(
				'org.freedesktop.DBus',
				'/org/freedesktop/DBus'
			)
			bus_iface = dbus.Interface(bus_obj, 'org.freedesktop.DBus')
			return int(bus_iface.GetConnectionUnixProcessID(sender, timeout=CALL_TIMEOUT_MS / 1000.0))
		except Exception:
			return 0

	def _pid_matches_window(self, pid):
		window_pid = int(self.window.get_pid() or 0)
		if pid <= 0 or window_pid <= 0:
			return False
		if pid == window_pid:
			return True
		scope = _flatpak_scope(window_pid)
		return bool(scope) and _flatpak_scope(pid) == scope

	def _introspect(self, sender, path):
		try:
			obj = self.session.get_object(sender, path, introspect=False)
			return obj.Introspect(
				dbus_interface='org.freedesktop.DBus.Introspectable',
				timeout=CALL_TIMEOUT_MS / 1000.0,
			)
		except Exception:
			return None

	def _menubar_paths(self, sender):
		paths = []
		for root in _MENU_ROOTS:
			xml = self._introspect(sender, root)
			if not xml:
				continue
			children = _NODE_NAME_RE.findall(str(xml))

			def sort_key(name):
				return (0, int(name)) if name.isdigit() else (1, name)

			for name in sorted(children, key=sort_key, reverse=True):
				paths.append(f"{root}/{name}")
		return paths

	def _list_unique_names(self):
		try:
			return [name for name in self.session.list_names()]
		except Exception:
			return []

	def _discover_qt_menu(self):
		key = self._discovery_key()
		if key is None:
			return None

		tried_at = self._discovery_tried.get(key)
		if tried_at is not None and (time.monotonic() - tried_at) < DISCOVERY_NEGATIVE_TTL_S:
			return None

		self._discovery_tried[key] = time.monotonic()
		hints = self._candidate_name_hints()
		candidates = self._list_unique_names()
		pid_matches = []
		hint_matches = []
		for sender in candidates:
			pid = self._sender_pid(sender)
			sender_name = str(sender).lower()
			pid_match = self._pid_matches_window(pid)
			hint_match = bool(hints) and any(hint in sender_name for hint in hints)
			if pid_match:
				pid_matches.append((sender, pid))
			elif hint_match:
				hint_matches.append((sender, pid))

		for sender, pid in [*pid_matches, *hint_matches]:
			for path in self._menubar_paths(sender):
				try:
					obj = self.session.get_object(sender, path)
					interface = dbus.Interface(obj, 'com.canonical.dbusmenu')
					results = interface.GetLayout(
						0,
						1,
						dbus.Array(signature="s"),
						timeout=CALL_TIMEOUT_MS / 1000.0,
					)
				except Exception:
					continue

				children = results[1][2]
				labeled = [
					child for child in children
					if child[1].get('label', '') or child[1].get('type', '') == 'separator'
				]
				if not labeled:
					continue

				s = interface.connect_to_signal('ItemsPropertiesUpdated', self.on_actions_changed)
				self.signal_matcher.append(s)
				s = interface.connect_to_signal('LayoutUpdated', self.layout_updated)
				self.signal_matcher.append(s)
				self._discovery_tried.pop(key, None)
				reason = 'pid' if self._pid_matches_window(pid) else 'hint'
				print('Fildem discovered unregistered dbusmenu:', sender, path, 'pid', pid, 'reason', reason, flush=True)
				return interface

		return None

	def _find_menu_for_wayland_window(self, menus):
		pid = int(self.window.get_pid() or 0)
		app_id = str(self.window.get_utf8_prop('appId') or '').lower()
		app_name = str(self.window.get_app_name() or '').lower()
		wm_class = str(self.window.get_utf8_prop('wmClass') or '').lower()
		haystack = ' '.join([app_id, app_name, wm_class])

		print('Fildem canonical menus available:', {
			int(xid): [str(entry[0]), str(entry[1]), self._sender_pid(str(entry[0]))]
			for xid, entry in menus.items()
		}, 'window pid:', pid, 'app:', haystack, flush=True)

		if len(menus) == 1:
			return list(menus.values())[0]

		if pid:
			for entry in menus.values():
				sender = str(entry[0])
				if self._sender_pid(sender) == pid:
					print('Fildem canonical menu matched by pid:', pid, sender, entry[1], flush=True)
					return entry

		if any(browser in haystack for browser in ['floorp', 'firefox', 'librewolf', 'waterfox', 'zen']):
			for entry in menus.values():
				sender = str(entry[0]).lower()
				if 'mozilla' in sender or 'floorp' in sender or 'firefox' in sender:
					print('Fildem canonical browser menu matched by sender:', entry[0], entry[1], flush=True)
					return entry

		return [None, None]

	def get_results(self):
		if self.interface is None:
			self.interface = self.get_interface()
		if self.interface:
			self.results = self.interface.GetLayout(0, -1, dbus.Array(signature="s"))
			print('Fildem dbusmenu root groups:', len(self.results[1][2]), flush=True)
			self.collect_entries(self.results[1])
			print('Fildem dbusmenu tree built:', len(self.tree), 'top:', len(self.top_level_menus), flush=True)

			if not len(self.tree.children(self.tree[self.tree.root].identifier)):
				self.tree = Tree()

	def collect_entries(self, item=None, labels=None, treelib_parent=None):
		if self.results is None:
			return
		if item is None:
			item = self.results[1]
		if labels is None:
			labels = []
		menu_item = DbusAppMenuItem(item, labels)
		menu_path = labels

		if 'children-display' in item[1]:
			item_id = item[0]
			try:
				self.interface.AboutToShow(item_id)
			except Exception:
				pass
			self.interface.Event(item_id, 'opened', 'not used', dbus.UInt32(time.time()))
			item = self.interface.GetLayout(item_id, -1, dbus.Array(signature="s"))[1]

		if bool(menu_item.label) and menu_item.label != 'Root' and menu_item.label != 'DBusMenuRoot':
			menu_path = labels + [menu_item.label]

		self.tree.create_node(menu_item.label, menu_item.action, treelib_parent, data=menu_item)
		if len(item[2]):
			if not self.top_level_menus:
				self.top_level_menus = list(map(lambda c: clean_label(c[1].get('label', '')), item[2]))

			for child in item[2]:
				self.collect_entries(child, menu_path, menu_item.action)

		elif bool(menu_item.label) or menu_item.separator:
			self.actions[menu_item.text] = menu_item.action

	def on_actions_changed(self, updated, removed):
		for upd in updated:
			item = self.tree.get_node(int(upd[0]))
			if item is not None:
				item.data.update_props(upd[1])
				if 'children-display' in upd[1]:
					# Just update everything
					self.add_timer()
					break

		# TODO removed

	def layout_updated(self, revision, parent):
		self.add_timer()

	def add_timer(self):
		if self._update_timer == 0:
			self._update_timer = GLib.timeout_add(50, self._update)

	def _update(self):
		self.actions = {}
		self.accels = {}
		self.tree = Tree()
		self.get_results()
		self._update_timer = 0
		if self.refresh_callback is not None:
			try:
				self.refresh_callback()
			except Exception as error:
				print('Fildem menu refresh callback failed:', repr(error), flush=True)
		return False

	def remove_actions_listener(self):
		for s in self.signal_matcher:
			s.remove()
		self.signal_matcher = []
		if self._update_timer != 0:
			GLib.source_remove(self._update_timer)
			self._update_timer = 0


class MenuModel:
	# The menubars have to be reused so they are cleanup
	def __init__(self, session, window):
		self.appmenu = None
		self.gtkmenu = None
		self.mozillamenu = None
		self.lomirimenu = None
		self.active_source = None
		self._session = session
		self.window = window
		self._init_window(session, window)

	def _looks_like_gtk_window(self):
		return any([
			self.window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME'),
			self.window.get_utf8_prop('_GTK_APPLICATION_OBJECT_PATH'),
			self.window.get_utf8_prop('_GTK_WINDOW_OBJECT_PATH'),
			self.window.get_utf8_prop('_GTK_MENUBAR_OBJECT_PATH'),
			self.window.get_utf8_prop('_GTK_APP_MENU_OBJECT_PATH'),
		])

	def _init_window(self, session, window):
		self.appmenu = DbusAppMenu(session, window)
		self.gtkmenu = DbusGtkMenu(session, window)
		self.mozillamenu = DbusMozillaGtkMenu(session, window)
		self.lomirimenu = DbusLomiriMenu(session, window)
		self.active_source = None

	def _sources(self):
		return (self.gtkmenu, self.mozillamenu, self.lomirimenu, self.appmenu)

	def _source_has_menu(self, source):
		tree = getattr(source, 'tree', None)
		if tree is None or tree.root is None:
			return False
		try:
			return len(tree.children(tree.root)) > 0
		except Exception:
			return False

	def _select_active_source(self):
		# Keep one active backend per window so the renderer and activator never
		# mix trees from different sources.
		for source in self._sources():
			if self._source_has_menu(source):
				return source
		return None

	@property
	def source(self):
		if self.active_source is None:
			self.active_source = self._select_active_source()
		return self.active_source

	@property
	def source_name(self):
		source = self.source
		return getattr(source, 'source_name', '') if source is not None else ''

	def set_refresh_callback(self, callback):
		self.appmenu.refresh_callback = callback
		self.gtkmenu.refresh_callback = callback
		self.mozillamenu.refresh_callback = callback
		self.lomirimenu.refresh_callback = callback

	def _update_menus(self):
		try:
			self.gtkmenu.get_results()
		except Exception as error:
			print('Fildem gtk menu build failed:', repr(error), flush=True)
		print('Fildem gtk menu state:', len(self.gtkmenu.tree), 'actions:', len(self.gtkmenu.actions), flush=True)
		if not len(self.gtkmenu.tree):
			try:
				self.mozillamenu.get_results()
			except Exception as error:
				print('Fildem mozilla menu build failed:', repr(error), flush=True)
		print('Fildem mozilla menu state:', len(self.mozillamenu.tree), 'actions:', len(self.mozillamenu.actions), flush=True)
		if not len(self.gtkmenu.tree):
			try:
				self.lomirimenu.get_results()
			except Exception as error:
				print('Fildem lomiri menu build failed:', repr(error), flush=True)
		print('Fildem lomiri menu state:', len(self.lomirimenu.tree), 'actions:', len(self.lomirimenu.actions), flush=True)
		if (not len(self.gtkmenu.tree) and not len(self.mozillamenu.tree) and
				not len(self.lomirimenu.tree) and not self._looks_like_gtk_window()):
			try:
				self.appmenu.get_results()
			except Exception as error:
				print('Fildem app menu build failed:', repr(error), flush=True)
		print('Fildem app menu state:', len(self.appmenu.tree), 'actions:', len(self.appmenu.actions), 'iface:', bool(self.appmenu.interface), flush=True)
		self.active_source = self._select_active_source()
		print('Fildem active menu source:', self.source_name or 'none', flush=True)

	@property
	def prompt(self):
		return self.window.get_app_name()

	@property
	def actions(self):
		actions = self.action_map
		self.handle_empty(actions)

		return actions.keys()

	@property
	def action_map(self):
		source = self.source
		actions = source.actions if source is not None else {}
		return actions

	@property
	def accel(self):
		source = self.source
		accel = source.accels if source is not None else {}
		return accel

	@property
	def tree(self):
		source = self.source
		return source.tree if source is not None else Tree()

	@property
	def top_level_menus(self):
		source = self.source
		return source.top_level_menus if source is not None else []

	def activate(self, selection):
		source = self.source
		candidates = [source] if source is not None else []
		candidates.extend([menu for menu in self._sources() if menu is not source])
		for menu in candidates:
			if menu is None or selection not in menu.actions:
				continue
			result = menu.activate(selection)
			if result is False:
				if hasattr(menu, '_update'):
					menu._update()
				result = menu.activate(selection)
			return True if result is None else bool(result)
		return False

	def find_node(self, selection):
		tree = self.tree
		if tree.root is None:
			return None
		for node in tree.all_nodes():
			data = node.data
			if data is None:
				continue
			if node.identifier == selection or data.text == selection:
				return node
		return None

	def _serialize_node(self, tree, node):
		data = node.data
		children = [self._serialize_node(tree, child) for child in tree.children(node.identifier)]
		children = [child for child in children if child is not None]
		if data and not data.separator and not data.action and not children:
			return None
		if data is None:
			return None

		node_type = 'submenu' if children else 'item'
		if data.separator:
			node_type = 'separator'
		elif getattr(data, 'toggle_type', '') == 'radio':
			node_type = 'radio'
		elif getattr(data, 'toggle_type', '') in ('checkmark', 'checkbox'):
			node_type = 'checkbox'

		return {
			'id': str(node.identifier),
			'label': str(data.label if data else node.tag),
			'action': str(data.text if data else ''),
			'enabled': bool(data.enabled) if data else True,
			'toggle': bool(data.toggle_state) if data else False,
			'checked': bool(data.toggle_state) if data else False,
			'toggleType': str(getattr(data, 'toggle_type', '') or '') if data else '',
			'section': _json_safe(getattr(data, 'section', None)) if data else None,
			'shortcut': str(getattr(data, 'shortcut', '') or '') if data else '',
			'accel': str(getattr(data, 'accel', '') or '') if data else '',
			'iconName': str(getattr(data, 'icon_name', '') or '') if data else '',
			'iconData': _json_safe(getattr(data, 'icon_data', [])) if data else [],
			'separator': bool(data.separator) if data else False,
			'type': node_type,
			'children': children,
		}

	def serialize_tree(self):
		tree = self.tree
		root = tree[tree.root] if tree.root is not None else None
		if root is None:
			return []
		nodes = [self._serialize_node(tree, child) for child in tree.children(root.identifier)]
		return [item for item in nodes if item is not None]

	def serialize_children(self, selection):
		node = self.find_node(selection)
		if node is None:
			return []
		tree = self.tree
		nodes = [self._serialize_node(tree, child) for child in tree.children(node.identifier)]
		return [item for item in nodes if item is not None]

	def serialize_bar(self, generation=0):
		window_name = ''
		try:
			window_name = str(self.window.get_utf8_prop('appId') or self.prompt or '')
		except Exception:
			window_name = ''
		return {
			'source': self.source_name or '',
			'generation': int(generation),
			'app_id': str(window_name),
			'menus': self.serialize_tree(),
		}

	def handle_empty(self, actions):
		if not len(actions):
			alert = 'No menu items available!'
			promt = ''
			try:
				promt = self.prompt
			except Exception as e:
				pass
			print('Gnome HUD: WARNING: (%s) %s' % (promt, alert))

	def __del__(self):
		try:
			if self.appmenu is not None:
				self.appmenu.remove_actions_listener()
			if self.gtkmenu is not None:
				self.gtkmenu.remove_actions_listener()
			if self.mozillamenu is not None:
				self.mozillamenu.remove_actions_listener()
			if self.lomirimenu is not None:
				self.lomirimenu.remove_actions_listener()
		except Exception:
			pass

	def destroy(self):
		self.__del__()
