import dbus
import json
import time

from gi.repository import GLib

from fildem.utils.global_keybinder import GlobalKeybinder
from fildem.utils.window import WindowManager
from fildem.utils.service import MyService

from fildem.handlers.default import HudMenu
from fildem.handlers.global_menu import GlobalMenu

from fildem.menu_model.menu_model import MenuModel


MENU_CACHE = {}
MENU_CACHE_MAX_AGE = 300


def _wait_for_service(bus_name, timeout=5.0):
	session = dbus.SessionBus()
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			if session.name_has_owner(bus_name):
				return session
		except Exception:
			pass
		time.sleep(0.1)
	return session


def _json_safe(value):
	if isinstance(value, (str, int, float, bool)) or value is None:
		return value
	if isinstance(value, (bytes, bytearray)):
		return list(value)
	if isinstance(value, (list, tuple)):
		return [_json_safe(item) for item in value]
	if isinstance(value, dict):
		return {str(key): _json_safe(item) for key, item in value.items()}
	try:
		return int(value)
	except Exception:
		return str(value)


SYNTHETIC_BROWSER_MENU = [
	{
		'label': 'File',
		'children': [
			{'label': 'New Tab', 'action': '__fildem_shell_key:ctrl+t'},
			{'label': 'New Window', 'action': '__fildem_shell_key:ctrl+n'},
			{'label': 'New Private Window', 'action': '__fildem_shell_key:ctrl+shift+p'},
			{'separator': True},
			{'label': 'Open File…', 'action': '__fildem_shell_key:ctrl+o'},
			{'label': 'Save Page As…', 'action': '__fildem_shell_key:ctrl+s'},
			{'label': 'Print…', 'action': '__fildem_shell_key:ctrl+p'},
			{'separator': True},
			{'label': 'Close Tab', 'action': '__fildem_shell_key:ctrl+w'},
			{'label': 'Close Window', 'action': '__fildem_shell_key:ctrl+shift+w'},
			{'label': 'Quit', 'action': '__fildem_shell_key:ctrl+q'},
		],
	},
	{
		'label': 'Edit',
		'children': [
			{'label': 'Undo', 'action': '__fildem_shell_key:ctrl+z'},
			{'label': 'Redo', 'action': '__fildem_shell_key:ctrl+shift+z'},
			{'separator': True},
			{'label': 'Cut', 'action': '__fildem_shell_key:ctrl+x'},
			{'label': 'Copy', 'action': '__fildem_shell_key:ctrl+c'},
			{'label': 'Paste', 'action': '__fildem_shell_key:ctrl+v'},
			{'label': 'Delete', 'action': '__fildem_shell_key:delete'},
			{'separator': True},
			{'label': 'Select All', 'action': '__fildem_shell_key:ctrl+a'},
			{'label': 'Find in Page…', 'action': '__fildem_shell_key:ctrl+f'},
			{'label': 'Find Again', 'action': '__fildem_shell_key:f3'},
		],
	},
	{
		'label': 'View',
		'children': [
			{'label': 'Reload', 'action': '__fildem_shell_key:ctrl+r'},
			{'label': 'Stop', 'action': '__fildem_shell_key:escape'},
			{'separator': True},
			{'label': 'Zoom In', 'action': '__fildem_shell_key:ctrl+plus'},
			{'label': 'Zoom Out', 'action': '__fildem_shell_key:ctrl+minus'},
			{'label': 'Actual Size', 'action': '__fildem_shell_key:ctrl+0'},
			{'separator': True},
			{'label': 'Full Screen', 'action': '__fildem_shell_key:f11'},
			{'label': 'Page Source', 'action': '__fildem_shell_key:ctrl+u'},
		],
	},
	{
		'label': 'History',
		'children': [
			{'label': 'Back', 'action': '__fildem_shell_key:alt+left'},
			{'label': 'Forward', 'action': '__fildem_shell_key:alt+right'},
			{'separator': True},
			{'label': 'History Sidebar', 'action': '__fildem_shell_key:ctrl+h'},
			{'label': 'Clear Recent History…', 'action': '__fildem_shell_key:ctrl+shift+delete'},
		],
	},
	{
		'label': 'Bookmarks',
		'children': [
			{'label': 'Bookmark Current Tab…', 'action': '__fildem_shell_key:ctrl+d'},
			{'label': 'Manage Bookmarks', 'action': '__fildem_shell_key:ctrl+shift+o'},
			{'label': 'Bookmarks Sidebar', 'action': '__fildem_shell_key:ctrl+b'},
		],
	},
	{
		'label': 'Tools',
		'children': [
			{'label': 'Downloads', 'action': '__fildem_shell_key:ctrl+j'},
			{'label': 'Add-ons and Themes', 'action': '__fildem_shell_key:ctrl+shift+a'},
			{'separator': True},
			{'label': 'Web Developer Tools', 'action': '__fildem_shell_key:ctrl+shift+i'},
			{'label': 'Browser Console', 'action': '__fildem_shell_key:ctrl+shift+j'},
			{'label': 'Settings', 'action': '__fildem_shell_key:ctrl+comma'},
		],
	},
	{
		'label': 'Window',
		'children': [
			{'label': 'Next Tab', 'action': '__fildem_shell_key:ctrl+tab'},
			{'label': 'Previous Tab', 'action': '__fildem_shell_key:ctrl+shift+tab'},
			{'separator': True},
			{'label': 'Minimize', 'action': '__fildem_shell_key:alt+space,n'},
		],
	},
	{
		'label': 'Help',
		'children': [
			{'label': 'Search Help', 'action': '__fildem_shell_key:f1'},
			{'label': 'Troubleshooting Information', 'action': '__fildem_shell_key:ctrl+shift+alt+i'},
		],
	},
]


def _normalise_synthetic(items):
	normalised = []
	for item in items:
		if item.get('separator'):
			normalised.append({
				'label': '',
				'action': '',
				'enabled': True,
				'toggle': False,
				'toggleType': '',
				'shortcut': '',
				'accel': '',
				'iconName': '',
				'iconData': [],
				'separator': True,
				'children': [],
			})
			continue
		children = _normalise_synthetic(item.get('children', []))
		normalised.append({
			'label': item.get('label', ''),
			'action': item.get('action', ''),
			'enabled': item.get('enabled', True),
			'toggle': False,
			'toggleType': '',
			'shortcut': item.get('shortcut', ''),
			'accel': item.get('accel', ''),
			'iconName': item.get('iconName', ''),
			'iconData': item.get('iconData', []),
			'separator': False,
			'children': children,
		})
	return normalised


class DbusMenu:

	def __init__(self):
		self.keyb = GlobalKeybinder.create(self.on_keybind_activated)
		self.app = None
		self.session = dbus.SessionBus()
		self.window = WindowManager.new_window()
		self.tries = 0
		self.retry_timer_id = 0
		self.collect_timer = 0
		self._menu_model = None
		self._window_cache_key = None

		self._init_window()
		self._listen_menu_activated()
		self._listen_hud_activated()
		self._listen_cache_clear()
		WindowManager.add_listener(self.on_window_switched)

	def _init_window(self):
		self._menu_model = MenuModel(self.session, self.window)
		self._menu_model.set_refresh_callback(self._publish_current_menu)
		self._window_cache_key = self._cache_key(self.window)
		if not self._send_cached_menu():
			self._update()

	def _cache_key(self, window):
		parts = [
			str(window.get_pid() or ''),
			str(window.get_xid() or ''),
			str(window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME') or ''),
			str(window.get_utf8_prop('_GTK_APPLICATION_OBJECT_PATH') or ''),
			str(window.get_utf8_prop('_GTK_WINDOW_OBJECT_PATH') or ''),
			str(window.get_utf8_prop('_GTK_MENUBAR_OBJECT_PATH') or ''),
			str(window.get_utf8_prop('_GTK_APP_MENU_OBJECT_PATH') or ''),
			str(window.get_app_name() or ''),
		]
		return '|'.join(parts)

	def _active_provider(self):
		if len(self._menu_model.gtkmenu.actions) or self._menu_model.gtkmenu.tree.root is not None:
			return 'gtk'
		if len(self._menu_model.mozillamenu.actions) or self._menu_model.mozillamenu.tree.root is not None:
			return 'mozilla'
		if len(self._menu_model.lomirimenu.actions) or self._menu_model.lomirimenu.tree.root is not None:
			return 'lomiri'
		if len(self._menu_model.appmenu.actions) or self._menu_model.appmenu.tree.root is not None:
			return 'appmenu'
		return ''

	def _is_chromium_browser_window(self):
		values = [
			self.window.get_app_name(),
			self.window.get_utf8_prop('appId'),
			self.window.get_utf8_prop('wmClass'),
			self.window.get_utf8_prop('title'),
			self.window.get_utf8_prop('_GTK_UNIQUE_BUS_NAME'),
		]
		haystack = ' '.join(str(value or '') for value in values).lower()
		return any(name in haystack for name in [
			'brave',
			'brave-browser',
			'chromium',
			'chrome',
			'google-chrome',
			'microsoft-edge',
			'vivaldi',
		])

	def _send_synthetic_browser_menu(self, start):
		tree = _normalise_synthetic(SYNTHETIC_BROWSER_MENU)
		top_level_menus = [item['label'] for item in tree]
		tree_json = json.dumps(tree, separators=(',', ':'))
		print('Fildem using synthetic browser menu:', self._cache_key(self.window), flush=True)
		self._handle_shortcuts(top_level_menus)
		self._send_msg(top_level_menus)
		self._store_tree_json(tree_json)
		if self._window_cache_key:
			MENU_CACHE[self._window_cache_key] = {
				'time': time.monotonic(),
				'top_level_menus': top_level_menus,
				'tree_json': tree_json,
				'actions': {},
				'provider': 'synthetic-browser',
			}
		print('Fildem menu update took: %.3fs provider=synthetic-browser cache=yes' % (
			time.monotonic() - start,
		), flush=True)

	def _restore_cached_actions(self, cached):
		provider = cached.get('provider', '')
		actions = dict(cached.get('actions', {}))
		if provider == 'gtk':
			self._menu_model.gtkmenu.actions = actions
		elif provider == 'mozilla':
			self._menu_model.mozillamenu.actions = actions
		elif provider == 'lomiri':
			self._menu_model.lomirimenu.actions = actions
		elif provider == 'appmenu':
			self._menu_model.appmenu.actions = actions

	def _send_cached_menu(self):
		cached = MENU_CACHE.get(self._window_cache_key)
		if cached is None:
			return False
		if time.monotonic() - cached.get('time', 0) > MENU_CACHE_MAX_AGE:
			return False
		if cached.get('provider') not in ('synthetic-browser',):
			return False

		self._restore_cached_actions(cached)
		top_level_menus = cached.get('top_level_menus', [])
		print('Fildem menu cache hit:', self._window_cache_key, 'items:', len(top_level_menus), flush=True)
		self._handle_shortcuts(top_level_menus)
		self._send_msg(top_level_menus)
		self._store_tree_json(cached.get('tree_json', '[]'))
		return True

	def on_window_switched(self, window):
		# The menu UI is a separate GTK helper window. On Wayland/Xwayland it
		# does not reliably receive focus-out when GNOME switches applications,
		# so close it explicitly before rebuilding the active app's menu.
		if self.app is not None:
			self.app.quit()
			self.app = None
		self.reset_timeout()
		self.window = window
		self._init_window()

	def reset_timeout(self):
		if self.retry_timer_id:
			GLib.source_remove(self.retry_timer_id)
		self.tries = 0
		self.retry_timer_id = 0

		if self.collect_timer:
			GLib.source_remove(self.collect_timer)
			self.collect_timer = 0

	def _listen_menu_activated(self):
		session = _wait_for_service('es.inled.fildem')
		try:
			proxy = session.get_object('es.inled.fildem', '/es/inled/fildem')
			proxy.connect_to_signal("MenuActivated", self.on_menu_activated)
		except Exception as error:
			print('Fildem failed to connect MenuActivated:', repr(error), flush=True)

	def _listen_hud_activated(self):
		session = _wait_for_service('es.inled.fildem')
		try:
			proxy = session.get_object('es.inled.fildem', '/es/inled/fildem')
			proxy.connect_to_signal("HudActivated", self.on_hud_activated)
		except Exception as error:
			print('Fildem failed to connect HudActivated:', repr(error), flush=True)

	def _listen_cache_clear(self):
		session = _wait_for_service('es.inled.fildem')
		try:
			proxy = session.get_object('es.inled.fildem', '/es/inled/fildem')
			proxy.connect_to_signal("ClearMenuCacheSignal", self.on_cache_clear_requested)
		except Exception as error:
			print('Fildem failed to connect ClearMenuCacheSignal:', repr(error), flush=True)

	def on_cache_clear_requested(self):
		print('Fildem clearing menu cache:', len(MENU_CACHE), flush=True)
		MENU_CACHE.clear()
		if self.app is not None:
			self.app.quit()
			self.app = None
		self.reset_timeout()
		self._init_window()

	def on_menu_activated(self, menu: str, x: int):
		print('Fildem menu signal:', repr(menu), x, flush=True)
		if menu.startswith('__fildem_activate:'):
			self.activate(menu[len('__fildem_activate:'):])
			return
		if menu == '__fildem_move':
			self._move_menu(x)
			return

		if x != -1:
			self._start_app(menu, x)
		else:
			self._start_app(menu)

	def on_hud_activated(self):
		menu = HudMenu(self)
		menu.run()

	def on_keybind_activated(self, character: str):
		self.on_app_started()
		self._start_app(character)

	def _move_menu(self, x: int):
		if self.app is None:
			return

		self.app.move_window(x)

	def _start_app(self, menu_activated: str, offset=300):
		if self.app is None:
			self.app = GlobalMenu(self, menu_activated, offset)
			self.app.connect('shutdown', self.on_app_shutdown)
			self.app.run()

	def on_app_started(self):
		self._echo_onoff(True)

	def on_app_shutdown(self, app):
		self._echo_onoff(False)
		self.app = None

	def _echo_onoff(self, on: bool):
		self.proxy = dbus.SessionBus().get_object('es.inled.fildem', '/es/inled/fildem')
		self.proxy.EchoMenuOnOff(on)

	def _handle_shortcuts(self, top_level_menus):
		self.keyb.remove_all_keybindings()
		for label in top_level_menus:
			idx = label.find('_')
			if idx == -1:
				continue
			c = label[idx + 1]
			self.keyb.add_keybinding(c)

	def _retry_init(self):
		self.retry_timer_id = 0
		self._init_window()
		return False

	def _update_menus(self):
		self._menu_model._update_menus()

		max_tries = 2
		if self.tries < max_tries and self.tree.root is None:
			self.tries += 1
			self.retry_timer_id = GLib.timeout_add_seconds(2, self._retry_init)

	def _update(self):
		start = time.monotonic()
		self._update_menus()
		# Browser synthetic menus are useful as a last-resort compatibility
		# layer. Prefer real GTK/AppMenu/Lomiri exports first; if Chromium- or
		# Firefox-derived browsers publish nothing useful on GNOME Wayland, give
		# them a functional shortcut-backed menu instead of leaving the panel
		# empty.
		provider = self._active_provider()
		if not provider and self._is_chromium_browser_window():
			self._send_synthetic_browser_menu(start)
			return
		self._handle_shortcuts(self._menu_model.top_level_menus)
		self._send_msg(self._menu_model.top_level_menus)
		tree_json = self._store_tree()
		if self._window_cache_key and tree_json != '[]' and provider == 'synthetic-browser':
			MENU_CACHE[self._window_cache_key] = {
				'time': time.monotonic(),
				'top_level_menus': list(self._menu_model.top_level_menus),
				'tree_json': tree_json,
				'actions': dict(self._menu_model.action_map),
				'provider': provider,
			}
		print('Fildem menu update took: %.3fs provider=%s cache=%s' % (
			time.monotonic() - start,
			provider or 'none',
			'yes' if self._window_cache_key in MENU_CACHE else 'no',
		), flush=True)

	def _publish_current_menu(self):
		self._handle_shortcuts(self._menu_model.top_level_menus)
		self._send_msg(self._menu_model.top_level_menus)
		tree_json = self._store_tree()
		self._send_tree_json(tree_json)

	def _store_tree(self):
		tree = self._build_tree_payload()
		print('Fildem storing native tree:', len(tree), flush=True)
		print('Fildem native hierarchy:', [(item['label'], len(item['children'])) for item in tree], flush=True)
		tree_json = json.dumps(tree, separators=(',', ':'))
		self._store_tree_json(tree_json)
		return tree_json

	def _build_tree_payload(self):
		def node_data(node):
			data = node.data
			children = [node_data(child) for child in self.tree.children(node.identifier)]
			children = [child for child in children if child is not None]
			if data and not data.separator and not data.action and not children:
				return None
			return {
				'label': str(data.label if data else node.tag),
				'action': str(data.text if data else ''),
				'enabled': bool(data.enabled) if data else True,
				'toggle': bool(data.toggle_state) if data else False,
				'toggleType': str(getattr(data, 'toggle_type', '') or '') if data else '',
				'section': _json_safe(getattr(data, 'section', None)) if data else None,
				'shortcut': str(getattr(data, 'shortcut', '') or '') if data else '',
				'accel': str(getattr(data, 'accel', '') or '') if data else '',
				'iconName': str(getattr(data, 'icon_name', '') or '') if data else '',
				'iconData': _json_safe(getattr(data, 'icon_data', [])) if data else [],
				'separator': bool(data.separator) if data else False,
				'children': children,
			}

		root = self.tree[self.tree.root] if self.tree.root else None
		tree = [node_data(child) for child in self.tree.children(root.identifier)] if root else []
		return [item for item in tree if item is not None]

	def _store_tree_json(self, tree_json):
		proxy = self.session.get_object('es.inled.fildem', '/es/inled/fildem')
		proxy.EchoStoreMenuTree(tree_json)

	def _send_tree_json(self, tree_json):
		proxy = self.session.get_object('es.inled.fildem', '/es/inled/fildem')
		proxy.EchoSendMenuTree(tree_json)

	def _send_msg(self, top_level_menus):
		if len(top_level_menus) == 0:
			top_level_menus = dbus.Array(signature="s")
		proxy = self.session.get_object('es.inled.fildem', '/es/inled/fildem')
		proxy.EchoSendTopLevelMenus(top_level_menus)

	@property
	def prompt(self):
		return self.window.get_app_name()

	@property
	def actions(self):
		return self._menu_model.actions

	def accel(self):
		return self._menu_model.accel

	@property
	def tree(self):
		return self._menu_model.tree

	def activate(self, selection):
		self._menu_model.activate(selection)
