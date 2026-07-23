#!/usr/bin/python3

import dbus
import time
import re

from gi.repository import GLib

from ..treelib import Tree

from fildem.menu_model.menu_item import DbusGtkMenuItem, DbusAppMenuItem, clean_label


class DbusGtkMenu(object):

	def __init__(self, session, window):
		self.results      = {}
		self.actions      = {}
		self.accels       = {}
		self.tree         = Tree()
		self._update_timer = 0
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

	def activate(self, selection):
		action = self.actions.get(selection, '')
		print('Fildem activate:', repr(selection), '->', repr(action), flush=True)

		if 'app.' in action:
			self.send_action(action, 'app.', self.app_path)
		elif 'win.' in action:
			self.send_action(action, 'win.', self.win_path)
		elif 'unity.' in action:
			self.send_action(action, 'unity.', self.menubar_path)

	def send_action(self, name, prefix, path):
		try:
			obj       = self.session.get_object(self.bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
			print('Fildem sending action:', self.bus_name, path, name, flush=True)
			interface.Activate(name.replace(prefix, ''), [], dict())
		except Exception as e:
			print('Fildem action failed:', repr(e), flush=True)

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

		self.tree.create_node('Root', 'Root')
		self.collect_entries(treelib_parent='Root')
		if not len(self.tree.children(self.tree[self.tree.root].identifier)):
			self.tree = Tree()

	def collect_entries(self, menu=(0, 0), labels=[], treelib_parent=None):
		section = (menu[0], menu[1])
		for menu in self.results.get(section, []):
			if 'label' in menu:
				label = clean_label(menu.get('label', ''))
				if not label and not menu.get('action') and ':submenu' not in menu:
					continue
				if len(labels) == 0:
					self.top_level_menus.append(label)

				menu_item = DbusGtkMenuItem(menu, labels)
				menu_item.section = section
				if self.describe_on_build:
					description = self.describe(menu_item.action)
					if description is not None:
						menu_item.enabled = description[0]
						menu_item.set_toggle(description[1])

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
					self.actions[menu_item.text] = menu_item.action

			elif ':section' in menu:
				self.collect_entries(menu[':section'], labels, treelib_parent)

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
		for action_name in [*enabled_changed, *state_changed]:
			items = map(lambda prefix: self.tree.get_node(prefix + action_name), prefixes)
			items = filter(None, items)
			item = next(items, None)
			if item is None:
				print('Item does not exists:', action_name)
				continue

			if action_name in enabled_changed:
				item.data.enabled = enabled_changed[action_name]
			else:
				if item.data.toggle_type == 'radio': # 'checkmark':
					for s in self.tree.siblings(item.identifier):
						if s.data.section == item.data.section:
							s.data.toggle_state = False
				item.data.toggle_state = state_changed[action_name]
				# item.data.enabled = state_changed[action_name]
				# item.data.set_description(self.describe(item.data.action))

	def remove_actions_listener(self):
		for s in self.signal_matcher:
			s.remove()
		self.signal_matcher = []


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
		self.bus_name     = None
		self.app_path     = None
		self.win_path     = None
		self.menubar_path = None
		self.appmenu_path = None
		self.action_path  = None
		self.top_level_menus = []
		self.signal_matcher = []
		self.describe_on_build = True
		self._resolve_registered_menu()

	def _resolve_registered_menu(self):
		try:
			obj = self.session.get_object('com.lomiri.MenuRegistrar', '/com/lomiri/MenuRegistrar')
			interface = dbus.Interface(obj, 'com.lomiri.MenuRegistrar')
			menus = interface.GetAppMenus()
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
			return
		self.send_action(action, 'unity.', self.action_path)

	def send_action(self, name, prefix, path):
		try:
			obj       = self.session.get_object(self.bus_name, path)
			interface = dbus.Interface(obj, dbus_interface='org.gtk.Actions')
			print('Fildem sending lomiri action:', self.bus_name, path, name, flush=True)
			interface.Activate(name.replace(prefix, ''), [], dict())
		except Exception as e:
			print('Fildem lomiri action failed:', repr(e), flush=True)

	def get_results(self):
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
		self._update_timer = 0
		self.signal_matcher = []
		self.interface = self.get_interface()
		self.top_level_menus = []
		self.results = None

	def activate(self, selection):
		action = self.actions[selection]
		try:
			self.interface.Event(action, 'clicked', 0, 0)
		except Exception as e:
			self.retry_activate(selection)

	def retry_activate(self, selection):
		# Electron apps change a lot their menus, we have to update to retry
		self.actions = {}
		self.accels = {}
		self.tree = Tree()
		results = self.interface.GetLayout(0, -1, dbus.Array(signature="s"))
		self.collect_entries(results[1], [])
		action = self.actions[selection]
		self.interface.Event(action, 'clicked', 0, 0)

	def get_interface(self):
		bus_name = 'com.canonical.AppMenu.Registrar'
		bus_path = '/com/canonical/AppMenu/Registrar'

		direct_name = self.window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME')
		direct_path = self.window.get_utf8_prop('_GTK_MENUBAR_OBJECT_PATH')
		if direct_name and direct_path:
			try:
				obj = self.session.get_object(direct_name, direct_path)
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
			obj        = self.session.get_object(bus_name, bus_path)
			interface  = dbus.Interface(obj, bus_name)
			xid = self.window.get_xid()
			if xid:
				name, path = interface.GetMenuForWindow(xid)
			else:
				menus = interface.GetMenus()
				name, path = self._find_menu_for_wayland_window(menus)
				if not name or not path:
					return None
			obj        = self.session.get_object(name, path)
			interface  = dbus.Interface(obj, 'com.canonical.dbusmenu')

			s = interface.connect_to_signal('ItemsPropertiesUpdated', self.on_actions_changed)
			self.signal_matcher.append(s)
			s = interface.connect_to_signal('LayoutUpdated', self.layout_updated)
			self.signal_matcher.append(s)

			return interface
		except dbus.exceptions.DBusException:
			# import traceback; traceback.print_exc()
			return None

	def _sender_pid(self, sender):
		try:
			bus_obj = self.session.get_object(
				'org.freedesktop.DBus',
				'/org/freedesktop/DBus'
			)
			bus_iface = dbus.Interface(bus_obj, 'org.freedesktop.DBus')
			return int(bus_iface.GetConnectionUnixProcessID(sender))
		except Exception:
			return 0

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
		if self.interface:
			self.results = self.interface.GetLayout(0, -1, dbus.Array(signature="s"))
			self.collect_entries(self.results[1])

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
			self._update_timer = GLib.timeout_add(200, self._update)

	def _update(self):
		self.actions = {}
		self.accels = {}
		self.tree = Tree()
		self.get_results()
		self._update_timer = 0
		return False

	def remove_actions_listener(self):
		for s in self.signal_matcher:
			s.remove()
		self.signal_matcher = []
		if self._update_timer != 0:
			GLib.source_remove(self._update_timer)


class MenuModel:
	# The menubars have to be reused so they are cleanup
	def __init__(self, session, window):
		self.appmenu = None
		self.gtkmenu = None
		self.mozillamenu = None
		self.lomirimenu = None
		self._session = session
		self.window = window
		self._init_window(session, window)

	def _init_window(self, session, window):
		self.appmenu = DbusAppMenu(session, window)
		self.gtkmenu = DbusGtkMenu(session, window)
		self.mozillamenu = DbusMozillaGtkMenu(session, window)
		self.lomirimenu = DbusLomiriMenu(session, window)

	def _update_menus(self):
		self.gtkmenu.get_results()
		if not len(self.gtkmenu.tree):
			self.mozillamenu.get_results()
		if not len(self.gtkmenu.tree):
			self.lomirimenu.get_results()
		if not len(self.gtkmenu.tree) and not len(self.mozillamenu.tree) and not len(self.lomirimenu.tree):
			self.appmenu.get_results()

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
		actions = self.gtkmenu.actions
		if not len(actions):
			actions = self.mozillamenu.actions
		if not len(actions):
			actions = self.lomirimenu.actions
		if not len(actions):
			actions = self.appmenu.actions
		return actions

	@property
	def accel(self):
		accel = self.gtkmenu.accels
		if not len(accel):
			accel = self.mozillamenu.accels
		if not len(accel):
			accel = self.lomirimenu.accels
		if not len(accel):
			accel = self.appmenu.accels
		return accel

	@property
	def tree(self):
		tree = self.gtkmenu.tree
		if tree.root is None:
			tree = self.mozillamenu.tree
		if tree.root is None:
			tree = self.lomirimenu.tree
		if tree.root is None:
			tree = self.appmenu.tree
		return tree

	@property
	def top_level_menus(self):
		if len(self.gtkmenu.top_level_menus):
			return self.gtkmenu.top_level_menus
		elif len(self.mozillamenu.top_level_menus):
			return self.mozillamenu.top_level_menus
		elif len(self.lomirimenu.top_level_menus):
			return self.lomirimenu.top_level_menus
		else:
			return self.appmenu.top_level_menus

	def activate(self, selection):
		if selection in self.gtkmenu.actions:
			self.gtkmenu.activate(selection)

		elif selection in self.mozillamenu.actions:
			self.mozillamenu.activate(selection)

		elif selection in self.lomirimenu.actions:
			self.lomirimenu.activate(selection)

		elif selection in self.appmenu.actions:
			self.appmenu.activate(selection)

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
		if self.appmenu is not None:
			self.appmenu.remove_actions_listener()
		if self.gtkmenu is not None:
			self.gtkmenu.remove_actions_listener()
		if self.mozillamenu is not None:
			self.mozillamenu.remove_actions_listener()
		if self.lomirimenu is not None:
			self.lomirimenu.remove_actions_listener()
