#!/usr/bin/python3

from __future__ import annotations

import json

import dbus
import dbus.service

from gi.repository import GLib

from fildem.menu_model.menu_model import MenuModel
from fildem.menu_model.menu_item import stringify_variant
from fildem.utils.window import Window


BUS_NAME = 'org.gnome.GlobalMenu'
BUS_PATH = '/org/gnome/GlobalMenu'


class GlobalMenuService(dbus.service.Object):
	def __init__(self):
		self._session = dbus.SessionBus()
		self._bus_name = dbus.service.BusName(BUS_NAME, bus=self._session)
		self._window_key = ''
		self._window_info = {}
		self._generation = 0
		self._menu_model = None
		self._current_source_generation = 0
		self._pending_build_id = 0
		self._pending_build_key = ''
		self._bar_cache = {}
		self._last_emitted_bar = ''
		self._current_bar = {
			'source': '',
			'generation': 0,
			'app_id': '',
			'menus': [],
		}
		dbus.service.Object.__init__(self, self._bus_name, BUS_PATH)

	def _window_from_info(self, info):
		window = Window()
		flattened = {str(key): stringify_variant(value) for key, value in dict(info).items()}
		for key, value in flattened.items():
			if key == 'pid':
				try:
					window.set_pid(int(value))
				except Exception:
					window.set_pid(0)
				continue
			if key == 'xid':
				try:
					window.set_xid(int(value))
				except Exception:
					window.set_xid(0)
				continue

			text = '' if value is None else str(value)
			window.set_utf8_prop(key, text)
			if key.startswith('gtk_'):
				window.set_utf8_prop(f'_{key.upper()}', text)
			elif key.startswith('_GTK_'):
				window.set_utf8_prop(key, text)
		return window

	def _window_signature(self, info):
		parts = []
		for key in (
			'pid', 'xid', 'appId', 'wmClass',
			'gtk_unique_bus_name', 'gtk_application_object_path',
			'gtk_window_object_path', 'gtk_menubar_object_path',
			'gtk_app_menu_object_path',
		):
			value = info.get(key, '')
			parts.append(f'{key}={value}')
		# GTK windows expose stable object paths, so we can ignore title churn.
		# Non-GTK windows often only have pid/app metadata, which is too coarse
		# to distinguish multiple windows of the same app; for those, fold the
		# title into the signature as a fallback.
		has_gtk_identity = any(info.get(key, '') for key in (
			'gtk_unique_bus_name', 'gtk_application_object_path',
			'gtk_window_object_path', 'gtk_menubar_object_path',
			'gtk_app_menu_object_path',
		))
		if not has_gtk_identity:
			parts.append(f"title={info.get('title', '')}")
		return '|'.join(parts)

	def _install_model(self, window):
		if self._menu_model is not None:
			try:
				self._menu_model.destroy()
			except Exception:
				pass
		self._menu_model = MenuModel(self._session, window)
		self._menu_model.set_refresh_callback(self._on_model_refresh)
		self._menu_model._update_menus()

	def _refresh_bar(self, generation=None):
		if self._menu_model is None:
			gen = self._generation if generation is None else int(generation)
			self._current_bar = {
				'source': '',
				'generation': gen,
				'app_id': '',
				'menus': [],
			}
			return self._current_bar

		if generation is None:
			generation = self._generation
		else:
			self._generation = int(generation)
		self._current_bar = self._menu_model.serialize_bar(int(generation))
		return self._current_bar

	def _is_gtk_window(self, info):
		return any(info.get(key, '') for key in (
			'gtk_unique_bus_name', 'gtk_application_object_path',
			'gtk_window_object_path', 'gtk_menubar_object_path',
			'gtk_app_menu_object_path',
		))

	def _cancel_pending_build(self):
		if not self._pending_build_id:
			return
		try:
			GLib.source_remove(self._pending_build_id)
		except Exception:
			pass
		self._pending_build_id = 0
		self._pending_build_key = ''

	def _clear_model(self):
		if self._menu_model is None:
			return
		try:
			self._menu_model.destroy()
		except Exception:
			pass
		self._menu_model = None

	def _publish_cached_or_empty(self, info, generation):
		cached = self._bar_cache.get(self._window_key)
		if cached is not None:
			self._current_bar = dict(cached)
			self._current_bar['generation'] = generation
			self._current_bar['app_id'] = str(info.get('appId', '') or self._current_bar.get('app_id', ''))
		else:
			self._current_bar = {
				'source': '',
				'generation': generation,
				'app_id': str(info.get('appId', '') or ''),
				'menus': [],
			}
		self._emit_bar_changed()

	def _rebuild_current_window(self, generation, info, key):
		self._pending_build_id = 0
		self._pending_build_key = ''
		if key != self._window_key or generation != self._generation:
			return GLib.SOURCE_REMOVE
		window = self._window_from_info(info)
		self._install_model(window)
		self._refresh_bar(generation=generation)
		self._bar_cache[key] = dict(self._current_bar)
		self._emit_bar_changed()
		return GLib.SOURCE_REMOVE

	def _schedule_rebuild(self, info, generation, delay_ms=50):
		self._cancel_pending_build()
		key = self._window_key
		self._pending_build_key = key
		self._pending_build_id = GLib.timeout_add(delay_ms, self._rebuild_current_window, generation, info, key)

	def _emit_bar_changed(self):
		payload = json.dumps(self._current_bar, separators=(',', ':'))
		if payload == self._last_emitted_bar:
			return
		self._last_emitted_bar = payload
		self.MenuBarChanged(self._generation)

	def _on_model_refresh(self):
		if self._menu_model is None:
			return
		self._refresh_bar(generation=self._generation)
		self._emit_bar_changed()

	# -- D-Bus interface -------------------------------------------------

	@dbus.service.method(BUS_NAME, in_signature='a{sv}')
	def SetActiveWindow(self, window_data):
		info = {str(key): stringify_variant(value) for key, value in dict(window_data).items()}
		signature = self._window_signature(info)
		if signature == self._window_key and self._menu_model is not None:
			return

		self._generation += 1
		generation = self._generation
		self._window_key = signature
		self._window_info = info
		window = self._window_from_info(info)
		print('Fildem GlobalMenu active window:', info, flush=True)
		self._cancel_pending_build()
		self._clear_model()

		if self._is_gtk_window(info):
			self._install_model(window)
			self._refresh_bar(generation=generation)
			self._bar_cache[signature] = dict(self._current_bar)
			self._emit_bar_changed()
			return

		self._publish_cached_or_empty(info, generation)
		self._schedule_rebuild(info, generation)

	@dbus.service.method(BUS_NAME, out_signature='s')
	def GetMenuBar(self):
		return json.dumps(self._current_bar, separators=(',', ':'))

	@dbus.service.method(BUS_NAME, in_signature='s', out_signature='s')
	def GetChildren(self, node_id):
		if self._menu_model is None:
			return json.dumps({'generation': self._generation, 'children': []}, separators=(',', ':'))
		children = self._menu_model.serialize_children(node_id)
		return json.dumps({
			'generation': self._generation,
			'children': children,
		}, separators=(',', ':'))

	@dbus.service.method(BUS_NAME, in_signature='us', out_signature='b')
	def Activate(self, generation, node_id):
		if self._menu_model is None or int(generation) != self._generation:
			return False
		node = self._menu_model.find_node(node_id)
		if node is None or node.data is None:
			return False
		selection = str(node.data.text or node.identifier)
		print('Fildem GlobalMenu activate:', generation, node_id, '->', selection, flush=True)
		return bool(self._menu_model.activate(selection))

	@dbus.service.method(BUS_NAME, in_signature='s')
	def Opened(self, node_id):
		print('Fildem GlobalMenu opened:', node_id, flush=True)

	@dbus.service.method(BUS_NAME, in_signature='s')
	def Closed(self, node_id):
		print('Fildem GlobalMenu closed:', node_id, flush=True)

	@dbus.service.method(BUS_NAME, out_signature='a{sv}')
	def GetDiagnostics(self):
		menus = self._current_bar.get('menus', [])
		diag = {
			'generation': self._generation,
			'window_key': self._window_key,
			'source': self._current_bar.get('source', ''),
			'app_id': self._current_bar.get('app_id', ''),
			'root_menus': len(menus),
			'pending_build': bool(self._pending_build_id),
		}
		return diag

	@dbus.service.signal(BUS_NAME, signature='u')
	def MenuBarChanged(self, generation):
		pass

	@dbus.service.signal(BUS_NAME, signature='us')
	def MenuUpdated(self, generation, node_id):
		pass
